import os
import textwrap
from datetime import UTC, datetime
from enum import Enum
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class TenancyContext(BaseModel):
    tenant_id: str = Field(min_length=1)


class Author(BaseModel):
    author_id: str = Field(min_length=1)
    author_name: str = Field(min_length=1)


class Bot(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    bot_id: str = Field(min_length=1)
    bot_name: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    created_at: datetime


class Attachment(BaseModel):
    attachment_id: str = Field(min_length=1)
    attachment_type: Literal["image", "video", "file", "audio"]
    content_type: str | None = None
    content_length: int | None = None
    url: str | None = None


class MessageContent(BaseModel):
    text: str
    attachments: list[Attachment] = Field(default_factory=list)


class Channel(BaseModel):
    channel_id: str = Field(min_length=1)
    channel_name: str


class Message(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    message_id: str = Field(min_length=1)
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime

    @computed_field  # type: ignore[misc]
    @property
    def timestamp_iso(self) -> str:
        tz = os.getenv("TZ", "Asia/Seoul")
        return self.timestamp.astimezone(tz=ZoneInfo(tz)).isoformat(timespec="minutes")

    @computed_field  # type: ignore[misc]
    @property
    def preview(self) -> str:
        snippet = textwrap.shorten(self.content.text.replace("\n", " "), width=100)
        return f"[{self.timestamp_iso}] {self.author.author_name}({self.author.author_id}): {snippet}"

    @field_validator("timestamp", mode="after")
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
    bot_id: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    kind: Literal["short_term", "long_term"] = "short_term"
    content: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None


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
    SEARCH_WEB_NEWS = "SEARCH_WEB_NEWS"
    SEARCH_WEB_BLOG = "SEARCH_WEB_BLOG"
    SEARCH_WEB_SCHOLAR = "SEARCH_WEB_SCHOLAR"
    SEARCH_WEB_ENCYCLOPEDIA = "SEARCH_WEB_ENCYCLOPEDIA"
    SEARCH_CHAT_HISTORY = "SEARCH_CHAT_HISTORY"


class PlanAction(BaseModel):
    action_type: ActionType
    description: str
    query: Optional[str] = None


class ResponsePlan(BaseModel):
    actions: list[PlanAction]
    generation_instructions: Optional[str]

    @computed_field  # type: ignore[misc]
    @property
    def summary(self) -> str:
        action_summaries = [
            f"- {action.action_type}: {textwrap.shorten(action.description, width=50)} (query: {action.query})"
            for action in self.actions
        ]
        return (
            "Actions:\n" + "\n".join(action_summaries) + (f"\nGeneration Instructions: {self.generation_instructions}")
        )


class PlanActionResult(BaseModel):
    action_result_id: str = Field(min_length=1)
    action: PlanAction
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "ABORTED"]
    priority: int = 0
    link: Optional[str] = None
    source: Optional[str] = None
    content: Optional[str] = None
    error: Optional[str] = None
    timestamp: Optional[str] = None


class EvaluationFeedback(str, Enum):
    PLAN_AGAIN = "plan_again"
    EXECUTE_AGAIN = "execute_again"
    GENERATE_AGAIN = "generate_again"
    FINALIZE = "finalize"
