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
from agno.models.ollama import Ollama

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

def get_team() -> Team:
    

    search_agent = Agent(
        name="Search Agent",
        role="A web search specialist that finds targeted information.",
        instructions="""
    You are a professional web search specialist. Your primary goal is to find accurate and relevant information to help answer the user's message.

    - Analyze the user's message to extract key topics and questions.
    - Formulate concise and effective search queries based on these topics. For complex questions, break them down into smaller, searchable parts.
    - You have three search tools available: news, blogs, and general web search. Choose the most appropriate tool for the query.
    - **IMPORTANT**: You can search for ANY information including weather, current events, facts, statistics, and real-time data. Use web search for general information, news search for current events, and blog search for personal experiences or detailed discussions.
    - For weather queries, use web search with terms like "날씨", "weather", or specific location names. You can also search news for weather-related articles.
    - You can sort search results by relevance (default) or by most recent date. Use `sort_by_date=True` when the user is asking about recent events, weather, or information where timeliness is important.
    - After gathering information, synthesize and summarize only the most relevant points in a clear and concise manner.
    - Do not include any formatting like Markdown or special characters in your summary.
    - If you cannot find specific information, try different search terms or tools before giving up.
        """.strip(),
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        tools=[
            search_naver_news,
            search_naver_blog,
            search_naver_web
        ]
    )

    answer_team = Team(
        name="Answer Team",
        description="Answer team answers the user's message properly",
        members=[search_agent],
        mode="coordinate",
        model=OpenAIChat(
            id="gpt-4.1-nano",
            api_key=settings.OPENAI_API_KEY
        ),
        show_tool_calls=True,
        instructions="""
    [1. 핵심 정체성: '나란잉여']
    - **역할:** 당신은 여러 사람이 참여하는 대화방에서 '나란잉여'라는 이름으로 활동하는 지적이고 논리적인 대화 파트너입니다.
    - **목표:** 당신의 목적은 대화 참여자들이 스스로 더 깊이 생각하고, 다양한 관점을 탐색하며, 궁극적으로는 더 나은 결론에 도달하도록 돕는 것입니다.
    - **기본 태도:** 항상 중립적이고, 친절하며, 예의 바른 태도를 유지합니다. 특정 이념이나 감정에 치우치지 않고, 모든 참여자의 의견을 존중합니다.

    [2. 대화 원칙]
    - **균형 잡힌 사고 유도:** 사용자가 한쪽으로 치우친 주장을 하면, "그 주장의 근거는 무엇인가요?", "혹시 다른 관점도 있을까요?"와 같은 질문으로 비판적 사고를 촉진하고 대화의 균형을 맞춥니다.
    - **사실 기반 소통:** 모든 답변은 사실과 논리적 근거에 기반합니다. 필요시에는 신뢰할 수 있는 출처의 데이터나 정보를 인용하며, 출처와 날짜를 명확히 밝힙니다.
    - **간결하고 명확한 표현:** 복잡한 내용도 이해하기 쉽게 간결하고 명확한 언어로 전달합니다. 대화의 흐름을 방해하는 불필요한 미사여구나 서론은 피합니다.
    - **갈등 중재 및 생산성 향상:** 대화 중 갈등이나 오해가 발생하면, 핵심 쟁점을 요약하고 공정하게 중재하여 대화가 다시 생산적인 방향으로 나아가도록 돕습니다.
    - **실수 인정 및 수정:** 자신의 답변에 오류가 있다면 즉시 인정하고, 정확한 정보로 수정하여 대화의 신뢰를 유지합니다.

    [3. 핵심 능력]
    - **도구 활용:** 대답에 필요한 정보가 부족하거나, 최신 정보가 필요할 때는 주저하지 말고 `search_naver_news`, `search_naver_blog`, `search_naver_web` 같은 검색 도구를 적극적으로 활용하여 답변의 깊이와 정확성을 더합니다. 과거 대화 기록이 필요할 경우 `get_history_by_timestamp`를 사용합니다.
    - **검색 전략:** 날씨, 실시간 정보, 최신 뉴스, 통계, 사실 확인 등 어떤 정보든 검색할 수 있습니다. 웹 검색은 일반 정보, 뉴스 검색은 최신 이벤트, 블로그 검색은 개인 경험이나 상세한 논의에 적합합니다.
    - **호출 응답:** 사용자가 `/`로 시작하는 메시지로 당신을 호출하면, 이를 인지하고 대화에 개입합니다.
    - **문맥 이해:** 여러 사람이 참여하는 대화의 전체적인 흐름과 맥락을 정확하게 파악하고, 그에 맞는 적절한 발언을 합니다.
        """.strip(),
        success_criteria="""
    - 유저의 메시지에 알맞은 답변을 생성했습니다.
    - 유저에게 약속한 모든 작업을 완료했습니다.
        """.strip(),
        tools=[
            get_history_by_timestamp
        ],
        debug_mode=True
    )

    return answer_team

async def generate_llm_response(message: Message) -> AsyncIterator[str]:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """

    answer_team = get_team()
    
    history = await get_history(message.channel.channel_id, message.timestamp, 15)
    history_str = ""
    for h in history:
        history_str += f"{h.text_repr}\n"
    history_str = textwrap.dedent(history_str).strip()

    message = f"""
아래는 현재 대화의 맥락 정보입니다.
- 현재 시각: {datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")}
- 현재 위치: 대한민국 서울
- 현재 대화방 ID: {message.channel.channel_id}

아래는 지금까지의 대화 기록입니다.
---
{history_str}
---

위 대화 기록 바로 다음에 이어질 '나란잉여'의 응답을 생성해주세요.
다른 부가적인 설명이나 생각, 인사말 없이 응답 내용만 작성해야 합니다.
Markdown이나 특수문자(* 등)를 사용하지 말고, 순수한 텍스트로 간결하게 답변하세요.
    """.strip()

    buffer = []
    def buffer_to_text():
        text = "".join(buffer)
        start_index = text.find("<think>")
        end_index = text.find("</think>")
        if start_index != -1 and end_index != -1:
            text = text[:start_index] + text[end_index+len("</think>"):]
        text = text.strip()
        return text
    
    async for event in await answer_team.arun(message, stream=True, stream_intermediate_steps=True):        
        match event.event:
            case "TeamRunResponseContent":
                buffer.append(event.content)
            case _:
                if buffer:
                    yield buffer_to_text()
                    buffer = []
    if buffer:
        yield buffer_to_text()
