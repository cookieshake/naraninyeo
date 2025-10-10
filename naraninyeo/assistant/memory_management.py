"""Memory related helpers backed by MongoDB and the LLM extractor."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol, runtime_checkable

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from pydantic_ai.output import NativeOutput

from naraninyeo.assistant.llm_toolkit import LLMTool, LLMToolFactory
from naraninyeo.assistant.models import MemoryItem, Message
from naraninyeo.assistant.prompts import MemoryPrompt
from naraninyeo.settings import Settings


@runtime_checkable
class MemoryStore(Protocol):
    async def put(self, items: list[MemoryItem]) -> None: ...

    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]: ...


class MongoMemoryStore:
    def __init__(self, mongodb: AsyncIOMotorDatabase):
        self._collection = mongodb["memory"]
        self._index_ready = False

    async def put(self, items: list[MemoryItem]) -> None:
        if not items:
            return
        if not self._index_ready:
            try:
                # TTL 인덱스를 한 번만 만들어 만료된 기억이 자동으로 정리되게 한다.
                await self._collection.create_index("expires_at", expireAfterSeconds=0)
            except Exception:
                pass
            self._index_ready = True
        for item in items:
            await self._collection.update_one(
                {"memory_id": item.memory_id},
                {"$set": item.model_dump()},
                upsert=True,
            )

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

    async def evict_expired(self, *, now: datetime) -> int:
        result = await self._collection.delete_many({"expires_at": {"$lte": now}})
        return int(result.deleted_count)


class LLMExtractionItem(BaseModel):
    content: str = Field(min_length=1, max_length=200)
    importance: int = Field(default=1, ge=1, le=5)
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    ttl_hours: int | None = Field(default=None, ge=1, le=48)


class ConversationMemoryExtractor:
    def __init__(self, settings: Settings, llm_factory: LLMToolFactory):
        self.settings = settings
        self.tool: LLMTool[MemoryPrompt, list[LLMExtractionItem]] = llm_factory.memory_tool(
            output_type=NativeOutput(list[LLMExtractionItem])
        )

    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]:
        if (message.content.text or "").strip().startswith("/"):
            return []

        prompt = MemoryPrompt(message=message, history=history)

        try:
            # LLM으로부터 기억 후보를 추출할 때 예외가 나면 조용히 빈 결과를 반환한다.
            items = await self.tool.run(prompt)
        except Exception:
            return []

        now = datetime.now(timezone.utc)
        output: list[MemoryItem] = []
        for item in (items or [])[:3]:
            ttl = item.ttl_hours if item.ttl_hours is not None else self.settings.MEMORY_TTL_HOURS
            expires = now + timedelta(hours=int(ttl))
            output.append(
                MemoryItem(
                    memory_id=str(uuid.uuid4()),
                    channel_id=message.channel.channel_id,
                    kind=item.kind,
                    content=item.content.strip(),
                    importance=item.importance,
                    created_at=now,
                    expires_at=expires,
                )
            )
        return output
