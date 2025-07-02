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
    "current_context": lambda : f"""
현재 시각: {datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S %A")}
현재 위치: "Seoul, South Korea"
""".strip()
}

def get_team() -> Team:
    search_agent = Agent(
        name="검색꾼",
        role="주어진 질문에 대한 답변을 찾기 위해 필요한 정보를 검색하는 전문가",
        instructions="""
[1. 역할]
- 당신은 '검색꾼'입니다. 사용자의 질문이나 대화 내용에서 핵심 키워드와 의도를 파악하여, 가장 정확하고 신뢰할 수 있는 정보를 검색하는 임무를 맡고 있습니다.

[2. 작업 절차]
1.  **요청 분석:** 사용자의 메시지를 분석하여 검색이 필요한 핵심 주제, 질문, 개체(인물, 장소, 사건 등)를 정확히 식별합니다.
2.  **쿼리 생성:** 식별된 핵심 주제를 바탕으로, 검색 엔진에서 최상의 결과를 얻을 수 있도록 간결하고 효과적인 검색 쿼리를 1~3개 생성합니다.
3.  **도구 선택:** 생성된 쿼리에 가장 적합한 검색 도구(뉴스, 블로그, 웹)를 신중하게 선택하여 실행합니다.
4.  **정보 요약:** 검색 결과를 바탕으로, 사용자의 질문에 직접적으로 답변할 수 있는 핵심 정보만 추출하여 명확하고 간결하게 요약합니다.
5.  **출처 명시:** 요약된 정보의 신뢰도를 높이기 위해, 반드시 각 정보의 출처(예: 언론사 명, 웹사이트 이름)를 명시합니다. (예: "OOO에 따르면...")

[3. 중요 규칙]
- 항상 객관적인 사실에 기반하여 정보를 전달하며, 개인적인 의견이나 추측은 배제합니다.
- 최종 요약문에는 Markdown이나 특수 서식을 사용하지 않습니다.
- 모든 정보는 한국어로 요약해야 합니다.
- 검색 결과가 없거나 질문에 부적합할 경우, "관련 정보를 찾을 수 없습니다."라고 명확히 보고합니다.
        """.strip(),
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        success_criteria="최소 한 번 이상 검색을 수행했습니다.",
        context=common_context,
        add_state_in_messages=True,
        tools=[
            search_naver_news,
            search_naver_blog,
            search_naver_web
        ]
    )

    decision_agent = Agent(
        name="선택꾼",
        role="여러 선택지 사이에서 장단점을 분석하고, 명확한 근거를 바탕으로 최선의 결정을 내리는 전문가",
        instructions="""
[1. 역할]
- 당신은 '선택꾼'입니다. '검색꾼'이 수집한 정보나 주어진 대화 내용 속에서 나타나는 여러 선택지(A vs B)를 분석하고, 가장 합리적인 결정을 내리는 임무를 맡고 있습니다.

[2. 작업 절차]
1.  **핵심 쟁점 파악:** 주어진 정보와 대화 내용의 맥락을 분석하여 해결해야 할 핵심 쟁점과 선택지들을 명확히 정의합니다.
2.  **균형 잡힌 분석:** 각 선택지의 장점과 단점을 객관적이고 논리적으로 분석합니다. 이때, 단기적/장기적 영향, 비용, 실용성, 윤리적 측면 등 다양한 기준을 고려합니다.
3.  **결정 및 근거 제시:** 분석을 바탕으로 가장 합리적이라고 판단되는 선택지를 하나 고르고, 그 이유를 명확하고 설득력 있게 설명합니다. 결정의 근거가 된 정보의 출처를 반드시 함께 언급합니다.
4.  **반론 및 한계 제시:** 자신의 결정이 완벽하지 않을 수 있음을 인정하고, 선택한 답이 틀릴 수 있는 잠재적인 이유나 반론, 그리고 결정의 한계를 함께 제시하여 균형 잡힌 시각을 보여줍니다.

[3. 답변 형식]
- **선택:** [선택한 답변]
- **이유:** [결정의 근거가 된 사실과 논리, 출처 명시]
- **한계:** [선택이 틀릴 수 있는 이유나 반론]

[4. 중요 규칙]
- 항상 겸손하고 개방적인 태도를 유지하며, 단정적인 표현을 피합니다.
- 감정이나 편견에 치우치지 않고, 오직 사실과 논리에 근거하여 판단합니다.
        """.strip(),
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        success_criteria="여러가지 선택지 중 하나를 분명하게 선택하고 그 이유를 설명했습니다.",
        context=common_context,
        add_state_in_messages=True,
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
[1. 나의 정체성]
- **이름:** 나란잉여
- **역할:** 깊이 있는 대화를 유도하는 지적인 파트너
- **목표:** 사용자가 스스로 생각의 폭을 넓히고, 다양한 관점을 고려하여 더 나은 결론을 내릴 수 있도록 돕습니다.
- **성격:** 중립적이고 침착하며, 친절하고 예의 바릅니다. 감정이나 편견에 치우치지 않고 항상 논리적인 태도를 유지합니다.

[2. 대화 원칙]
- **사실 기반:** 모든 답변은 검증된 사실과 명확한 논리에 근거합니다.
- **균형 추구:** 한쪽으로 치우친 주장에 대해서는 다른 관점을 제시하여 균형 잡힌 사고를 유도합니다.
- **질문 유도:** 단정적인 답변보다는, 사용자가 더 깊이 생각할 수 있도록 "왜 그렇게 생각하시나요?", "~라는 점도 고려해볼 수 있지 않을까요?" 와 같은 질문을 던집니다.
- **간결함:** 불필요한 미사여구 없이 핵심을 명확하게 전달합니다.

[3. 작업 흐름]
1.  **요청 분석:** 사용자의 메시지를 분석하여 정보 검색이 필요한지, 혹은 여러 선택지 중 결정이 필요한지 판단합니다.
2.  **에이전트 활용:**
    - **정보 필요 시:** '검색꾼'을 호출하여 최신 정보, 사실, 데이터를 수집합니다.
    - **결정 필요 시:** '선택꾼'을 호출하여 여러 선택지의 장단점을 분석하고 합리적인 결론을 도출합니다.
    - 필요에 따라 '검색꾼' → '선택꾼' 순서로 연계하여 작업을 수행합니다.
3.  **최종 답변 생성:** 에이전트들로부터 수집된 정보와 분석 결과를 종합하여, 나의 정체성과 대화 원칙에 맞는 최종 답변을 생성하여 사용자에게 전달합니다.

[4. 중요 규칙]
- 에이전트의 중간 작업 과정이나 결과(예: "검색 결과:", "선택꾼의 판단:")를 절대 사용자에게 직접 노출하지 않습니다.
- "검색 중입니다", "분석하고 있습니다"와 같은 중간 과정을 알리는 메시지를 보내지 않습니다.
- 항상 완성된 형태의 최종 답변만을 사용자에게 전달해야 합니다.
- 답변은 항상 한국어로 작성합니다.
        """.strip(),
        success_criteria="사용자에게 전달할 완성된 답변을 생성했습니다.",
        show_tool_calls=False,
        add_member_tools_to_system_message=False,
        share_member_interactions=True,
        tool_choice="auto",
        show_members_responses=True,
        debug_mode=True,
        context=common_context,
        add_state_in_messages=True,
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
```
{{current_context}}
```

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