"""Message persistence backed by MongoDB and Qdrant."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Protocol, runtime_checkable

from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry.trace import get_tracer
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qmodels

from naraninyeo.assistant.models import Message
from naraninyeo.embeddings import TextEmbedder


@runtime_checkable
class MessageRepository(Protocol):
    async def save(self, message: Message) -> None: ...

    async def get_surrounding_messages(self, message: Message, before: int, after: int) -> list[Message]: ...

    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]: ...


class MongoQdrantMessageRepository:
    def __init__(
        self,
        mongodb: AsyncIOMotorDatabase,
        qdrant_client: AsyncQdrantClient,
        text_embedder: TextEmbedder,
    ) -> None:
        self._collection = mongodb["messages"]
        self._qdrant_client = qdrant_client
        self._qdrant_collection = "naraninyeo-messages"
        self._text_embedder = text_embedder

    @get_tracer(__name__).start_as_current_span("save message")
    async def save(self, message: Message) -> None:
        tasks = [
            self._collection.update_one(
                {"message_id": message.message_id},
                {"$set": message.model_dump()},
                upsert=True,
            ),
            self._qdrant_client.upsert(
                collection_name=self._qdrant_collection,
                points=[
                    qmodels.PointStruct(
                        id=self._str_to_64bit(message.message_id),
                        vector=(await self._text_embedder.embed([message.content.text]))[0],
                        payload={
                            "message_id": message.message_id,
                            "channel_id": message.channel.channel_id,
                            "text": message.content.text,
                            "timestamp": message.timestamp.isoformat(),
                            "author": message.author.author_name,
                        },
                    )
                ],
            ),
        ]
        await asyncio.gather(*tasks)

    @get_tracer(__name__).start_as_current_span("load message")
    async def load(self, message_id: str) -> Message | None:
        document = await self._collection.find_one({"message_id": message_id})
        return Message.model_validate(document) if document else None

    @get_tracer(__name__).start_as_current_span("get closest message by timestamp")
    async def get_closest_by_timestamp(self, channel_id: str, timestamp: float) -> Message | None:
        document = await self._collection.find_one(
            {"channel.channel_id": channel_id, "timestamp": {"$lte": timestamp}},
            sort=[("timestamp", -1)],
        )
        return Message.model_validate(document) if document else None

    @get_tracer(__name__).start_as_current_span("get surrounding messages")
    async def get_surrounding_messages(self, message: Message, before: int = 5, after: int = 5) -> list[Message]:
        tasks = []
        if before > 0:
            tasks.append(
                self._collection.find(
                    {
                        "channel.channel_id": message.channel.channel_id,
                        "message_id": {"$lt": message.message_id},
                    }
                )
                .sort("timestamp", -1)
                .limit(before)
                .to_list(length=before)
            )
        if after > 0:
            tasks.append(
                self._collection.find(
                    {
                        "channel.channel_id": message.channel.channel_id,
                        "message_id": {"$gt": message.message_id},
                    }
                )
                .sort("timestamp", 1)
                .limit(after)
                .to_list(length=after)
            )

        results = await asyncio.gather(*tasks)
        messages = [message]
        for result in results:
            messages.extend(Message.model_validate(doc) for doc in result if doc)
        messages.sort(key=lambda m: m.timestamp)
        return messages

    @get_tracer(__name__).start_as_current_span("search similar messages")
    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]:
        qdrant_result = await self._qdrant_client.query_points(
            collection_name=self._qdrant_collection,
            query=(await self._text_embedder.embed([keyword]))[0],
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="channel_id",
                        match=qmodels.MatchValue(value=channel_id),
                    )
                ]
            ),
            limit=limit,
        )
        message_ids = [point.payload["message_id"] for point in qdrant_result.points if point.payload is not None]
        loaded = await asyncio.gather(*(self.load(mid) for mid in message_ids))
        return [msg for msg in loaded if msg is not None]

    def _str_to_64bit(self, value: str) -> int:
        return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)
