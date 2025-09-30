from __future__ import annotations

import logging

from naraninyeo.plugins import AppRegistry, ChatMiddleware
from naraninyeo.settings import Settings


class LoggingMiddleware(ChatMiddleware):
    def __init__(self, settings: Settings) -> None:  # noqa: D401
        self._enabled = True
        self._prefix = "[chat]"

    async def before_handle(self, message):
        if self._enabled:
            logging.info(f"{self._prefix} incoming: {message.text_repr}")

    async def on_reply(self, reply):
        if self._enabled:
            logging.info(f"{self._prefix} reply: {reply.text_repr}")


def register(registry: AppRegistry) -> None:
    registry.register_chat_middleware(lambda settings: LoggingMiddleware(settings))
