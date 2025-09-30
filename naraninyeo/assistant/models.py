"""Shared data structures used across the assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


class Author(BaseModel):
    author_id: str
    author_name: str


class Attachment(BaseModel):
    attachment_id: str
    attachment_type: Literal["image", "video", "file"]
    content_type: Optional[str] = None
    content_length: Optional[int] = None


class MessageContent(BaseModel):
    text: str
    attachments: list[Attachment] = Field(default_factory=list)


class Channel(BaseModel):
    channel_id: str
    channel_name: str


class Message(BaseModel):
    message_id: str
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime

    @property
    def timestamp_str(self) -> str:
        return self.timestamp.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def text_repr(self) -> str:
        preview = self.content.text[:200]
        return f"{self.timestamp_str} {self.author.author_name} : {preview}"


class MemoryItem(BaseModel):
    memory_id: str
    channel_id: str
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    content: str
    importance: int = 1
    created_at: datetime
    expires_at: Optional[datetime] = None


@dataclass
class EnvironmentalContext:
    timestamp: datetime
    location: str


@dataclass
class KnowledgeReference:
    content: str
    source_name: str
    timestamp: Optional[datetime] = None


@dataclass
class ReplyContext:
    environment: EnvironmentalContext
    last_message: Message
    latest_history: list[Message]
    knowledge_references: list[KnowledgeReference]
    processing_logs: list[str]
    short_term_memory: list[MemoryItem] | None = None


class RetrievalPlan(BaseModel):
    search_type: str
    query: str


@dataclass
class ChatHistoryRef:
    value: list[Message]

    @property
    def as_text(self) -> str:
        return "\n".join([m.text_repr for m in self.value])


@dataclass
class UrlRef:
    value: str

    @property
    def as_text(self) -> str:
        return self.value


class RetrievalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RetrievalStatusReason(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class RetrievalResult:
    plan: RetrievalPlan
    result_id: str
    content: str
    ref: ChatHistoryRef | UrlRef
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    source_name: str
    source_timestamp: Optional[datetime]
