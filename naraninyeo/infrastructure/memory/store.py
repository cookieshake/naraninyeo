from datetime import datetime
from typing import override

from motor.motor_asyncio import AsyncIOMotorDatabase

from naraninyeo.domain.gateway.memory import MemoryStore
from naraninyeo.domain.model.memory import MemoryItem


class MongoMemoryStore(MemoryStore):
    def __init__(self, mongodb: AsyncIOMotorDatabase):
        self._db = mongodb
        self._collection = mongodb["memory"]
        self._index_ready = False

    @override
    async def put(self, items: list[MemoryItem]) -> None:
        if not items:
            return
        # Ensure TTL index exists (expire at document's expires_at)
        if not self._index_ready:
            try:
                await self._collection.create_index("expires_at", expireAfterSeconds=0)
            except Exception:
                pass
            self._index_ready = True
        ops = []
        for item in items:
            ops.append(
                self._collection.update_one(
                    {"memory_id": item.memory_id}, {"$set": item.model_dump()}, upsert=True
                )
            )
        # Fire sequentially to avoid overwhelming small test DB; could be optimized
        for op in ops:
            await op

    @override
    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]:
        cursor = (
            self._collection.find(
                {
                    "channel_id": channel_id,
                    "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
                }
            )
            .sort([("importance", -1), ("created_at", -1)])
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [MemoryItem.model_validate(doc) for doc in docs]

    @override
    async def evict_expired(self, *, now: datetime) -> int:
        result = await self._collection.delete_many({"expires_at": {"$lte": now}})
        return int(result.deleted_count)
