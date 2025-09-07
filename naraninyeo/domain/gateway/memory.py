from abc import ABC, abstractmethod
from datetime import datetime

from naraninyeo.domain.model.memory import MemoryItem
from naraninyeo.domain.model.message import Message


class MemoryStore(ABC):
    @abstractmethod
    async def put(self, items: list[MemoryItem]) -> None: ...

    @abstractmethod
    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]: ...

    @abstractmethod
    async def evict_expired(self, *, now: datetime) -> int: ...


class MemoryExtractor(ABC):
    @abstractmethod
    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]: ...
