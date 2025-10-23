"""Task responsible for persisting inbound messages."""

from __future__ import annotations

from naraninyeo.api.interfaces import MessageRepository
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class StoreMessageTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MessageRepository) -> None:
        super().__init__(repository=repository)
        self._repository = repository

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        message = payload.inbound
        await self._repository.save(message)
        payload.stored = message
        context.set_state("last_message_id", message.message_id)
        return TaskResult(output=payload, diagnostics={"stored": message.message_id})
