from datetime import datetime
import random
import re
import textwrap
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from agno.team.team import Team
from agno.agent import Agent
from agno.models.google.gemini import Gemini
from agno.models.openai.chat import OpenAIChat
from pydantic import BaseModel, Field

from naraninyeo.core.config import settings
from naraninyeo.handlers.history import get_history
from naraninyeo.models.message import Message
from naraninyeo.tools import search_naver_news, search_naver_blog, get_history_by_timestamp
from naraninyeo.tools.search import search_naver_web

RANDOM_RESPONSES = [
    "음… 그렇게 볼 수도 있겠네요.",
    "사람마다 다를 수 있죠, 뭐.",
    "그럴 만도 하네요, 듣고 보니.",
    "그런 얘기, 종종 들려요.",
    "뭐, 그런 식으로도 생각할 수 있죠.",
    "그럴 수도 있고 아닐 수도 있겠네요. 알 수 없는 거죠.",
    "세상엔 참 다양한 생각이 있는 것 같아요.",
    "맞다기보단… 그냥 그런 경우도 있는 거 같아요.",
    "그런 입장도 충분히 이해는 가요.",
    "어떻게 보면 맞는 말이죠, 생각하기 나름이에요.",
    "그런 관점도 있군요, 흥미롭네요.",
    "사실 정답은 없는 것 같아요.",
    "그럴 법도 하네요, 충분히.",
    "음, 나름대로의 이유가 있겠죠.",
    "그런 식으로 접근하는 것도 방법이네요.",
    "뭐라고 딱 잘라 말하기는 어렵겠어요.",
    "경우에 따라 다를 수 있겠네요.",
    "그런 시각으로 보면 그렇겠어요.",
    "일리가 있는 말씀이에요.",
    "그럴 가능성도 배제할 수는 없죠.",
    "상황에 따라서는 맞는 말일 수도 있어요.",
    "그런 해석도 가능하겠네요.",
    "어느 정도는 공감이 가는 부분이에요.",
    "그런 각도에서 보면 그럴 수도 있고요.",
    "사람들이 흔히 하는 얘기죠.",
    "그런 면도 분명히 있을 거예요.",
    "완전히 틀렸다고는 할 수 없겠네요.",
    "그런 생각을 하는 사람들도 많죠.",
    "어떻게 보느냐에 따라 달라지는 것 같아요.",
    "그런 입장에서는 당연한 생각이겠어요.",
    "뭐, 그럴 수도 있는 일이죠.",
    "그런 관점에서는 이해가 가네요.",
    "상당히 설득력 있는 의견이에요.",
    "그런 측면도 고려해볼 만하네요.",
    "충분히 그럴 만한 이유가 있겠어요.",
    "그런 식으로 생각해본 적은 없었는데, 흥미롭네요.",
    "케이스 바이 케이스인 것 같아요.",
    "그런 부분도 무시할 수는 없죠.",
    "어느 정도 타당성이 있는 말씀이에요.",
    "그런 시선으로 바라보면 그렇겠네요."
]

async def get_random_response(message: Message) -> str:
    """
    Get a random response from the predefined list
    """
    rand = random.Random(message.content.text)
    return rand.choice(RANDOM_RESPONSES)

not_safe_settings = [
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"}
]

class TeamResponse(BaseModel):
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

common_context = {
    "current_datetime": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S %A"),
    "current_location": "Seoul, South Korea"
}

def get_team() -> Team:
    search_agent = Agent(
        name="검색꾼",
        role="답변에 필요한 정보를 검색하는 전문가",
        instructions="""
- 사용자 메시지를 분석하여 주요 주제와 질문을 추출하세요
- 간결하고 효과적인 검색 쿼리를 작성하세요
- 뉴스, 블로그, 일반 웹 검색 중 적합한 도구를 선택하세요
- 날씨, 현재 이벤트, 사실, 통계, 실시간 데이터를 검색할 수 있습니다
- 정보를 수집한 후, 관련성 높은 요점만 명확하고 간결하게 요약하세요
- 모든 정보 요약 시 반드시 출처를 명시하세요
  - 예시: "(언론사명, 년월)"
- Markdown이나 특수 문자를 포함하지 마세요
        """.strip(),
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        success_criteria="최소 한 번 이상 검색을 수행했습니다.",
        context=common_context,
        tools=[
            search_naver_news,
            search_naver_blog,
            search_naver_web
        ]
    )

    decision_agent = Agent(
        name="선택꾼",
        role="여러 가지 선택지 중 하나를 선택하고 그 이유를 설명하는 전문가",
        instructions="""
- 검색꾼이 수집한 정보를 바탕으로 판단을 내리세요
- A vs B 같은 선택지가 있을 때 각 선택지의 장단점을 분석하세요
- 더 나은 선택지를 선택하고 그 이유를 명확히 설명하세요
- 선택한 답이 틀릴 수 있는 이유도 함께 언급하세요
- 객관적 사실, 논리적 일관성, 실용성, 장기적 영향, 윤리적 고려사항을 근거로 하세요
- 판단 근거로 사용한 정보의 출처를 함께 언급하세요
- 답변 형식: 선택한 답 → 선택 이유 (출처 포함) → 틀릴 수 있는 이유
- 겸손하고 개방적인 태도를 유지하세요
        """.strip(),
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        success_criteria="여러가지 선택지 중 하나를 분명하게 선택하고 그 이유를 설명했습니다.",
        context=common_context
    )

    answer_team = Team(
        name="나란잉여",
        description="나란잉여의 목적은 대화 참여자들이 스스로 더 깊이 생각하고, 다양한 관점을 탐색하며, 궁극적으로는 더 나은 결론에 도달하도록 돕는 것입니다.",
        members=[search_agent, decision_agent],
        mode="coordinate",
        model=OpenAIChat(
            id="gpt-4.1-mini",
            api_key=settings.OPENAI_API_KEY
        ),
        instructions="""
[1. 핵심 정체성]
- **역할:** 대화방에서 '나란잉여'라는 이름으로 활동하는 지적이고 논리적인 대화 파트너
- **목표:** 대화 참여자들이 더 깊이 생각하고, 다양한 관점을 탐색하며, 더 나은 결론에 도달하도록 돕기
- **태도:** 중립적, 친절, 예의 바름. 특정 이념이나 감정에 치우치지 않음

[2. 대화 원칙]
- **사실 기반 소통:** 모든 답변은 사실과 논리적 근거에 기반
- **균형 잡힌 사고 유도:** 한쪽으로 치우친 주장에 대해 다른 관점도 고려하도록 촉진
- **간결하고 명확한 표현:** 불필요한 미사여구 없이 명확하게 전달

[3. 작업 순서]
1. **검색 필요성 판단:** 답변에 최신 정보, 사실, 통계가 필요한지 확인
2. **선택 필요성 판단:** A vs B 같은 선택지가 있는지 확인
3. **에이전트 호출:** 필요시 검색꾼 → 선택꾼 순서로 호출
4. **최종 답변 생성:** 수집된 정보와 판단 결과를 종합하여 사용자에게 전달할 최종 답변을 생성

[4. 중요 규칙]
- 에이전트들의 중간 작업 과정은 사용자에게 보이지 않습니다
- 반드시 최종 답변을 생성해야 합니다
- "검색 중입니다", "분석 중입니다" 같은 중간 메시지를 남기지 마세요
- 사용자에게는 완성된 답변만 전달하세요
        """.strip(),
        success_criteria="사용자에게 전달할 완성된 답변을 생성했습니다.",
        add_location_to_instructions=True,
        show_tool_calls=False,
        add_member_tools_to_system_message=False,
        share_member_interactions=True,
        tool_choice="auto",
        show_members_responses=True,
        debug_mode=True,
        context=common_context
    )
    return answer_team

async def generate_llm_response(message: Message) -> AsyncIterator[dict]:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """

    answer_team = get_team()
    
    history = await get_history(message.channel.channel_id, message.timestamp, 10)
    history_str = ""
    for h in history:
        history_str += f"{h.text_repr}\n"
    history_str = textwrap.dedent(history_str).strip()

    message = f"""
대화방 ID: {message.channel.channel_id}

대화 기록:
---
{history_str}
---

위 대화에 이어질 '나란잉여'의 응답을 생성하세요.
유저에게는 에이전트의 답변이 보이지 않습니다.
에이전트의 답변을 참고하여 유저에게 전달할 답변을 생성하세요.
    """.strip()
    
    buffer = []
    def buffer_to_text():
        nonlocal buffer
        text = "".join(buffer).strip()
        buffer.clear()
        return text
    
    async for event in await answer_team.arun(message, stream=True, stream_intermediate_steps=True):
        if event.event == "TeamRunResponseContent":
            if event.content is not None:
                buffer.append(event.content)
        elif event.event == "TeamToolCallStarted":
            if buffer:
                yield {"response": buffer_to_text(), "is_final": False}
        elif event.event == "TeamRunCompleted":
            if buffer:
                yield {"response": buffer_to_text(), "is_final": True}