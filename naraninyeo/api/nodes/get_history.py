"""Task that fetches recent conversation history."""

from __future__ import annotations

from naraninyeo.api.infrastructure.interfaces import MessageRepository
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class GetHistoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MessageRepository, *, limit: int = 20) -> None:
        super().__init__(repository=repository, limit=limit)
        self._repository = repository
        self._limit = limit

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        tenant = payload.tenant
        channel_id = payload.inbound.channel.channel_id
        history = await self._repository.history(tenant, channel_id, limit=self._limit)
        payload.history = list(history)
        context.set_state("history_size", len(history))
        return TaskResult(output=payload, diagnostics={"history": len(history)})
