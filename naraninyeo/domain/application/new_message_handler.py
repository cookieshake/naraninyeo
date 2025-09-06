import asyncio
from typing import AsyncIterator

from opentelemetry.trace import get_tracer

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import KnowledgeReference
from naraninyeo.domain.model.retrieval import RetrievalStatus
from naraninyeo.domain.usecase.message import MessageUseCase
from naraninyeo.domain.usecase.reply import ReplyUseCase
from naraninyeo.domain.usecase.retrieval import RetrievalUseCase
from naraninyeo.domain.usecase.memory import MemoryUseCase
from naraninyeo.domain.application.context_builder import ReplyContextBuilder


class NewMessageHandler:
    def __init__(
        self,
        message_use_case: MessageUseCase,
        retrieval_use_case: RetrievalUseCase,
        reply_use_case: ReplyUseCase,
        memory_use_case: MemoryUseCase,
        reply_context_builder: ReplyContextBuilder,
    ):
        self.message_use_case = message_use_case
        self.retrieval_use_case = retrieval_use_case
        self.reply_use_case = reply_use_case
        self.memory_use_case = memory_use_case
        self.reply_context_builder = reply_context_builder

    async def handle(self, message: Message) -> AsyncIterator[Message]:
        with get_tracer(__name__).start_as_current_span("handle new message"):
            save_new_message_task = asyncio.create_task(self.message_use_case.save_message(message))
            # Ingest potential short-term memory in parallel using recent history
            history = await self.message_use_case.get_recent_messages(message, limit=10)
            memory_ingest_task = asyncio.create_task(self.memory_use_case.ingest(message, history))
            try:
                if await self.message_use_case.reply_needed(message):
                    with get_tracer(__name__).start_as_current_span("generate reply"):
                        async for reply in self._generate_reply(message):
                            yield reply
                            await self.message_use_case.save_message(reply)
            finally:
                await asyncio.gather(save_new_message_task, memory_ingest_task)

    async def _generate_reply(self, message: Message) -> AsyncIterator[Message]:
        reply_context = await self.reply_context_builder.build(message)

        plans = await self.retrieval_use_case.plan_retrieval(reply_context)
        retrieval_results = await self.retrieval_use_case.execute_retrieval(plans, reply_context)
        reply_context.knowledge_references = [
            KnowledgeReference(
                content=result.content,
                source_name=result.source_name,
                timestamp=result.source_timestamp,
            )
            for result in retrieval_results
            if result.status == RetrievalStatus.SUCCESS
        ]
        async for reply in self.reply_use_case.create_replies(reply_context):
            yield reply
