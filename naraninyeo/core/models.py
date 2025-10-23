"""Domain models shared across flows and tasks."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Iterable, Literal

from pydantic import BaseModel, Field, computed_field, field_validator


class TenantReference(BaseModel):
    """Identifies the tenant and bot handling a conversation."""

    tenant_id: str = Field(min_length=1)
    bot_id: str = Field(min_length=1)

    def as_key(self) -> str:
        return f"{self.tenant_id}:{self.bot_id}"


class BotReference(BaseModel):
    """Describes a bot that belongs to a tenant."""

    tenant: TenantReference
    display_name: str = Field(min_length=1)
    description: str | None = None
    model_hint: str | None = None


class AuthorRole(str, Enum):
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"


class Author(BaseModel):
    author_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: AuthorRole = AuthorRole.USER
    locale: str | None = None


class Attachment(BaseModel):
    attachment_id: str = Field(min_length=1)
    attachment_type: Literal["image", "video", "file", "link"]
    content_type: str | None = None
    content_length: int | None = None
    url: str | None = None


class MessageContent(BaseModel):
    text: str = Field(min_length=1)
    attachments: list[Attachment] = Field(default_factory=list)


class Channel(BaseModel):
    channel_id: str = Field(min_length=1)
    channel_name: str
    slug: str | None = None


class Message(BaseModel):
    """Represents an inbound or outbound conversation message."""

    tenant: TenantReference
    message_id: str = Field(min_length=1)
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reply_to_id: str | None = None

    @computed_field  # type: ignore[misc]
    @property
    def timestamp_iso(self) -> str:
        return self.timestamp.astimezone(UTC).isoformat()

    @computed_field  # type: ignore[misc]
    @property
    def preview(self) -> str:
        snippet = self.content.text[:200]
        return f"[{self.timestamp_iso}] {self.author.display_name}: {snippet}"

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class MemoryImportance(int, Enum):
    LOW = 1
    MEDIUM = 5
    HIGH = 9


class MemoryItem(BaseModel):
    """Represents knowledge derived from conversations."""

    memory_id: str = Field(min_length=1)
    tenant: TenantReference
    channel_id: str = Field(min_length=1)
    kind: Literal["short_term", "long_term", "persona", "task"] = "short_term"
    content: str = Field(min_length=1)
    importance: MemoryImportance = MemoryImportance.LOW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

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


class RetrievalPlan(BaseModel):
    search_type: Literal["web", "memory", "history", "hybrid"]
    query: str
    max_results: int = Field(default=5, ge=1)


class RetrievalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class RetrievalStatusReason(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    EMPTY = "EMPTY"


class RetrievalResult(BaseModel):
    plan: RetrievalPlan
    result_id: str
    content: str
    references: list[KnowledgeReference] = Field(default_factory=list)
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    source_name: str
    source_timestamp: datetime | None = None


class ReplyContext(BaseModel):
    tenant: TenantReference
    bot: BotReference | None
    environment: EnvironmentalContext
    incoming: Message
    history: list[Message] = Field(default_factory=list)
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    retrievals: list[RetrievalResult] = Field(default_factory=list)
    short_term_memory: list[MemoryItem] | None = None
    long_term_memory: list[MemoryItem] | None = None

    def iter_all_memory(self) -> Iterable[MemoryItem]:
        for item in self.short_term_memory or []:
            yield item
        for item in self.long_term_memory or []:
            yield item
