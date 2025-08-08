"""검색 계획 생성을 담당하는 플래너 에이전트"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Literal, List

from loguru import logger
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.core.config import Settings
from naraninyeo.models.message import Message, Author

# 스키마 정의
class SearchMethod(BaseModel):
    """검색 방법 모델"""
    type: Literal["news", "blog", "web", "encyclopedia", "cafe", "doc"] = Field(description="검색 유형")
    query: str = Field(description="검색어")
    limit: int = Field(default=3, description="결과 수")
    sort: Literal["sim", "date"] = Field(default="sim", description="정렬 방식")

class SearchPlan(BaseModel):
    """검색 계획 모델"""
    methods: list[SearchMethod] = Field(description="수행할 검색 목록")

    @field_validator('methods')
    def methods_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("하나 이상의 검색 방법이 필요합니다.")
        return v

class Planner:
    """검색 계획 생성을 담당하는 플래너 클래스"""
    
    def __init__(self, settings: Settings):
        """플래너 초기화"""
        self.settings = settings
        # 플래너 에이전트 생성
        self.agent = Agent(
            model=OpenAIModel(
                model_name="openai/gpt-5-mini",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY
                )
            ),
            output_type=SearchPlan,
            instrument=True,
            model_settings=OpenAIModelSettings(
                timeout=30,
                extra_body={
                    "reasoning": {
                        "effort": "minimal"
                    }
                }
            )
        )
        
        # 시스템 프롬프트 설정
        self.agent.system_prompt = self._get_system_prompt()
    
    def _get_current_time_info(self) -> str:
        """현재 시간 정보를 반환합니다."""
        now = datetime.now(ZoneInfo(self.settings.TIMEZONE))
        return f"""현재 시각: {now.strftime("%Y-%m-%d %H:%M:%S %A")}
현재 위치: "{self.settings.LOCATION}" """

    def _get_system_prompt(self) -> str:
        """플래너 에이전트의 시스템 프롬프트를 생성합니다."""
        return f"""{self._get_current_time_info()}

당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
사용자의 질문과 대화 기록을 바탕으로, 어떤 종류의 검색을 수행할지 계획해야 합니다.

다음과 같은 검색 유형을 사용할 수 있습니다:
1. news - 뉴스 기사 검색, 최신 뉴스나 시사 정보에 적합
2. blog - 블로그 글 검색, 개인적인 경험이나 일상적인 정보에 적합
3. web - 일반 웹 검색, 다양한 웹사이트 정보가 필요할 때 적합
4. encyclopedia - 백과사전 검색, 개념이나 사실 정보가 필요할 때 적합
5. cafe - 카페 게시글 검색, 커뮤니티 의견이나 토론이 필요할 때 적합
6. doc - 전문 문서 검색, 학술적 정보나 보고서가 필요할 때 적합

필요에 따라 여러 유형을 선택하고 각각에 맞는 검색어를 생성하세요.
예시:
- 최신 정치 뉴스를 찾을 때: 'news' 타입에 '대한민국 최신 정치 이슈' 쿼리
- 요리법을 찾을 때: 'blog' 타입에 '간단한 김치찌개 만드는 법' 쿼리
- 학술 정보를 찾을 때: 'doc' 타입에 '인공지능 윤리적 이슈 연구' 쿼리

반드시 하나 이상의 검색 방법을 생성해야 하며, 각 검색은 서로 다른 측면의 정보를 찾는 데 도움이 되어야 합니다."""

    def _create_prompt(self, message: Message, history_str: str, reference_conversations_str: str) -> str:
        """플래너 에이전트용 프롬프트를 생성합니다."""
        return f"""대화방 ID: {message.channel.channel_id}

참고할만한 예전 대화 기록:
---
{reference_conversations_str}
---

직전 대화 기록:
---
{history_str}
---

새로 들어온 메시지:
{message.text_repr}

위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요? 참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요."""

    async def create_search_plan(
        self,
        message: Message,
        conversation_history: str, 
        reference_conversations: str
    ) -> SearchPlan:
        """검색 계획을 생성합니다."""
        planner_prompt = self._create_prompt(message, conversation_history, reference_conversations)
        
        logger.info(f"Running planner agent for message: {message.message_id}")
        search_plan = (await self.agent.run(planner_prompt)).output
        logger.info(f"Search plan generated with {len(search_plan.methods)} methods")
        
        return search_plan
