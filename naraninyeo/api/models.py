"""API-facing models and pipeline state definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from naraninyeo.core import (
    Attachment,
    Author,
    AuthorRole,
    BotReference,
    Channel,
    EnvironmentalContext,
    KnowledgeReference,
    MemoryItem,
    Message,
    MessageContent,
    ReplyContext,
    RetrievalPlan,
    TenantReference,
)


class AttachmentPayload(BaseModel):
    attachment_id: str = Field(default_factory=lambda: uuid4().hex)
    attachment_type: str
    content_type: str | None = None
    content_length: int | None = None
    url: str | None = None

    def to_domain(self) -> Attachment:
        return Attachment(
            attachment_id=self.attachment_id,
            attachment_type=self.attachment_type,  # type: ignore[arg-type]
            content_type=self.content_type,
            content_length=self.content_length,
            url=self.url,
        )


class AuthorPayload(BaseModel):
    author_id: str
    display_name: str
    role: AuthorRole = AuthorRole.USER
    locale: str | None = None

    def to_domain(self) -> Author:
        return Author(author_id=self.author_id, display_name=self.display_name, role=self.role, locale=self.locale)


class ChannelPayload(BaseModel):
    channel_id: str
    channel_name: str
    slug: str | None = None

    def to_domain(self) -> Channel:
        return Channel(channel_id=self.channel_id, channel_name=self.channel_name, slug=self.slug)


class IncomingMessageRequest(BaseModel):
    tenant_id: str
    bot_id: str
    channel: ChannelPayload
    author: AuthorPayload
    text: str
    attachments: list[AttachmentPayload] = Field(default_factory=list)
    timestamp: datetime | None = None
    reply_to_id: str | None = None

    def to_domain(self) -> Message:
        tenant = TenantReference(tenant_id=self.tenant_id, bot_id=self.bot_id)
        content = MessageContent(text=self.text, attachments=[att.to_domain() for att in self.attachments])
        return Message(
            tenant=tenant,
            message_id=uuid4().hex,
            channel=self.channel.to_domain(),
            author=self.author.to_domain(),
            content=content,
            timestamp=self.timestamp or datetime.utcnow(),
            reply_to_id=self.reply_to_id,
        )


class ReplyRequest(BaseModel):
    tenant_id: str
    bot_id: str
    channel_id: str
    message_id: str


class MessageResponse(BaseModel):
    message_id: str
    text: str
    timestamp: datetime

    @classmethod
    def from_domain(cls, message: Message) -> "MessageResponse":
        return cls(message_id=message.message_id, text=message.content.text, timestamp=message.timestamp)


class FlowResponse(BaseModel):
    flow: str
    message: MessageResponse | None = None
    diagnostics: list[str] = Field(default_factory=list)


class MessageProcessingState(BaseModel):
    """Mutable state shared across message-processing tasks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tenant: TenantReference
    bot: BotReference | None
    inbound: Message
    stored: Message | None = None
    history: list[Message] = Field(default_factory=list)
    related_history: list[Message] = Field(default_factory=list)
    memory_candidates: list[MemoryItem] = Field(default_factory=list)
    saved_memory: list[MemoryItem] = Field(default_factory=list)
    retrieved_memory: list[MemoryItem] = Field(default_factory=list)
    knowledge: list[KnowledgeReference] = Field(default_factory=list)
    retrieval_plan: RetrievalPlan | None = None
    reply_context: ReplyContext | None = None
    reply: Message | None = None
    environment: EnvironmentalContext | None = None

    def with_history(self, history: Sequence[Message]) -> "MessageProcessingState":
        self.history = list(history)
        return self

    def with_related_history(self, history: Sequence[Message]) -> "MessageProcessingState":
        self.related_history = list(history)
        return self

    def with_memory_candidates(self, items: Sequence[MemoryItem]) -> "MessageProcessingState":
        self.memory_candidates = list(items)
        return self

    def with_saved_memory(self, items: Sequence[MemoryItem]) -> "MessageProcessingState":
        self.saved_memory = list(items)
        return self

    def with_retrieved_memory(self, items: Sequence[MemoryItem]) -> "MessageProcessingState":
        self.retrieved_memory = list(items)
        return self

    def with_knowledge(self, knowledge: Sequence[KnowledgeReference]) -> "MessageProcessingState":
        self.knowledge = list(knowledge)
        return self

    def prepare_reply_context(self) -> ReplyContext:
        history = self.related_history or self.history
        short_memory = [m for m in self.retrieved_memory if m.kind == "short_term"]
        long_memory = [m for m in self.retrieved_memory if m.kind != "short_term"]
        environment = self.environment or EnvironmentalContext(
            timestamp=self.inbound.timestamp, timezone="UTC", metadata={}
        )
        context = ReplyContext(
            tenant=self.tenant,
            bot=self.bot,
            environment=environment,
            incoming=self.inbound,
            history=history,
            knowledge_references=self.knowledge,
            retrievals=[],
            short_term_memory=short_memory,
            long_term_memory=long_memory,
        )
        self.reply_context = context
        return context
