from __future__ import annotations

from abc import ABC, abstractmethod

from naraninyeo.core.models.memory import MemoryItem
from naraninyeo.core.models.message import Message


class MemoryStore(ABC):
    @abstractmethod
    async def put(self, items: list[MemoryItem]) -> None: ...

    @abstractmethod
    async def recall(self, *, channel_id: str, limit: int, now) -> list[MemoryItem]: ...

    @abstractmethod
    async def evict_expired(self, *, now) -> int: ...


class MemoryExtractor(ABC):
    @abstractmethod
    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]: ...

