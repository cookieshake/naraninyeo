"""Interfaces used by API handlers for dependency injection."""

from __future__ import annotations

from typing import Protocol, Sequence

from naraninyeo.core import (
    KnowledgeReference,
    MemoryItem,
    Message,
    MessageContent,
    ReplyContext,
    RetrievalPlan,
    TenantReference,
)


class MessageRepository(Protocol):
    async def save(self, message: Message) -> None: ...

    async def history(
        self,
        tenant: TenantReference,
        channel_id: str,
        *,
        limit: int,
    ) -> Sequence[Message]: ...

    async def history_after(
        self,
        tenant: TenantReference,
        channel_id: str,
        message_id: str,
        *,
        limit: int,
    ) -> Sequence[Message]: ...

    async def search(
        self,
        tenant: TenantReference,
        channel_id: str,
        query: str,
        *,
        limit: int,
    ) -> Sequence[Message]: ...

    async def get(
        self,
        tenant: TenantReference,
        channel_id: str,
        message_id: str,
    ) -> Message | None: ...


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


class MemoryStrategy(Protocol):
    async def prioritize(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]: ...

    async def consolidate(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]: ...


class WebSearchClient(Protocol):
    async def search(self, plan: RetrievalPlan) -> Sequence[KnowledgeReference]: ...


class ReplyGenerator(Protocol):
    async def generate(self, *, context: ReplyContext) -> MessageContent: ...


class OutboundDispatcher(Protocol):
    async def dispatch(self, message: Message) -> None: ...


class Clock(Protocol):
    async def now(self) -> float: ...
