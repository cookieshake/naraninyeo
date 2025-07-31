"""응답 생성을 담당하는 리스폰더 에이전트"""

import asyncio
import re
from typing import AsyncIterator, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.core.config import Settings
from naraninyeo.models.message import Message

# 스키마 정의
class TeamResponse(BaseModel):
    """팀 응답 모델"""
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

class Responder:
    """응답 생성을 담당하는 리스폰더 클래스"""
    
    def __init__(self, settings: Settings):
        """리스폰더 초기화"""
        self.settings = settings
        # 리스폰더 에이전트 생성
        self.agent = Agent(
            model=OpenAIModel(
                model_name="openai/gpt-4.1",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY
                )
            ),
            instrument=True,
            model_settings=OpenAIModelSettings(
                timeout=30
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
        """리스폰더 에이전트의 시스템 프롬프트를 생성합니다."""
        return f"""{self._get_current_time_info()}

[1. 나의 정체성]
- **이름:** {self.settings.BOT_AUTHOR_NAME}
- **역할:** 깊이 있는 대화를 유도하는 지적인 파트너
- **목표:** 사용자가 스스로 생각의 폭을 넓히고, 다양한 관점을 고려하여 더 나은 결론을 내릴 수 있도록 돕습니다.
- **성격:** 중립적이고 침착하며, 친절하고 예의 바릅니다. 감정이나 편견에 치우치지 않고 항상 논리적인 태도를 유지합니다.

[2. 대화 원칙]
- **정보 활용:** 사용자의 질문에 답변하기 위해 주어진 '검색 결과'와 '참고할만한 예전 대화 기록'을 활용하여 사실에 기반한 답변을 제공합니다.
- **간결함:** 답변은 항상 짧고 간결하게, 핵심만 요약해서 전달합니다. 불필요한 미사여구나 설명은 생략합니다.
- **균형 추구:** 한쪽으로 치우친 주장에 대해서는 다른 관점을 제시하여 균형 잡힌 사고를 유도합니다.
- **질문 유도:** 단정적인 답변보다는, 사용자가 더 깊이 생각할 수 있도록 자연스러운 질문을 던집니다.

[3. 작업 흐름]
1.  **요청 및 정보 분석:** 사용자의 메시지와 함께 제공된 '검색 결과', '참고할만한 예전 대화 기록'을 분석하여 의도를 명확히 파악합니다.
2.  **최종 답변 생성:** 분석된 정보들을 종합하여, '{self.settings.BOT_AUTHOR_NAME}'의 정체성과 대화 원칙에 맞는 최종 답변을 생성하여 사용자에게 전달합니다.

[4. 중요 규칙]
- **사용자 관점:** 당신에게 제공된 '검색 결과', '참고할만한 예전 대화 기록' 등은 사용자에게 보이지 않습니다. 따라서 "검색 결과에 따르면", "예전 대화를 참고하면" 과 같은 표현을 절대 사용하지 마세요.
- **내부 과정 비공개:** 검색 과정이나 중간 분석 내용을 사용자에게 직접 노출하지 않습니다. (예: "검색 결과:", "분석 중입니다...")
- **완성된 답변:** 항상 완성된 형태의 최종 답변만을 사용자에게 전달해야 합니다.
- **언어:** 답변은 항상 한국어로 작성합니다.
- **응답 형식:** 절대로 응답에 "시간 이름: 메시지" 형식을 사용하지 마세요. 시간과 이름을 포함하지 말고 바로 내용만 작성하세요."""

    def _create_prompt(self, message: Message, history_str: str, reference_conversations_str: str, search_context: str) -> str:
        """응답자 에이전트용 프롬프트를 생성합니다."""
        return f"""대화방 ID: {message.channel.channel_id}

참고할만한 예전 대화 기록:
---
{reference_conversations_str}
---

검색 결과:
---
{search_context}
---

직전 대화 기록:
---
{history_str}
---

새로 들어온 메시지:
{message.text_repr}

위 메시지와 검색 결과, 그리고 참고할만한 예전 대화 기록을 바탕으로 '{self.settings.BOT_AUTHOR_NAME}'의 응답을 생성하세요. 
참고할만한 예전 대화 기록에서 관련 정보나 이전에 한 대답들을 활용하여 더 일관성 있고 정확한 답변을 제공하세요.

중요: 반드시 메시지 내용만 작성하세요. "시간 이름: 내용" 형식이나 "나란잉여:" 같은 접두사를 절대 사용하지 마세요. 바로 답변 내용으로 시작하세요."""

    def _extract_response_text(self, response) -> str:
        """AI 응답에서 텍스트를 추출합니다."""
        if isinstance(response, str):
            return response
        
        # 응답 객체에서 텍스트 추출
        return getattr(response, "output", "") or getattr(response, "text", "") or str(response)

    def _clean_paragraph(self, paragraph: str) -> str:
        """단락을 정리합니다."""
        # Remove leading list markers and trailing punctuation
        cleaned = re.sub(r'^\s*([-*•]|\d+\.)\s*|[.,;:]$', '', paragraph).strip()
        return cleaned

    def _format_search_results(self, search_results: List[Dict[str, Any]]) -> str:
        """검색 결과를 포맷팅하여 문자열로 변환합니다."""
        search_context_parts = []
        
        for result in search_results:
            response = result["response"]
            source_header = f"--- 검색: [{result['type']}] {response.query} ---"
            search_context_parts.append(source_header)
            
            # 각 검색 결과 항목을 포맷팅
            for item in response.items:
                item_text = f"[{item.source_type}] {item.title}\n"
                item_text += f"{item.description}\n"
                if item.date:
                    item_text += f"날짜: {item.date}\n"
                search_context_parts.append(item_text)
        
        return "\n\n".join(search_context_parts)

    async def generate_response(
        self,
        message: Message, 
        conversation_history: str,
        reference_conversations: str,
        search_results: List[Dict[str, Any]]
    ) -> AsyncIterator[dict]:
        """
        LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
        
        Args:
            message: 사용자의 입력 메시지
            conversation_history: 대화 기록 문자열
            reference_conversations: 참고할만한 예전 대화 기록 문자열
            search_results: 검색 결과 리스트
            
        Yields:
            dict: TeamResponse 객체의 딕셔너리 표현
        """
        logger.info(f"Generating response for message: {message.message_id} in channel: {message.channel.channel_id}")
        
        # 검색 결과 포맷팅
        search_context = self._format_search_results(search_results)
        logger.info(f"Created search context with {len(search_results)} search results")
        
        # 응답 생성
        responder_prompt = self._create_prompt(message, conversation_history, reference_conversations, search_context)

        logger.info("Running responder agent")
        response = await self.agent.run(responder_prompt)
        response_text = self._extract_response_text(response)
        
        # 응답을 단락별로 분리하여 스트리밍
        contents = re.split(r'\n{2,}', response_text)
        logger.info(f"Split response into {len(contents)} paragraphs")
        
        paragraph_count = 0
        while contents:
            paragraph = contents.pop(0)
            cleaned_paragraph = self._clean_paragraph(paragraph)
            
            # 빈 내용은 건너뛰기
            if not cleaned_paragraph:
                continue
            
            paragraph_count += 1
            is_final = len(contents) == 0
            logger.debug(f"Yielding paragraph {paragraph_count}, is_final={is_final}")
            
            yield TeamResponse(
                response=cleaned_paragraph,
                is_final=is_final
            ).model_dump()
            
            await asyncio.sleep(self.settings.RESPONSE_DELAY)
