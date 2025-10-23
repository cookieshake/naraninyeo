"""Task that converts messages into memory candidates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import MemoryImportance, MemoryItem
from naraninyeo.core.flow import FlowContext
from naraninyeo.core.task import TaskBase, TaskResult


class MessagesToMemoryTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, *, short_term_ttl_minutes: int = 60) -> None:
        super().__init__(short_term_ttl_minutes=short_term_ttl_minutes)
        self._ttl_minutes = short_term_ttl_minutes

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        message = payload.inbound
        text = message.content.text.strip()
        candidates: list[MemoryItem] = []
        if not text:
            return TaskResult(output=payload, diagnostics={"created_memory": 0})

        importance = MemoryImportance.MEDIUM if len(text) > 100 else MemoryImportance.LOW
        expires_at = None
        if self._ttl_minutes > 0:
            expires_at = datetime.now(UTC) + timedelta(minutes=self._ttl_minutes)
        candidates.append(
            MemoryItem(
                memory_id=uuid4().hex,
                tenant=message.tenant,
                channel_id=message.channel.channel_id,
                kind="short_term",
                content=text,
                importance=importance,
                created_at=message.timestamp,
                expires_at=expires_at,
            )
        )
        payload.memory_candidates = candidates
        context.set_state("memory_candidates", [m.memory_id for m in candidates])
        return TaskResult(output=payload, diagnostics={"created_memory": len(candidates)})
