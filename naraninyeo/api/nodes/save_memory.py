"""Task that persists generated memory items."""

from __future__ import annotations

from naraninyeo.api.infrastructure.interfaces import MemoryRepository
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class SaveMemoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MemoryRepository) -> None:
        super().__init__(repository=repository)
        self._repository = repository

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        items = payload.memory_candidates
        if items:
            await self._repository.save_many(items)
            payload.saved_memory = list(items)
            context.set_state("saved_memory", [item.memory_id for item in items])
        return TaskResult(output=payload, diagnostics={"saved_memory": len(items)})
