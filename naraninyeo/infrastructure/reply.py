from datetime import datetime
from typing import AsyncIterable, AsyncIterator, Union, override
from textwrap import dedent
from zoneinfo import ZoneInfo

import logfire
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.model.message import Author, Message, MessageContent
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.infrastructure.settings import Settings


class ReplyGeneratorAgent(ReplyGenerator):
    @override
    async def generate_reply(self, context: ReplyContext) -> AsyncIterator[Message]:
        
        knowledge_text = []
        for ref in context.knowledge_references:
            ref_text = f"[출처: {ref.source_name}"
            if ref.timestamp:
                ref_text += f", {ref.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            ref_text += f"]\n{ref.content}"
            knowledge_text.append(ref_text)
        
        query = dedent(
            f"""
            참고할 만한 정보
            ---
            [상황]
            현재 시각은 {context.environment.timestamp.strftime('%Y-%m-%d %H:%M:%S')}입니다.
            현재 위치는 {context.environment.location}입니다.

            {"\n\n".join(knowledge_text) if knowledge_text else "딱히 참고할 만한 정보가 없습니다."}
            ---

            직전 대화 기록:
            ---
            {"\n".join([msg.text_repr for msg in context.latest_history])}
            ---

            마지막으로 들어온 메시지:
            {context.last_message.text_repr}

            위 내용을 바탕으로 '{self.settings.BOT_AUTHOR_NAME}'의 응답을 생성하세요. 

            중요: 반드시 메시지 내용만 작성하세요. "시간 이름: 내용" 형식이나 "나란잉여:" 같은 접두사를 절대 사용하지 마세요. 바로 답변 내용으로 시작하세요.
            짧고 간결하게, 핵심만 요약해서 전달하세요. 불필요한 미사여구나 설명은 생략하세요.
            """
        )
        logfire.debug("Reply generation query: {query}", query=query)

        async with self.agent.run_stream(query) as stream:
            last_text = ""
            async for message in stream.stream_text(delta=True):
                last_text += message
                while "\n\n" in last_text:
                    text_to_send, last_text = last_text.split("\n\n", 1)
                    yield self._create_new_message(context, text_to_send)
            if last_text:
                yield self._create_new_message(context, last_text)

    def __init__(self, settings: Settings):
        self.settings = settings
        self.agent = Agent(
            model=OpenAIModel(
                model_name="deepseek/deepseek-chat-v3-0324",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY
                )
            ),
            instrument=True,
            output_type=str,
            model_settings=OpenAIModelSettings(
                timeout=20,
                extra_body={
                    "reasoning": {
                        "effort": "minimal"
                    }
                }
            ),
            system_prompt=dedent(
                f"""
                [정체성]
                - 이름: {self.settings.BOT_AUTHOR_NAME}
                - 역할: 생각을 넓혀주는 대화 파트너
                - 성격: 중립적이고 친근함

                [답변 규칙]
                - 간결하고 핵심만 말함
                - 한쪽에 치우치지 않고 다양한 관점 제시
                - 무조건 한국어 반말 사용
                - "검색 결과에 따르면" 같은 표현 절대 사용 금지
                - "시간 이름: 메시지" 형식 사용 금지
                """.strip()
            )
        )

    def _create_new_message(self, context: ReplyContext, text: str) -> Message:
        now = datetime.now(ZoneInfo(self.settings.TIMEZONE))
        timestamp_millis = int(now.timestamp() * 1000)
        return Message(
            message_id=f"{context.last_message.message_id}-reply-{timestamp_millis}",
            channel=context.last_message.channel,
            author=Author(
                author_id=self.settings.BOT_AUTHOR_ID,
                author_name=self.settings.BOT_AUTHOR_NAME
            ),
            content=MessageContent(
                text=text,
                attachments=[]
            ),
            timestamp=now
        )       