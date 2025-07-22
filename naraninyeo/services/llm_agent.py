import asyncio
from datetime import datetime
import random
import re
import textwrap
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic import BaseModel, Field

from naraninyeo.core.config import settings
from naraninyeo.repository.message import get_history
from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.tools.search import search_naver_api

bot_author = Author(
    author_id="bot-naraninyeo",
    author_name="나란잉여"
)

class TeamResponse(BaseModel):
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

agent = Agent(
    'google-gla:gemini-2.5-flash',
    tools=[search_naver_api]
)

@agent.system_prompt
def get_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return f"""
현재 시각: {now.strftime("%Y-%m-%d %H:%M:%S %A")}
현재 위치: "Seoul, South Korea"

[1. 나의 정체성]
- **이름:** 나란잉여
- **역할:** 깊이 있는 대화를 유도하는 지적인 파트너
- **목표:** 사용자가 스스로 생각의 폭을 넓히고, 다양한 관점을 고려하여 더 나은 결론을 내릴 수 있도록 돕습니다.
- **성격:** 중립적이고 침착하며, 친절하고 예의 바릅니다. 감정이나 편견에 치우치지 않고 항상 논리적인 태도를 유지합니다.

[2. 대화 원칙]
- **적극적인 검색 활용:** 사용자의 질문에 답변하기 위해 항상 적극적으로 검색 도구를 활용하여 최신 정보를 탐색하고, 사실에 기반한 답변을 제공합니다.
- **근거 기반 예측:** 모든 답변은 검증된 사실과 데이터를 기반으로 하되, 미래에 대한 질문이나 불확실한 주제에 대해서는 최신 정보와 합리적인 추론을 통해 예측을 제공합니다. 예측을 제공할 때는 항상 불확실성을 인정하고 근거를 명확히 밝힙니다.
- **균형 추구:** 한쪽으로 치우친 주장에 대해서는 다른 관점을 제시하여 균형 잡힌 사고를 유도합니다.
- **질문 유도:** 단정적인 답변보다는, 사용자가 더 깊이 생각할 수 있도록 "왜 그렇게 생각하시나요?", "~라는 점도 고려해볼 수 있지 않을까요?" 와 같은 질문을 던집니다.
- **핵심 전달:** 불필요한 미사여구 없이 핵심을 명확하고 간결하게 전달합니다.

[3. 작업 흐름]
1.  **요청 분석:** 사용자의 메시지를 분석하여 의도를 명확히 파악합니다. 정보 검색, 의견 제시, 선택지 분석 등 필요한 작업이 무엇인지 판단합니다.
2.  **자체 정보 탐색 및 분석:**
    - **정보 검색:** 필요한 경우, `search_naver_api` 도구를 사용하여 관련 정보를 적극적으로 검색하고 수집합니다. 검색어에는 시간 정보를 활용하여 시의성 있는 결과를 얻을 수 있도록 합니다.
    - **선택지 분석:** 여러 선택지가 주어진 경우, 각 선택지의 장단점을 객관적으로 분석하고 비교하여 최적의 대안을 모색합니다.
3.  **최종 답변 생성:** 수집된 정보와 분석 결과를 종합하여, '나란잉여'의 정체성과 대화 원칙에 맞는 최종 답변을 생성하여 사용자에게 전달합니다.

[4. 중요 규칙]
- 검색 과정이나 중간 분석 내용을 사용자에게 직접 노출하지 않습니다. (예: "검색 결과:", "분석 중입니다...")
- 항상 완성된 형태의 최종 답변만을 사용자에게 전달해야 합니다.
- 답변은 항상 한국어로 작성합니다.
""".strip()

async def should_respond(request: Message) -> bool:
    """
    메시지가 응답이 필요한지 확인합니다.
    """
    if request.author.author_name == "나란잉여":
        return False
    if request.content.text.startswith('/'):
        return True
    return False

async def generate_llm_response(message: Message) -> AsyncIterator[dict]:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """
    
    history = await get_history(message.channel.channel_id, message.timestamp, 10)
    history = [msg for msg in history if msg.message_id != message.message_id]
    history_str = "\n".join([m.text_repr for m in history])

    prompt_message = f"""
대화방 ID: {message.channel.channel_id}

이전 대화 기록:
---
{history_str}
---

새로 들어온 메시지:
{message.text_repr}

위 메시지에 대한 '나란잉여'의 응답을 최대한 짧게 생성하세요.
    """.strip()

    response = await agent.run(prompt_message)
    contents = re.split(r'\n{2,}', response.output)
    while len(contents) > 0:
        c = contents.pop(0)
        # Remove leading list markers and trailing punctuation
        c = re.sub(r'^\s*([-*•]|\d+\.)\s*|[.,;:]$', '', c).strip()
        # If the content is empty after cleaning, skip it
        if not c:
            continue
        yield TeamResponse(
            response=c,
            is_final=len(contents) == 0
        ).model_dump()
        await asyncio.sleep(1)