import asyncio

import nanoid
from opentelemetry.trace import get_tracer

from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.gateway.retrieval import PlanExecutorStrategy, RetrievalResultCollector
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import (
    ChatHistoryRef,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
)


class ChatHistoryStrategy(PlanExecutorStrategy):
    def __init__(self, message_repository: MessageRepository):
        self.message_repository = message_repository

    def supports(self, plan: RetrievalPlan) -> bool:
        return isinstance(plan, RetrievalPlan) and plan.search_type == "chat_history"

    @get_tracer(__name__).start_as_current_span("execute chat history retrieval")
    async def execute(self, plan: RetrievalPlan, context: ReplyContext, collector: RetrievalResultCollector):
        messages = await self.message_repository.search_similar_messages(
            channel_id=context.last_message.channel.channel_id,
            keyword=plan.query,
            limit=3,
        )
        chunks = [
            self.message_repository.get_surrounding_messages(message=message, before=3, after=3) for message in messages
        ]
        for task in asyncio.as_completed(chunks):
            chunk = await task
            if not chunk:
                continue
            ref = ChatHistoryRef(value=chunk)
            await collector.add(
                RetrievalResult(
                    plan=plan,
                    result_id=nanoid.generate(),
                    content=ref.as_text(),
                    ref=ref,
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=f"chat_history_{chunk[-1].timestamp_str}",
                    source_timestamp=chunk[-1].timestamp if chunk else None,
                )
            )
