from datetime import datetime
from zoneinfo import ZoneInfo

from naraninyeo.domain.model.reply import EnvironmentalContext, ReplyContext
from naraninyeo.domain.model.message import Message
from naraninyeo.domain.usecase.memory import MemoryUseCase
from naraninyeo.domain.usecase.message import MessageUseCase
from naraninyeo.infrastructure.settings import Settings


class ReplyContextBuilder:
    def __init__(self, message_use_case: MessageUseCase, memory_use_case: MemoryUseCase, settings: Settings):
        self.message_use_case = message_use_case
        self.memory_use_case = memory_use_case
        self.settings = settings

    async def build(self, message: Message) -> ReplyContext:
        history = await self.message_use_case.get_recent_messages(message, limit=self.settings.HISTORY_LIMIT)
        short_term_memory = await self.memory_use_case.recall_for_context(message, limit=5)
        env = EnvironmentalContext(
            timestamp=datetime.now(tz=ZoneInfo(self.settings.TIMEZONE)),
            location=self.settings.LOCATION,
        )
        return ReplyContext(
            environment=env,
            last_message=message,
            latest_history=history,
            knowledge_references=[],
            processing_logs=[],
            short_term_memory=short_term_memory,
        )

