"""Reply generation helpers tying LLM output to message objects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from opentelemetry.trace import get_tracer

from naraninyeo.assistant.llm_toolkit import LLMToolFactory
from naraninyeo.assistant.models import Author, Message, MessageContent, ReplyContext
from naraninyeo.assistant.prompts import ReplyPrompt
from naraninyeo.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from naraninyeo.app.pipeline import ChatPipeline


class ReplyGenerator:
    """Stream text chunks from the LLM and convert them into Message objects."""

    def __init__(self, settings: Settings, llm_factory: LLMToolFactory):
        self.settings = settings
        self.tool = llm_factory.reply_tool()

    def _create_message(self, context: ReplyContext, text: str) -> Message:
        now = datetime.now(ZoneInfo(self.settings.TIMEZONE))
        timestamp_millis = int(now.timestamp() * 1000)
        return Message(
            message_id=f"{context.last_message.message_id}-reply-{timestamp_millis}",
            channel=context.last_message.channel,
            author=Author(
                author_id=self.settings.BOT_AUTHOR_ID,
                author_name=self.settings.BOT_AUTHOR_NAME,
            ),
            content=MessageContent(text=text, attachments=[]),
            timestamp=now,
        )

    async def stream(self, context: ReplyContext) -> AsyncIterator[Message]:
        prompt = ReplyPrompt(context=context, bot_name=self.settings.BOT_AUTHOR_NAME)
        buffer = self.settings.REPLY_TEXT_PREFIX
        async for chunk in self.tool.stream_text(prompt, delta=True):
            buffer += chunk
            while "\n\n" in buffer:
                text_to_send, buffer = buffer.split("\n\n", 1)
                # 두 줄 공백을 기준으로 메시지를 잘라 실시간으로 내보낸다.
                yield self._create_message(context, text_to_send)
        if buffer:
            yield self._create_message(context, buffer)


class NewMessageHandler:
    """Facade that runs the chat pipeline and streams out reply messages."""

    def __init__(self, pipeline: "ChatPipeline"):
        self._pipeline = pipeline

    async def handle(self, message: Message) -> AsyncIterator[Message]:
        with get_tracer(__name__).start_as_current_span("handle new message"):
            # 파이프라인이 생성하는 응답을 그대로 전달하여 스트리밍 인터페이스를 유지한다.
            async for reply in self._pipeline.run(message):
                yield reply
