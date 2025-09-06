from datetime import datetime, timezone

from naraninyeo.domain.gateway.memory import MemoryExtractor, MemoryStore
from naraninyeo.domain.model.message import Message


class MemoryUseCase:
    def __init__(self, store: MemoryStore, extractor: MemoryExtractor):
        self.store = store
        self.extractor = extractor

    async def ingest(self, message: Message, history: list[Message]) -> None:
        items = await self.extractor.extract_from_message(message, history)
        if items:
            await self.store.put(items)

    async def recall_for_context(self, message: Message, limit: int = 5):
        now = datetime.now(timezone.utc)
        return await self.store.recall(channel_id=message.channel.channel_id, limit=limit, now=now)

