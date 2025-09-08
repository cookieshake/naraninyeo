import uuid
from datetime import datetime, timedelta, timezone
from typing import override

from naraninyeo.core.contracts.memory import MemoryExtractor
from naraninyeo.core.models.memory import MemoryItem
from naraninyeo.core.models.message import Message


class RuleBasedMemoryExtractor(MemoryExtractor):
    """
    Minimal, safe extractor that only creates ephemeral short-lived memory
    when a simple heuristic is met. This avoids depending on an LLM while
    providing a pluggable spot to evolve later.
    """

    def __init__(self, ttl_hours: int = 6, max_length: int = 200):
        self.ttl_hours = ttl_hours
        self.max_length = max_length

    @override
    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]:
        text = (message.content.text or "").strip()
        # Do not extract for command-like messages
        if not text or text.startswith("/"):
            return []
        # Keep only small nuggets as ephemeral memory candidates
        if len(text) > self.max_length:
            return []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.ttl_hours)
        return [
            MemoryItem(
                memory_id=str(uuid.uuid4()),
                channel_id=message.channel.channel_id,
                kind="ephemeral",
                content=text,
                importance=1,
                created_at=now,
                expires_at=expires,
            )
        ]
