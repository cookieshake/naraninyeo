import asyncio

from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.model.message import Message


class MessageUseCase:
    def __init__(self, message_repository: MessageRepository):
        self.message_repository = message_repository

    async def reply_needed(self, message: Message) -> bool:
        if message.content.text.startswith("/"):
            return True
        return False

    async def save_message(self, message: Message) -> None:
        await self.message_repository.save(message)

    async def get_recent_messages(self, message: Message, limit: int) -> list[Message]:
        return await self.message_repository.get_surrounding_messages(message=message, before=limit, after=0)

    async def get_similar_messages(self, message: Message, limit: int = 3) -> list[list[Message]]:
        similar_messages = await self.message_repository.search_similar_messages(
            channel_id=message.channel.channel_id, keyword=message.content.text, limit=limit
        )
        blocks = [
            asyncio.create_task(self.message_repository.get_surrounding_messages(message=msg, before=3, after=3))
            for msg in similar_messages
        ]
        results = await asyncio.gather(*blocks, return_exceptions=True)
        results = [b for b in results if not isinstance(b, Exception)]
        return results
