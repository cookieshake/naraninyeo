import os
from datetime import UTC, datetime
from enum import Enum
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, computed_field, field_validator


class Tenant(BaseModel):
    tenant_id: str = Field(min_length=1)

class Author(BaseModel):
    author_id: str = Field(min_length=1)
    author_name: str = Field(min_length=1)

class Bot(Author):
    tenant: Tenant

class Attachment(BaseModel):
    attachment_id: str = Field(min_length=1)
    attachment_type: Literal["image", "video", "file", "audio"]
    content_type: str | None = None
    content_length: int | None = None
    url: str | None = None

class MessageContent(BaseModel):
    text: str = Field(min_length=1)
    attachments: list[Attachment] = Field(default_factory=list)

class Channel(BaseModel):
    channel_id: str = Field(min_length=1)
    channel_name: str

class Message(BaseModel):
    tenant: Tenant
    message_id: str = Field(min_length=1)
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[misc]
    @property
    def timestamp_iso(self) -> str:
        tz = os.getenv("TZ", "UTC")
        return self.timestamp.astimezone(tz=ZoneInfo(tz)).isoformat()

    @computed_field  # type: ignore[misc]
    @property
    def preview(self) -> str:
        snippet = self.content.text[:200]
        return f"[{self.timestamp_iso}] {self.author.author_name}({self.author.author_id}): {snippet}"

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

class BotMessage(BaseModel):
    bot: Bot
    channel: Channel
    content: MessageContent

class MemoryItem(BaseModel):
    memory_id: str = Field(min_length=1)
    bot: Bot
    kind: Literal["short_term", "long_term"] = "short_term"
    content: str = Field(min_length=1)
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None

    @computed_field  # type: ignore[misc]
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


class EnvironmentalContext(BaseModel):
    timestamp: datetime
    timezone: str
    locale: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeReference(BaseModel):
    content: str
    source_name: str
    url: str | None = None
    timestamp: datetime | None = None

class ActionType(str, Enum):
    SEARCH_WEB_GENERAL = "SEARCH_WEB_GENERAL"
    SEARCH_WEB_NEWS = "SEARCH_WEB_NEWS"
    SEARCH_WEB_BLOG = "SEARCH_WEB_BLOG"
    SEARCH_WEB_SCHOLAR = "SEARCH_WEB_SCHOLAR"
    SEARCH_CHAT_HISTORY = "SEARCH_CHAT_HISTORY"

class PlanAction(BaseModel):
    action_type: ActionType
    description: str
    query: Optional[str] = None

class ResponsePlan(BaseModel):
    actions: list[PlanAction]
    generation_instructions: Optional[str]

class PlanActionResult(BaseModel):
    action: PlanAction
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "ABORTED"]
    result: Optional[str] = None
    error: Optional[str] = None
