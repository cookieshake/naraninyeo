"""Straightforward chat pipeline orchestrating message handling."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from opentelemetry.trace import get_tracer

from naraninyeo.assistant.llm_toolkit import LLMToolFactory
from naraninyeo.assistant.memory_management import (
    ConversationMemoryExtractor,
    MemoryStore,
)
from naraninyeo.assistant.message_repository import MessageRepository
from naraninyeo.assistant.models import (
    Author,
    EnvironmentalContext,
    KnowledgeReference,
    Message,
    MessageContent,
    ReplyContext,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
)
from naraninyeo.assistant.prompts import ReplyPrompt
from naraninyeo.assistant.retrieval_workflow import (
    RetrievalExecutor,
    RetrievalPlanner,
    RetrievalPostProcessor,
    RetrievalResultCollectorFactory,
)
from naraninyeo.plugins import ChatMiddleware
from naraninyeo.settings import Settings

EmitFn = Callable[[Message], Awaitable[None]]
StepFn = Callable[["PipelineState", "PipelineTools", EmitFn], Awaitable[None]]
DEFAULT_RETRIEVAL_TIMEOUT = 10.0


class ReplyContextBuilder:
    """Gather message history and memory to form the reply context."""

    def __init__(
        self,
        message_repository: MessageRepository,
        memory_store: MemoryStore,
        settings: Settings,
    ) -> None:
        self._messages = message_repository
        self._memory = memory_store
        self._settings = settings

    async def build(self, message: Message) -> ReplyContext:
        history = await self._messages.get_surrounding_messages(
            message=message,
            before=self._settings.HISTORY_LIMIT,
            after=0,
        )
        short_term_memory = await self._memory.recall(
            channel_id=message.channel.channel_id,
            limit=5,
            now=datetime.now(tz=ZoneInfo(self._settings.TIMEZONE)),
        )
        environment = EnvironmentalContext(
            timestamp=datetime.now(tz=ZoneInfo(self._settings.TIMEZONE)),
            location=self._settings.LOCATION,
        )
        return ReplyContext(
            environment=environment,
            last_message=message,
            latest_history=history,
            knowledge_references=[],
            processing_logs=[],
            short_term_memory=short_term_memory,
        )


@dataclass
class PipelineState:
    incoming: Message
    history: list[Message] | None = None
    reply_needed: bool | None = None
    reply_context: ReplyContext | None = None
    plans: list[RetrievalPlan] | None = None
    retrieval_results: list[RetrievalResult] | None = None
    stop: bool = False
    finalizers: list[asyncio.Task[object]] = field(default_factory=list)


@dataclass
class PipelineStep:
    name: str
    fn: StepFn


@dataclass
class PipelineTools:
    settings: Settings
    message_repository: MessageRepository
    memory_store: MemoryStore
    memory_extractor: ConversationMemoryExtractor
    retrieval_planner: RetrievalPlanner
    retrieval_executor: RetrievalExecutor
    retrieval_collector_factory: RetrievalResultCollectorFactory
    retrieval_post_processor: RetrievalPostProcessor
    reply_generator: "ReplyGenerator"
    context_builder: ReplyContextBuilder
    middlewares: list[ChatMiddleware] = field(default_factory=list)
    retrieval_timeout_seconds: float = DEFAULT_RETRIEVAL_TIMEOUT


class StepRegistry:
    """Keeps the available steps by name so plugins can add to the flow."""

    def __init__(self) -> None:
        self._steps: dict[str, StepFn] = {}

    def register(self, step: PipelineStep) -> None:
        if step.name in self._steps:
            raise ValueError(f"Duplicate pipeline step name: {step.name}")
        self._steps[step.name] = step.fn

    def register_many(self, steps: Sequence[PipelineStep]) -> None:
        for step in steps:
            self.register(step)

    def get(self, name: str) -> StepFn:
        if name not in self._steps:
            raise KeyError(f"Unknown pipeline step: {name}")
        return self._steps[name]


async def save_incoming(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    task = asyncio.create_task(tools.message_repository.save(state.incoming))
    state.finalizers.append(task)


async def ingest_memory(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    history = await tools.message_repository.get_surrounding_messages(
        state.incoming,
        before=tools.settings.HISTORY_LIMIT,
        after=0,
    )
    state.history = history

    async def ingest() -> None:
        items = await tools.memory_extractor.extract_from_message(state.incoming, history)
        if items:
            await tools.memory_store.put(items)

    state.finalizers.append(asyncio.create_task(ingest()))


async def should_reply(state: PipelineState, _tools: PipelineTools, _: EmitFn) -> None:
    state.reply_needed = state.incoming.content.text.startswith("/")
    if not state.reply_needed:
        state.stop = True


async def build_context(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    state.reply_context = await tools.context_builder.build(state.incoming)


async def before_retrieval(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    for middleware in tools.middlewares:
        await middleware.before_retrieval(state.reply_context)


async def plan_retrieval(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    state.plans = await tools.retrieval_planner.plan(state.reply_context)


async def execute_retrieval(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    plans = state.plans or []
    collector = tools.retrieval_collector_factory.create()
    logs = await tools.retrieval_executor.execute_with_timeout(
        plans,
        state.reply_context,
        tools.retrieval_timeout_seconds,
        collector=collector,
    )
    results = await collector.snapshot()
    state.reply_context.processing_logs.extend(
        [f"plan={entry.plan.model_dump()} matched={entry.matched}" for entry in logs]
    )
    state.retrieval_results = tools.retrieval_post_processor.process(results, state.reply_context)


async def after_retrieval(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    for middleware in tools.middlewares:
        await middleware.after_retrieval(state.reply_context)


async def attach_references(state: PipelineState, _tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    results = state.retrieval_results or []
    refs = [
        KnowledgeReference(
            content=result.content,
            source_name=result.source_name,
            timestamp=result.source_timestamp,
        )
        for result in results
        if result.status == RetrievalStatus.SUCCESS
    ]
    state.reply_context.knowledge_references = refs


async def before_reply_stream(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    if state.reply_context is None:
        return
    for middleware in tools.middlewares:
        await middleware.before_reply_stream(state.reply_context)


async def stream_reply(state: PipelineState, tools: PipelineTools, emit: EmitFn) -> None:
    if state.reply_context is None:
        return
    async for reply in tools.reply_generator.stream(state.reply_context):
        await emit(reply)


async def after_reply_stream(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    for middleware in tools.middlewares:
        await middleware.after_reply_stream()


async def finalize_background(state: PipelineState, _tools: PipelineTools, _: EmitFn) -> None:
    if state.finalizers:
        await asyncio.gather(*state.finalizers, return_exceptions=True)


DEFAULT_STEPS: list[PipelineStep] = [
    PipelineStep("save_incoming", save_incoming),
    PipelineStep("ingest_memory", ingest_memory),
    PipelineStep("should_reply", should_reply),
    PipelineStep("build_context", build_context),
    PipelineStep("before_retrieval", before_retrieval),
    PipelineStep("plan_retrieval", plan_retrieval),
    PipelineStep("execute_retrieval", execute_retrieval),
    PipelineStep("after_retrieval", after_retrieval),
    PipelineStep("attach_references", attach_references),
    PipelineStep("before_reply_stream", before_reply_stream),
    PipelineStep("stream_reply", stream_reply),
    PipelineStep("after_reply_stream", after_reply_stream),
    PipelineStep("finalize", finalize_background),
]


def default_step_order() -> list[str]:
    return [step.name for step in DEFAULT_STEPS]


class ChatPipeline:
    def __init__(
        self,
        tools: PipelineTools,
        step_registry: StepRegistry,
        step_order: Sequence[str],
        reply_saver: Callable[[Message], Awaitable[None]] | None = None,
    ) -> None:
        self.tools = tools
        self.step_registry = step_registry
        self.step_order = list(step_order)
        self._save_reply = reply_saver

    async def run(self, message: Message) -> AsyncIterator[Message]:
        for middleware in self.tools.middlewares:
            await middleware.before_handle(message)

        queue: asyncio.Queue[Message] = asyncio.Queue()
        state = PipelineState(incoming=message)

        async def emit(reply: Message) -> None:
            await queue.put(reply)

        producer_done = asyncio.Event()

        async def produce() -> None:
            try:
                for name in self.step_order:
                    step = self.step_registry.get(name)
                    await step(state, self.tools, emit)
                    if state.stop:
                        break
            finally:
                producer_done.set()

        producer_task = asyncio.create_task(produce())

        try:
            while True:
                if producer_done.is_set() and queue.empty():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                yield item
                if self._save_reply is not None:
                    await self._save_reply(item)
                for middleware in self.tools.middlewares:
                    await middleware.on_reply(item)
        finally:
            await producer_task
            if state.finalizers:
                await asyncio.gather(*state.finalizers, return_exceptions=True)


class ReplyGenerator:
    def __init__(self, settings: Settings, llm_factory: LLMToolFactory):
        self.settings = settings
        self.tool = llm_factory.reply_tool()

    def _create_message(self, context: ReplyContext, text: str) -> Message:
        now = datetime.now(ZoneInfo(self.settings.TIMEZONE))
        timestamp_millis = int(now.timestamp() * 1000)
        return Message(
            message_id=f"{context.last_message.message_id}-reply-{timestamp_millis}",
            channel=context.last_message.channel,
            author=Author(
                author_id=self.settings.BOT_AUTHOR_ID,
                author_name=self.settings.BOT_AUTHOR_NAME,
            ),
            content=MessageContent(text=text, attachments=[]),
            timestamp=now,
        )

    async def stream(self, context: ReplyContext) -> AsyncIterator[Message]:
        prompt = ReplyPrompt(context=context, bot_name=self.settings.BOT_AUTHOR_NAME)
        buffer = self.settings.REPLY_TEXT_PREFIX
        async for chunk in self.tool.stream_text(prompt, delta=True):
            buffer += chunk
            while "\n\n" in buffer:
                text_to_send, buffer = buffer.split("\n\n", 1)
                yield self._create_message(context, text_to_send)
        if buffer:
            yield self._create_message(context, buffer)


class NewMessageHandler:
    def __init__(self, pipeline: ChatPipeline):
        self._pipeline = pipeline

    async def handle(self, message: Message) -> AsyncIterator[Message]:
        with get_tracer(__name__).start_as_current_span("handle new message"):
            async for reply in self._pipeline.run(message):
                yield reply
