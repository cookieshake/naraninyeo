import logging
from textwrap import dedent
from typing import List, override

from opentelemetry.trace import get_tracer
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.domain.gateway.retrieval import RetrievalPlanner
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan
from naraninyeo.infrastructure.settings import Settings


class RetrievalPlannerAgent(RetrievalPlanner):
    @override
    @get_tracer(__name__).start_as_current_span("plan retrieval")
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        message = dedent(
            f"""
        직전 대화 기록:
        ---
        {"\n".join([msg.text_repr for msg in context.latest_history])}
        ---

        새로 들어온 메시지:
        {context.last_message.text_repr}

        위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요?
        참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요.
        """
        ).strip()

        result = await self.agent.run(message)
        plans = result.output

        logging.debug(f"Retrieval plans generated: {[p.model_dump() for p in plans]}")
        return list(plans)

    def __init__(self, settings: Settings):
        self.settings = settings
        self.agent = Agent(
            model=OpenAIModel(
                model_name="anthropic/claude-sonnet-4",
                provider=OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY),
            ),
            output_type=List[RetrievalPlan],
            instrument=True,
            model_settings=OpenAIModelSettings(timeout=20, extra_body={"reasoning": {"effort": "minimal"}}),
            system_prompt=dedent(
                """
                당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
                사용자의 질문과 대화 기록을 바탕으로, 어떤 종류의 검색을 수행할지 계획해야 합니다.

                다음과 같은 검색 유형을 사용할 수 있습니다:
                - naver_news: 뉴스 기사 검색, 최신 뉴스나 시사 정보에 적합
                - naver_blog: 블로그 글 검색, 개인적인 경험이나 일상적인 정보에 적합
                - naver_web: 일반 웹 검색, 다양한 웹사이트 정보가 필요할 때 적합
                - naver_doc: 학술 문서 검색, 연구나 학술적 정보에 적합
                - chat_history: 채팅 기록 검색, 이전 대화 내용을 기반으로 정보 검색에 적합

                필요에 따라 여러 유형을 선택하고 각각에 맞는 검색어를 생성하세요.
                예시:
                - 최신 정치 뉴스를 찾을 때: 'naver_news' 타입에 '대한민국 최신 정치 이슈' 쿼리
                - 요리법을 찾을 때: 'naver_blog' 타입에 '간단한 김치찌개 만드는 법' 쿼리
                - 학술 정보를 찾을 때: 'naver_doc' 타입에 '인공지능 윤리적 이슈 연구' 쿼리
                - 강아지에 대한 과거 대화 내용을 찾을 때: 'chat_history' 타입에 '강아지' 쿼리

                검색이 필요하지 않은 경우, 빈 배열을 반환하세요.
                검색이 필요한 경우 되도록이면 다양한 검색 유형을 포함하여 계획을 세우세요.
                """.strip()
            ),
        )
