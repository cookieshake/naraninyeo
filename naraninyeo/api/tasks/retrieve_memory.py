"""Task that retrieves memory items relevant to the conversation."""

from __future__ import annotations

from naraninyeo.api.interfaces import MemoryRepository
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class RetrieveMemoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, repository: MemoryRepository, *, limit: int = 20) -> None:
        super().__init__(repository=repository, limit=limit)
        self._repository = repository
        self._limit = limit

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        query = payload.inbound.content.text
        channel_id = payload.inbound.channel.channel_id
        retrieved = await self._repository.search(payload.tenant, query, limit=self._limit)
        recent = await self._repository.recent(payload.tenant, channel_id, limit=5)
        seen: set[str] = set()
        merged = []
        for item in [*retrieved, *recent]:
            if item.memory_id in seen:
                continue
            seen.add(item.memory_id)
            merged.append(item)
        payload.retrieved_memory = merged
        context.set_state("retrieved_memory", [item.memory_id for item in merged])
        return TaskResult(output=payload, diagnostics={"retrieved_memory": len(merged)})
