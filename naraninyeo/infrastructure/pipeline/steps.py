from __future__ import annotations

import asyncio
from dataclasses import dataclass

from naraninyeo.core.middleware import ChatMiddleware
from naraninyeo.core.pipeline.steps import PipelineStep
from naraninyeo.core.pipeline.types import PipelineState
from naraninyeo.infrastructure.pipeline.context import ReplyContextBuilder
from naraninyeo.domain.model.reply import KnowledgeReference
from naraninyeo.domain.model.retrieval import RetrievalStatus
from naraninyeo.domain.gateway.memory import MemoryExtractor, MemoryStore
from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.gateway.retrieval import (
    RetrievalPlanExecutor,
    RetrievalPlanner,
    RetrievalResultCollectorFactory,
)
from naraninyeo.domain.gateway.retrieval_post import RetrievalPostProcessor
from naraninyeo.domain.variable import Variables
from naraninyeo.infrastructure.settings import Settings


@dataclass
class PipelineDeps:
    settings: Settings
    message_repository: MessageRepository
    memory_store: MemoryStore
    memory_extractor: MemoryExtractor
    retrieval_planner: RetrievalPlanner
    retrieval_executor: RetrievalPlanExecutor
    retrieval_collector_factory: RetrievalResultCollectorFactory
    retrieval_post_processor: RetrievalPostProcessor
    reply_generator: ReplyGenerator
    context_builder: ReplyContextBuilder
    middlewares: list[ChatMiddleware]


class SaveIncomingMessageStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("save_incoming")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        t = asyncio.create_task(self.deps.message_repository.save(state.incoming))
        state.finalizers.append(t)


class IngestMemoryStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("ingest_memory")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        # Fetch recent history needed for memory ingestion
        history = await self.deps.message_repository.get_surrounding_messages(
            state.incoming, before=self.deps.settings.HISTORY_LIMIT, after=0
        )
        state.history = history

        async def ingest():
            items = await self.deps.memory_extractor.extract_from_message(state.incoming, history)
            if items:
                await self.deps.memory_store.put(items)

        t = asyncio.create_task(ingest())
        state.finalizers.append(t)


class ShouldReplyStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("should_reply")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        # Simple policy: commands start with '/'
        state.reply_needed = state.incoming.content.text.startswith("/")
        if not state.reply_needed:
            state.stop = True


class BuildContextStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("build_context")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        state.reply_context = await self.deps.context_builder.build(state.incoming)


class BeforeRetrievalHookStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("before_retrieval_hook")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        for mw in self.deps.middlewares:
            await mw.before_retrieval(state.reply_context)


class PlanRetrievalStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("plan_retrieval")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        state.plans = await self.deps.retrieval_planner.plan(state.reply_context)


class ExecuteRetrievalStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("execute_retrieval")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        plans = state.plans or []
        collector = self.deps.retrieval_collector_factory.create()
        await self.deps.retrieval_executor.execute_with_timeout(
            plans,
            state.reply_context,
            Variables.RETRIEVAL_EXECUTION_TIMEOUT,
            collector=collector,
        )
        results = await collector.snapshot()
        state.retrieval_results = self.deps.retrieval_post_processor.process(results, state.reply_context)


class AfterRetrievalHookStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("after_retrieval_hook")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        for mw in self.deps.middlewares:
            await mw.after_retrieval(state.reply_context)


class AttachReferencesStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("attach_references")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        results = state.retrieval_results or []
        refs = [
            KnowledgeReference(content=r.content, source_name=r.source_name, timestamp=r.source_timestamp)
            for r in results
            if r.status == RetrievalStatus.SUCCESS
        ]
        state.reply_context.knowledge_references = refs


class BeforeReplyStreamHookStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("before_reply_stream_hook")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        for mw in self.deps.middlewares:
            await mw.before_reply_stream(state.reply_context)


class StreamReplyStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("stream_reply")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.reply_context is None:
            return
        async for reply in self.deps.reply_generator.generate_reply(state.reply_context):  # type: ignore
            await emit(reply)


class AfterReplyStreamHookStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("after_reply_stream_hook")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        for mw in self.deps.middlewares:
            await mw.after_reply_stream()


class FinalizeBackgroundStep(PipelineStep):
    def __init__(self, deps: PipelineDeps) -> None:
        super().__init__("finalize")
        self.deps = deps

    async def run(self, state: PipelineState, emit):
        if state.finalizers:
            await asyncio.gather(*state.finalizers, return_exceptions=True)


def default_pipeline_order() -> list[str]:
    return [
        "save_incoming",
        "ingest_memory",
        "should_reply",
        "build_context",
        "before_retrieval_hook",
        "plan_retrieval",
        "execute_retrieval",
        "after_retrieval_hook",
        "attach_references",
        "before_reply_stream_hook",
        "stream_reply",
        "after_reply_stream_hook",
        "finalize",
    ]
