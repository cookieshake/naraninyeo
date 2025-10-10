"""Utilities for building reply contexts from repositories and memory."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from naraninyeo.assistant.memory_management import MemoryStore
from naraninyeo.assistant.message_repository import MessageRepository
from naraninyeo.assistant.models import (
    EnvironmentalContext,
    MemoryItem,
    Message,
    ReplyContext,
)
from naraninyeo.settings import Settings


class ReplyContextBuilder:
    """Collect recent messages and short-term memory to feed the reply pipeline."""

    def __init__(
        self,
        message_repository: MessageRepository,
        memory_store: MemoryStore,
        settings: Settings,
    ) -> None:
        self._messages = message_repository
        self._memory = memory_store
        self._settings = settings

    async def build(
        self,
        message: Message,
        *,
        history: list[Message] | None = None,
        short_term_memory: list[MemoryItem] | None = None,
    ) -> ReplyContext:
        resolved_history = (
            history
            if history is not None
            else await self._messages.get_surrounding_messages(
                message=message,
                before=self._settings.HISTORY_LIMIT,
                after=0,
            )
        )
        current_time = datetime.now(tz=ZoneInfo(self._settings.TIMEZONE))
        resolved_memory = (
            short_term_memory
            if short_term_memory is not None
            else await self._memory.recall(
                channel_id=message.channel.channel_id,
                limit=5,
                now=current_time,
            )
        )
        environment = EnvironmentalContext(
            timestamp=current_time,
            location=self._settings.LOCATION,
        )
        return ReplyContext(
            environment=environment,
            last_message=message,
            latest_history=resolved_history,
            knowledge_references=[],
            processing_logs=[],
            short_term_memory=resolved_memory,
        )
