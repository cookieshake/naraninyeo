"""Kafka consumer router that forwards messages to the assistant flows."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer

from naraninyeo.api.handlers.message_handler import MessageHandler
from naraninyeo.api.models import IncomingMessageRequest

logger = logging.getLogger(__name__)


RequestMapper = Callable[[Any], IncomingMessageRequest]
ErrorHandler = Callable[[Exception, dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class KafkaRouterConfig:
    topic: str
    bootstrap_servers: str
    group_id: str
    enable_auto_commit: bool = True
    auto_offset_reset: str = "latest"


class KafkaMessageRouter:
    def __init__(
        self,
        *,
        consumer: AIOKafkaConsumer,
        handler: MessageHandler,
        request_mapper: RequestMapper,
        error_handler: ErrorHandler | None = None,
    ) -> None:
        self._consumer = consumer
        self._handler = handler
        self._request_mapper = request_mapper
        self._error_handler = error_handler
        self._running = asyncio.Event()

    async def start(self) -> None:
        await self._consumer.start()
        self._running.set()
        logger.info("Kafka consumer started for topics %s", self._consumer.subscription())
        try:
            async for record in self._consumer:
                await self._handle_record(record)
        finally:
            await self._consumer.stop()
            self._running.clear()
            logger.info("Kafka consumer stopped")

    async def _handle_record(self, record: Any) -> None:
        try:
            payload = self._deserialize(record.value)
            request = self._request_mapper(payload)
            await self._handler.handle(request)
        except Exception as exc:  # pragma: no cover - defensive log path
            logger.exception("Failed to process Kafka record: %s", exc)
            if self._error_handler:
                await self._error_handler(exc, {"record": record})

    @staticmethod
    def _deserialize(value: bytes | str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, bytes):
            return json.loads(value.decode("utf-8"))
        if isinstance(value, str):
            return json.loads(value)
        raise TypeError(f"unsupported kafka payload type: {type(value)}")

    async def stop(self) -> None:
        if self._running.is_set():
            await self._consumer.stop()
            self._running.clear()
