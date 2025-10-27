from datetime import datetime
from typing import Protocol, Sequence

from naraninyeo.core import (
    KnowledgeReference,
    MemoryItem,
    Message,
    MessageContent,
    ReplyContext,
    RetrievalPlan
)
from naraninyeo.core.models import Bot, Channel

class ChannelRepository(Protocol):
    async def exists(self, channel_id: str) -> bool: ...
    async def save(self, channel: Channel) -> None: ...

class MessageRepository(Protocol):
    async def save(self, message: Message) -> None: ...

class BotRepository(Protocol):
    async def exists(self, bot_id: str) -> bool: ...
    async def save(self, bot: Bot) -> None: ...

class MemoryRepository(Protocol):
    async def save_many(self, items: Sequence[MemoryItem]) -> None: ...

    async def search(
        self,
        tenant: TenantReference,
        query: str,
        *,
        limit: int,
    ) -> Sequence[MemoryItem]: ...

    async def recent(
        self,
        tenant: TenantReference,
        channel_id: str,
        *,
        limit: int,
    ) -> Sequence[MemoryItem]: ...

    async def prune(self, tenant: TenantReference) -> None: ...

class Clock(Protocol):
    def now(self) -> datetime: ...
