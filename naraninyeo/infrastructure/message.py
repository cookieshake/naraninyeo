import asyncio
import hashlib
from typing import override

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from qdrant_client import AsyncQdrantClient, models as qmodels

from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.model.message import Message
from naraninyeo.infrastructure.embedding import TextEmbedder



class MongoQdrantMessageRepository(MessageRepository):
    def __init__(
        self,
        mongodb: AsyncIOMotorDatabase,
        qdrant_client: AsyncQdrantClient,
        text_embedder: TextEmbedder
    ):
        self._db = mongodb
        self._collection = mongodb["messages"]
        self._qdrant_client = qdrant_client
        self._qdrant_collection = "naraninyeo-messages"
        self._text_embedder = text_embedder

    @override
    async def save(self, message: Message) -> None:
        tasks = []
        tasks.append(self._collection.update_one(
            {"message_id": message.message_id},
            {"$set": message.model_dump()},
            upsert=True
        ))
        tasks.append(self._qdrant_client.upsert(
            collection_name=self._qdrant_collection,
            points=[
                qmodels.PointStruct(
                    id=self._str_to_64bit(message.message_id),
                    vector=(await self._text_embedder.embed([message.content.text]))[0],
                    payload={
                        "message_id": message.message_id,
                        "room": message.channel.channel_id,
                        "text": message.content.text,
                        "timestamp": message.timestamp.isoformat(),
                        "author": message.author.author_name,
                    }
                )
            ]
        ))
        await asyncio.gather(*tasks)

    @override
    async def load(self, message_id: str) -> Message | None:
        document = await self._collection.find_one({"message_id": message_id})
        if document:
            return Message.model_validate(document)
        return None

    @override
    async def get_closest_by_timestamp(self, channel_id: str, timestamp: float) -> Message | None:
        document = await self._collection.find_one({
            "channel_id": channel_id,
            "timestamp": {"$lte": timestamp}
        }, sort=[("timestamp", -1)])
        if document:
            return Message.model_validate(document)
        return None
    
    @override
    async def get_surrounding_messages(self, message: Message, before: int = 5, after: int = 5) -> list[Message]:
        tasks = []
        if before > 0:
            tasks.append(
                self._collection.find({
                    "channel.channel_id": message.channel.channel_id,
                    "message_id": {"$lt": message.message_id}
                })
                .sort("timestamp", -1)
                .limit(before)
                .to_list(length=before)
            )
        if after > 0:
            tasks.append(
                self._collection.find({
                    "channel.channel_id": message.channel.channel_id,
                    "message_id": {"$gt": message.message_id}
                })
                .sort("timestamp", 1)
                .limit(after)
                .to_list(length=after)
            )

        results = await asyncio.gather(*tasks)
        messages = [message]
        for result in results:
            result = [Message.model_validate(doc) for doc in result if doc]
            messages.extend(result)
        messages.sort(key=lambda m: m.timestamp)
        return messages

    @override
    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]:
        result = await self._qdrant_client.query_points(
            collection_name=self._qdrant_collection,
            query_vector=(await self._text_embedder.embed([keyword]))[0],
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(key="channel_id", match=qmodels.MatchValue(value=channel_id))
                ]
            ),
            limit=limit
        )
        message_ids = [point.payload["message_id"] for point in result.points if point.payload is not None]
        loaded_messages = await asyncio.gather(*[self.load(message_id) for message_id in message_ids])
        return [msg for msg in loaded_messages if msg is not None]
    
    def _str_to_64bit(self, s: str) -> int:
        return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], 16)