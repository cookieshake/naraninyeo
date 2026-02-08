from datetime import datetime
from typing import List, Literal, Optional, Protocol, Sequence, runtime_checkable

from naraninyeo.core.models import (
    Bot,
    FetchedDocument,
    MemoryItem,
    Message,
    NewsSearchResult,
    PriceInfo,
    SearchResult,
    TenancyContext,
    Ticker,
)


@runtime_checkable
class MessageRepository(Protocol):
    async def upsert(self, tctx: TenancyContext, message: Message) -> None: ...
    async def get_channel_messages_before(
        self, tctx: TenancyContext, channel_id: str, before_message_id: str, limit: int = 10
    ) -> Sequence[Message]: ...
    async def get_channel_messages_after(
        self, tctx: TenancyContext, channel_id: str, after_message_id: str, limit: int = 10
    ) -> Sequence[Message]: ...
    async def text_search_messages(
        self, tctx: TenancyContext, channel_id: str, query: str, limit: int = 10
    ) -> Sequence[Message]: ...


@runtime_checkable
class BotRepository(Protocol):
    async def get(self, tctx: TenancyContext, bot_id: str) -> Bot | None: ...
    async def list_all(self, tctx: TenancyContext) -> Sequence[Bot]: ...
    async def create(self, tctx: TenancyContext, bot: Bot) -> None: ...


@runtime_checkable
class MemoryRepository(Protocol):
    async def upsert_many(self, tctx: TenancyContext, memory_items: Sequence[MemoryItem]) -> None: ...
    async def delete_many(self, tctx: TenancyContext, memory_item_ids: Sequence[str]) -> int: ...
    async def delete_expired(self, tctx: TenancyContext, current_time: datetime) -> int: ...
    async def get_channel_memory_items(
        self, tctx: TenancyContext, bot_id: str, channel_id: str, limit: int = 100
    ) -> Sequence[MemoryItem]: ...
    async def get_latest_memory_update_ts(
        self, tctx: TenancyContext, bot_id: str, channel_id: str
    ) -> datetime | None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class IdGenerator(Protocol):
    def generate_id(self) -> str: ...


@runtime_checkable
class TextEmbedder(Protocol):
    async def embed_docs(self, docs: list[str]) -> list[list[float]]: ...
    async def embed_queries(self, queries: list[str]) -> list[list[float]]: ...


@runtime_checkable
class NaverSearch(Protocol):
    async def search(
        self,
        search_type: Literal["general", "news", "blog", "document", "encyclopedia"],
        query: str,
        limit: int,
        order: Optional[Literal["sim", "date"]] = None,
    ) -> List[SearchResult]: ...


@runtime_checkable
class FinanceSearch(Protocol):
    async def search_symbol(self, query: str) -> Ticker | None: ...
    async def search_news(self, symbol: Ticker) -> list[NewsSearchResult]: ...
    async def search_current_price(self, symbol: Ticker) -> str | None: ...
    async def get_short_term_price(self, symbol: Ticker) -> list[PriceInfo]: ...
    async def get_long_term_price(self, symbol: Ticker) -> list[PriceInfo]: ...


@runtime_checkable
class WebDocumentFetch(Protocol):
    async def fetch_document(self, url: str) -> FetchedDocument: ...
