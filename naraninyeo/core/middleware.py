from __future__ import annotations

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import ReplyContext


class ChatMiddleware:
    """Hook points around the chat pipeline. All methods are optional no-ops by default."""

    async def before_handle(self, message: Message) -> None:  # noqa: D401
        """Called before any processing of the incoming message."""

    async def before_retrieval(self, context: ReplyContext) -> None:  # noqa: D401
        """Called after context building and before retrieval planning/execution."""

    async def after_retrieval(self, context: ReplyContext) -> None:  # noqa: D401
        """Called after retrieval results are attached to context."""

    async def before_reply_stream(self, context: ReplyContext) -> None:  # noqa: D401
        """Called before starting to stream reply messages."""

    async def on_reply(self, reply: Message) -> None:  # noqa: D401
        """Called for each reply message as it streams out."""

    async def after_reply_stream(self) -> None:  # noqa: D401
        """Called once all reply messages have been generated for this input."""
