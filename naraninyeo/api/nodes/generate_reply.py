"""Task that generates a bot reply for the inbound message."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from naraninyeo.api.infrastructure.interfaces import OutboundDispatcher, ReplyGenerator
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import Author, AuthorRole, FlowContext, Message, MessageContent
from naraninyeo.core.task import TaskBase, TaskResult


class GenerateReplyTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, generator: ReplyGenerator, dispatcher: OutboundDispatcher | None = None) -> None:
        super().__init__(generator=generator, dispatcher=dispatcher)
        self._generator = generator
        self._dispatcher = dispatcher

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        reply_context = payload.prepare_reply_context()
        content = await self._generator.generate(context=reply_context)
        bot_name = payload.bot.display_name if payload.bot else "Assistant"
        reply_author = Author(author_id=payload.tenant.bot_id, display_name=bot_name, role=AuthorRole.BOT)
        reply_message = Message(
            tenant=payload.tenant,
            message_id=uuid4().hex,
            channel=payload.inbound.channel,
            author=reply_author,
            content=content if isinstance(content, MessageContent) else MessageContent(text=str(content)),
            timestamp=datetime.now(UTC),
            reply_to_id=payload.inbound.message_id,
        )
        payload.reply = reply_message
        context.set_state("reply_message_id", reply_message.message_id)
        if self._dispatcher:
            await self._dispatcher.dispatch(reply_message)
        return TaskResult(output=payload, diagnostics={"reply_generated": True})
