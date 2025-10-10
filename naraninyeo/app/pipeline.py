"""Straightforward chat pipeline orchestrating message handling."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Sequence
from zoneinfo import ZoneInfo

from naraninyeo.app.context import ReplyContextBuilder
from naraninyeo.assistant.memory_management import (
    ConversationMemoryExtractor,
    MemoryStore,
)
from naraninyeo.assistant.message_repository import MessageRepository
from naraninyeo.assistant.models import (
    KnowledgeReference,
    MemoryItem,
    Message,
    ReplyContext,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
)
from naraninyeo.assistant.retrieval import (
    RetrievalExecutor,
    RetrievalPlanner,
    RetrievalPostProcessor,
    RetrievalResultCollectorFactory,
)
from naraninyeo.plugins import ChatMiddleware
from naraninyeo.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from naraninyeo.app.reply import ReplyGenerator

EmitFn = Callable[[Message], Awaitable[None]]
StepFn = Callable[["PipelineState", "PipelineTools", EmitFn], Awaitable[None]]
DEFAULT_RETRIEVAL_TIMEOUT = 10.0


@dataclass
class PipelineState:
    incoming: Message
    history: list[Message] | None = None
    reply_context: ReplyContext | None = None
    plans: list[RetrievalPlan] | None = None
    retrieval_results: list[RetrievalResult] | None = None
    short_term_memory: list[MemoryItem] | None = None
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
    # 원본 메시지를 즉시 저장하고, 완료 여부는 파이프라인 마지막에서 확인한다.
    task = asyncio.create_task(tools.message_repository.save(state.incoming))
    state.finalizers.append(task)


async def ingest_memory(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    history = await tools.message_repository.get_surrounding_messages(
        state.incoming,
        before=tools.settings.HISTORY_LIMIT,
        after=0,
    )
    state.history = history
    now = datetime.now(tz=ZoneInfo(tools.settings.TIMEZONE))
    state.short_term_memory = await tools.memory_store.recall(
        channel_id=state.incoming.channel.channel_id,
        limit=5,
        now=now,
    )

    async def ingest() -> None:
        # 새 메시지를 분석해 기억이 생기면 비동기적으로 저장한다.
        items = await tools.memory_extractor.extract_from_message(state.incoming, history)
        if items:
            await tools.memory_store.put(items)

    state.finalizers.append(asyncio.create_task(ingest()))


async def should_reply(state: PipelineState, _tools: PipelineTools, _: EmitFn) -> None:
    text = (state.incoming.content.text or "").strip()
    if not text.startswith("/"):
        # 슬래시가 없는 일반 메시지는 사용자 간 대화로 간주해 봇이 응답하지 않는다.
        state.stop = True


async def build_context(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    state.reply_context = await tools.context_builder.build(
        state.incoming,
        history=state.history,
        short_term_memory=state.short_term_memory,
    )


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
    # 처리 결과는 후속 단계에서 참고하도록 상태에 저장한다.
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
        # 스트리밍으로 생성된 메시지를 소비자에게 즉시 전달한다.
        await emit(reply)


async def after_reply_stream(state: PipelineState, tools: PipelineTools, _: EmitFn) -> None:
    for middleware in tools.middlewares:
        await middleware.after_reply_stream()


async def finalize_background(state: PipelineState, _tools: PipelineTools, _: EmitFn) -> None:
    if state.finalizers:
        await asyncio.gather(*state.finalizers, return_exceptions=True)
        state.finalizers.clear()


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
                        # stop 플래그가 서면 이후 단계는 건너뛰고 종료한다.
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
