from abc import ABC, abstractmethod

from naraninyeo.domain.model.message import Message

class MessageRepository(ABC):
    @abstractmethod
    async def save(self, message: Message) -> None:
        ...

    @abstractmethod
    async def load(self, message_id: str) -> Message | None:
        ...

    @abstractmethod
    async def get_closest_by_timestamp(self, channel_id: str, timestamp: float) -> Message | None:
        ...

    @abstractmethod
    async def get_surrounding_messages(self, message: Message, before: int = 5, after: int = 5) -> list[Message]:
        ...

    @abstractmethod
    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]:
        ...
