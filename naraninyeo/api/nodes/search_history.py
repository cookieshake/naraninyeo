"""Task that searches within the conversation transcript."""

from __future__ import annotations

from naraninyeo.api.infrastructure.interfaces import MessageRepository
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class SearchHistoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MessageRepository, *, limit: int = 10) -> None:
        super().__init__(repository=repository, limit=limit)
        self._repository = repository
        self._limit = limit

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        tenant = payload.tenant
        channel_id = payload.inbound.channel.channel_id
        query = payload.inbound.content.text
        if len(query) < 3:
            return TaskResult(output=payload, diagnostics={"related_history": 0})
        related = await self._repository.search(tenant, channel_id, query, limit=self._limit)
        payload.related_history = list(related)
        context.set_state("related_history", [message.message_id for message in related])
        return TaskResult(output=payload, diagnostics={"related_history": len(related)})
