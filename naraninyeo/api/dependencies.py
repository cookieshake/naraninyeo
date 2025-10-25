"""Default runtime dependencies for the NaraninYeo assistant."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Sequence

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from naraninyeo.api.handlers.message_handler import (
    BotResolver as MessageBotResolver,
    MessageHandler,
)
from naraninyeo.api.handlers.reply_handler import BotResolver as ReplyBotResolver
from naraninyeo.api.interfaces import (
    MemoryRepository,
    MemoryStrategy,
    MessageRepository,
    OutboundDispatcher,
    ReplyGenerator,
    WebSearchClient,
)
from naraninyeo.api.models import IncomingMessageRequest
from naraninyeo.api.router import RouterDependencies, build_message_flow
from naraninyeo.core import (
    BotReference,
    KnowledgeReference,
    MemoryItem,
    Message,
    MessageContent,
    ReplyContext,
    RetrievalPlan,
    TenantReference,
)
from naraninyeo.router.router import KafkaMessageRouter

logger = logging.getLogger(__name__)


class _InMemoryMessageRepository(MessageRepository):
    def __init__(self) -> None:
        self._messages: list[Message] = []
        self._lock = asyncio.Lock()

    async def save(self, message: Message) -> None:
        async with self._lock:
            self._messages.append(message)

    async def history(self, tenant: TenantReference, channel_id: str, *, limit: int) -> Sequence[Message]:
        async with self._lock:
            items = [
                message
                for message in self._messages
                if message.tenant == tenant and message.channel.channel_id == channel_id
            ]
        return items[-limit:] if limit > 0 else []

    async def history_after(
        self, tenant: TenantReference, channel_id: str, message_id: str, *, limit: int
    ) -> Sequence[Message]:
        async with self._lock:
            items = [
                message
                for message in self._messages
                if message.tenant == tenant and message.channel.channel_id == channel_id
            ]
        try:
            index = next(i for i, message in enumerate(items) if message.message_id == message_id)
        except StopIteration:
            return []
        start = index + 1
        end = start + limit if limit > 0 else None
        return items[start:end]

    async def search(self, tenant: TenantReference, channel_id: str, query: str, *, limit: int) -> Sequence[Message]:
        lowered = query.lower()
        async with self._lock:
            items = [
                message
                for message in self._messages
                if message.tenant == tenant
                and message.channel.channel_id == channel_id
                and lowered in message.content.text.lower()
            ]
        return items[:limit] if limit > 0 else []

    async def get(self, tenant: TenantReference, channel_id: str, message_id: str) -> Message | None:
        async with self._lock:
            for message in self._messages:
                matches = (
                    message.tenant == tenant
                    and message.channel.channel_id == channel_id
                    and message.message_id == message_id
                )
                if matches:
                    return message
        return None


class _InMemoryMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self._items: list[MemoryItem] = []
        self._lock = asyncio.Lock()

    async def save_many(self, items: Sequence[MemoryItem]) -> None:
        async with self._lock:
            self._items.extend(items)

    async def search(self, tenant: TenantReference, query: str, *, limit: int) -> Sequence[MemoryItem]:
        lowered = query.lower()
        async with self._lock:
            items = [
                item for item in self._items if item.tenant == tenant and lowered in item.content.lower()
            ]
        return items[:limit] if limit > 0 else []

    async def recent(self, tenant: TenantReference, channel_id: str, *, limit: int) -> Sequence[MemoryItem]:
        async with self._lock:
            items = [
                item for item in self._items if item.tenant == tenant and item.channel_id == channel_id
            ]
        return items[-limit:] if limit > 0 else []

    async def prune(self, tenant: TenantReference) -> None:
        async with self._lock:
            self._items = [item for item in self._items if item.tenant != tenant or not item.is_expired]


class _PassthroughMemoryStrategy(MemoryStrategy):
    async def prioritize(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]:
        return list(items)

    async def consolidate(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]:
        return list(items)


class _StaticWebSearchClient(WebSearchClient):
    async def search(self, plan: RetrievalPlan) -> Sequence[KnowledgeReference]:
        query = plan.query.strip()
        if not query:
            return []
        reference = KnowledgeReference(
            content=f"Static knowledge for '{query}'",
            source_name="static",
            timestamp=datetime.now(UTC),
        )
        return [reference][: plan.max_results]


class _EchoReplyGenerator(ReplyGenerator):
    def __init__(self, *, prefix: str = "Echo") -> None:
        self._prefix = prefix

    async def generate(self, *, context: ReplyContext) -> MessageContent:
        text = context.incoming.content.text.strip()
        display_name = context.bot.display_name if context.bot else "Assistant"
        if not text:
            return MessageContent(text=f"{self._prefix} ({display_name}): ...")
        return MessageContent(text=f"{self._prefix} ({display_name}): {text}")


class _LoggingDispatcher(OutboundDispatcher):
    def __init__(self, logger_name: str = "naraninyeo.dispatcher") -> None:
        self._logger = logging.getLogger(logger_name)

    async def dispatch(self, message: Message) -> None:
        self._logger.info("Dispatching reply %s -> %s", message.message_id, message.content.text)


async def _default_bot_resolver(_: TenantReference) -> BotReference | None:
    return None


class DependencySettings(BaseSettings):
    """Configures built-in dependency implementations."""

    model_config = SettingsConfigDict(env_prefix="NARANIN_YEO_")

    reply_prefix: str = "Echo"
    kafka_topic: str = "naraninyeo.messages"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "naraninyeo-router"
    kafka_auto_offset_reset: str = "latest"
    kafka_enable_auto_commit: bool = True


def build_router_dependencies(settings: DependencySettings | None = None) -> RouterDependencies:
    settings = settings or DependencySettings()
    message_repository: MessageRepository = _InMemoryMessageRepository()
    memory_repository: MemoryRepository = _InMemoryMemoryRepository()
    memory_strategy: MemoryStrategy = _PassthroughMemoryStrategy()
    web_client: WebSearchClient = _StaticWebSearchClient()
    reply_generator: ReplyGenerator = _EchoReplyGenerator(prefix=settings.reply_prefix)
    dispatcher: OutboundDispatcher = _LoggingDispatcher()
    return RouterDependencies(
        message_repository=message_repository,
        memory_repository=memory_repository,
        memory_strategy=memory_strategy,
        web_client=web_client,
        reply_generator=reply_generator,
        dispatcher=dispatcher,
        message_bot_resolver=_default_bot_resolver,
        reply_bot_resolver=_default_bot_resolver,
    )


def create_kafka_router(settings: DependencySettings | None = None) -> KafkaMessageRouter:
    settings = settings or DependencySettings()
    deps = build_router_dependencies(settings)
    message_flow = build_message_flow(deps)
    handler = MessageHandler(message_flow, resolve_bot=deps.message_bot_resolver)

    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_group_id,
        enable_auto_commit=settings.kafka_enable_auto_commit,
        auto_offset_reset=settings.kafka_auto_offset_reset,
    )

    def _map_request(payload: Any) -> IncomingMessageRequest:
        if isinstance(payload, IncomingMessageRequest):
            return payload
        if not isinstance(payload, dict):
            raise TypeError("Kafka payload must be a dict or IncomingMessageRequest")
        try:
            return IncomingMessageRequest.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover - defensive guard
            raise ValueError("Kafka payload could not be validated as IncomingMessageRequest") from exc

    async def _handle_error(exc: Exception, context: dict[str, Any]) -> None:
        logger.error("Kafka router failed to process record: %s (context=%s)", exc, context)

    return KafkaMessageRouter(
        consumer=consumer,
        handler=handler,
        request_mapper=_map_request,
        error_handler=_handle_error,
    )


__all__ = ["DependencySettings", "build_router_dependencies", "create_kafka_router"]

