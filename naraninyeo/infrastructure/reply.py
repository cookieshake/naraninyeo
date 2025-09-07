from datetime import datetime
from textwrap import dedent
from typing import AsyncIterator, override
from zoneinfo import ZoneInfo

from opentelemetry.trace import get_tracer

from naraninyeo.core.llm.agent import Agent
from naraninyeo.core.llm.spec import text
from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.model.message import Author, Message, MessageContent
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.settings import Settings


class ReplyGeneratorAgent(ReplyGenerator):
    @override
    async def generate_reply(self, context: ReplyContext) -> AsyncIterator[Message]:
        with get_tracer(__name__).start_as_current_span("execute reply generation"):
            knowledge_text = []
            for ref in context.knowledge_references:
                ref_text = f"[출처: {ref.source_name}"
                if ref.timestamp:
                    ref_text += f", {ref.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                ref_text += f"]\n{ref.content}"
                knowledge_text.append(ref_text)

            memory_text = [f"- {m.content}" for m in (context.short_term_memory or [])]

            query = dedent(
                f"""
                참고할 만한 정보
                ---
                [상황]
                현재 시각은 {context.environment.timestamp.strftime("%Y-%m-%d %H:%M:%S")}입니다.
                현재 위치는 {context.environment.location}입니다.

                [단기 기억]
                {"\n".join(memory_text) if memory_text else "(없음)"}

                [검색/지식]
                {"\n\n".join(knowledge_text) if knowledge_text else "(없음)"}
                ---

                직전 대화 기록:
                ---
                {"\n".join([msg.text_repr for msg in context.latest_history])}
                ---

                마지막으로 들어온 메시지:
                {context.last_message.text_repr}

                [응답 생성 우선순위]
                1) 직전 대화의 흐름과 톤에 자연스럽게 이어질 것
                2) 마지막 메시지의 의도에 정확히 답할 것
                3) 참고 정보는 보조로만 사용하고, 대화 맥락과 충돌하면 무시할 것
                - 주제 일탈 금지. 사용자가 원하지 않으면 새로운 화제를 시작하지 말 것.

                위 내용을 바탕으로 '{self.settings.BOT_AUTHOR_NAME}'의 응답을 생성하세요.

                반드시 메시지 내용만 작성하세요.
                "시간 이름: 내용" 형식이나 "나란잉여:" 같은 접두사를 절대 사용하지 마세요.
                바로 답변 내용으로 시작하세요.
                짧고 간결하게, 핵심만 요약해서 전달하세요. 불필요한 미사여구나 설명은 생략하세요.
                참고 정보에 끌려가서 대화 흐름을 깨지 않도록 주의하세요.
                """
            )

            async with self.agent.run_stream(query) as stream:
                last_text = self.settings.REPLY_TEXT_PREFIX
                async for message in stream.stream_text(delta=True):
                    last_text += message
                    while "\n\n" in last_text:
                        text_to_send, last_text = last_text.split("\n\n", 1)
                        yield self._create_new_message(context, text_to_send)
                if last_text:
                    yield self._create_new_message(context, last_text)

    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.settings = settings
        self.agent: Agent[str] = llm_factory.reply_agent(output_type=text())

    def _create_new_message(self, context: ReplyContext, text: str) -> Message:
        now = datetime.now(ZoneInfo(self.settings.TIMEZONE))
        timestamp_millis = int(now.timestamp() * 1000)
        return Message(
            message_id=f"{context.last_message.message_id}-reply-{timestamp_millis}",
            channel=context.last_message.channel,
            author=Author(author_id=self.settings.BOT_AUTHOR_ID, author_name=self.settings.BOT_AUTHOR_NAME),
            content=MessageContent(text=text, attachments=[]),
            timestamp=now,
        )
