from datetime import datetime
from typing import Protocol, Sequence

from naraninyeo.core.models import Bot, MemoryItem, Message, PlanAction, PlanActionResult, TenancyContext


class MessageRepository(Protocol):
    async def upsert(self, tctx: TenancyContext, message: Message) -> None: ...
    async def get_channel_messages_before(
        self,
        tctx: TenancyContext,
        channel_id: str,
        before_message_id: str,
        limit: int = 10
    ) -> Sequence[Message]: ...
    async def get_channel_messages_after(
        self,
        tctx: TenancyContext,
        channel_id: str,
        after_message_id: str,
        limit: int = 10
    ) -> Sequence[Message]: ...
    async def text_search_messages(
        self,
        tctx: TenancyContext,
        channel_id: str,
        query: str,
        limit: int = 10
    ) -> Sequence[Message]: ...

class BotRepository(Protocol):
    async def get(self, tctx: TenancyContext, bot_id: str) -> bool: ...
    async def list_all(self, tctx: TenancyContext) -> Sequence[Bot]: ...
    async def create(self, tctx: TenancyContext, bot: Bot) -> None: ...

class MemoryRepository(Protocol):
    async def upsert_many(self, tctx: TenancyContext, memory_items: Sequence[MemoryItem]) -> None: ...
    async def delete_many(self, tctx: TenancyContext, memory_item_ids: Sequence[str]) -> int: ...
    async def delete_expired(self, tctx: TenancyContext, current_time: datetime) -> int: ...
    async def get_channel_memory_items(
        self,
        tctx: TenancyContext,
        bot_id: str,
        channel_id: str,
        limit: int = 100
    ) -> Sequence[MemoryItem]: ...

class Clock(Protocol):
    def now(self) -> datetime: ...

class PlanActionExecutor(Protocol):
    async def execute_actions(
        self,
        actions: list[PlanAction]
    ) -> list[PlanActionResult]: ...

class IdGenerator(Protocol):
    def generate_id(self) -> str: ...

class TextEmbedder(Protocol):
    async def embed_docs(self, docs: list[str]) -> list[list[float]]: ...
    async def embed_queries(self, queries: list[str]) -> list[list[float]]: ...

