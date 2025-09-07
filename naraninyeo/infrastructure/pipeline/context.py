from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from naraninyeo.domain.gateway.memory import MemoryStore
from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import EnvironmentalContext, ReplyContext
from naraninyeo.infrastructure.settings import Settings


class ReplyContextBuilder:
    """Builds a ReplyContext using pipeline-level gateways.

    This replaces the domain-layer builder to keep logic colocated with the
    pipeline and its steps.
    """

    def __init__(
        self,
        message_repository: MessageRepository,
        memory_store: MemoryStore,
        settings: Settings,
    ) -> None:
        self._messages = message_repository
        self._memory = memory_store
        self._settings = settings

    async def build(self, message: Message) -> ReplyContext:
        # Fetch recent history (up to HISTORY_LIMIT before the message)
        history = await self._messages.get_surrounding_messages(
            message=message, before=self._settings.HISTORY_LIMIT, after=0
        )

        # Recall short-term memory for this channel
        short_term_memory = await self._memory.recall(
            channel_id=message.channel.channel_id,
            limit=5,
            now=datetime.now(tz=ZoneInfo(self._settings.TIMEZONE)),
        )

        env = EnvironmentalContext(
            timestamp=datetime.now(tz=ZoneInfo(self._settings.TIMEZONE)),
            location=self._settings.LOCATION,
        )
        return ReplyContext(
            environment=env,
            last_message=message,
            latest_history=history,
            knowledge_references=[],
            processing_logs=[],
            short_term_memory=short_term_memory,
        )

