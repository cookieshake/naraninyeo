"""Task that applies memory management policies."""

from __future__ import annotations

from naraninyeo.api.interfaces import MemoryRepository, MemoryStrategy
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class ManageMemoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MemoryRepository, strategy: MemoryStrategy) -> None:
        super().__init__(repository=repository, strategy=strategy)
        self._repository = repository
        self._strategy = strategy

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        items = payload.saved_memory or payload.memory_candidates
        if items:
            prioritized = await self._strategy.prioritize(items)
            consolidated = await self._strategy.consolidate(prioritized)
            payload.saved_memory = list(consolidated)
            context.set_state("managed_memory", [item.memory_id for item in consolidated])
        await self._repository.prune(payload.tenant)
        diagnostics = {"managed_memory": len(payload.saved_memory)}
        return TaskResult(output=payload, diagnostics=diagnostics)
