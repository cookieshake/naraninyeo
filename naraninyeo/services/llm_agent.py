import asyncio
from datetime import datetime
import random
import re
import textwrap
from typing import AsyncIterator, Literal
from zoneinfo import ZoneInfo

from loguru import logger
from pydantic_ai import Agent
from pydantic import BaseModel, Field, field_validator

from naraninyeo.core.config import settings
from naraninyeo.repository.message import get_history
from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.services.search_service import (
    search_news, search_blog, search_web, 
    search_encyclopedia, search_cafe, search_doc,
    SearchResponse
)

bot_author = Author(
    author_id="bot-naraninyeo",
    author_name="나란잉여"
)

class TeamResponse(BaseModel):
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

class SearchMethod(BaseModel):
    """검색 방법"""
    type: Literal["news", "blog", "web", "encyclopedia", "cafe", "doc"] = Field(description="검색 유형")
    query: str = Field(description="검색어")
    limit: int = Field(default=3, description="결과 수")
    sort: Literal["sim", "date"] = Field(default="sim", description="정렬 방식")

class SearchPlan(BaseModel):
    methods: list[SearchMethod] = Field(description="수행할 검색 목록")

    @field_validator('methods')
    def methods_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("하나 이상의 검색 방법이 필요합니다.")
        return v

planner_agent = Agent(
    'google-gla:gemini-2.5-flash-lite',
    output_type=SearchPlan
)

responder_agent = Agent(
    'google-gla:gemini-2.5-flash'
)

@planner_agent.system_prompt
def get_planner_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return f"""
현재 시각: {now.strftime("%Y-%m-%d %H:%M:%S %A")}
현재 위치: "Seoul, South Korea"

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

반드시 하나 이상의 검색 방법을 생성해야 하며, 각 검색은 서로 다른 측면의 정보를 찾는 데 도움이 되어야 합니다.
""".strip()

@responder_agent.system_prompt
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
- **제공된 정보 활용:** 사용자의 질문에 답변하기 위해 항상 주어진 '검색 결과'를 최대한 활용하여 사실에 기반한 답변을 제공합니다.
- **근거 기반 예측:** 모든 답변은 검증된 사실과 데이터를 기반으로 하되, 미래에 대한 질문이나 불확실한 주제에 대해서는 최신 정보와 합리적인 추론을 통해 예측을 제공합니다. 예측을 제공할 때는 항상 불확실성을 인정하고 근거를 명확히 밝힙니다.
- **균형 추구:** 한쪽으로 치우친 주장에 대해서는 다른 관점을 제시하여 균형 잡힌 사고를 유도합니다.
- **질문 유도:** 단정적인 답변보다는, 사용자가 더 깊이 생각할 수 있도록 "왜 그렇게 생각하시나요?", "~라는 점도 고려해볼 수 있지 않을까요?" 와 같은 질문을 던집니다.
- **핵심 전달:** 불필요한 미사여구 없이 핵심을 명확하고 간결하게 전달합니다.

[3. 작업 흐름]
1.  **요청 및 정보 분석:** 사용자의 메시지와 함께 제공된 '검색 결과'를 분석하여 의도를 명확히 파악합니다.
2.  **최종 답변 생성:** 분석된 정보들을 종합하여, '나란잉여'의 정체성과 대화 원칙에 맞는 최종 답변을 생성하여 사용자에게 전달합니다.

[4. 중요 규칙]
- 검색 과정이나 중간 분석 내용을 사용자에게 직접 노출하지 않습니다. (예: "검색 결과:", "분석 중입니다...")
- 항상 완성된 형태의 최종 답변만을 사용자에게 전달해야 합니다.
- 답변은 항상 한국어로 작성합니다.
""".strip()

async def should_respond(request: Message) -> bool:
    """
    메시지가 응답이 필요한지 확인합니다.
    """
    logger.debug(f"Checking if message {request.message_id} from '{request.author.author_name}' needs a response")
    
    if request.author.author_name == "나란잉여":
        logger.debug(f"Message {request.message_id} is from bot itself, no response needed")
        return False
        
    if request.content.text.startswith('/'):
        logger.debug(f"Message {request.message_id} starts with '/', response needed")
        return True
        
    logger.debug(f"Message {request.message_id} does not need a response")
    return False

async def generate_llm_response(message: Message) -> AsyncIterator[dict]:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """
    logger.info(f"Generating response for message: {message.message_id} in channel: {message.channel.channel_id}")
    
    history = await get_history(message.channel.channel_id, message.timestamp, 10)
    history = [msg for msg in history if msg.message_id != message.message_id]
    history_str = "\n".join([m.text_repr for m in history])
    logger.debug(f"Retrieved {len(history)} messages from history")

    planner_prompt = f"""
대화방 ID: {message.channel.channel_id}

이전 대화 기록:
---
{history_str}
---

새로 들어온 메시지:
{message.text_repr}

위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요?
    """.strip()

    search_results = []
    try:
        logger.info(f"Running planner agent for message: {message.message_id}")
        search_plan = (await planner_agent.run(planner_prompt)).output
        logger.info(f"Search plan generated with {len(search_plan.methods)} methods")
        
        # 여러 검색을 병렬로 실행
        search_tasks = []
        for method in search_plan.methods:
            logger.debug(f"Planning search: {method.type} with query: {method.query}")
            if method.type == "news":
                search_tasks.append(search_news(method.query, method.limit, method.sort))
            elif method.type == "blog":
                search_tasks.append(search_blog(method.query, method.limit, method.sort))
            elif method.type == "web":
                search_tasks.append(search_web(method.query, method.limit, method.sort))
            elif method.type == "encyclopedia":
                search_tasks.append(search_encyclopedia(method.query, method.limit, method.sort))
            elif method.type == "cafe":
                search_tasks.append(search_cafe(method.query, method.limit, method.sort))
            elif method.type == "doc":
                search_tasks.append(search_doc(method.query, method.limit, method.sort))
        
        logger.info(f"Executing {len(search_tasks)} search tasks in parallel")
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # 검색 결과를 정리
        for i, method in enumerate(search_plan.methods):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Search failed for {method.type} query '{method.query}': {result}")
            elif isinstance(result, SearchResponse) and result.items:
                logger.info(f"Search successful for {method.type} query '{method.query}': {len(result.items)} results")
                search_results.append({
                    "type": method.type,
                    "query": method.query,
                    "response": result
                })
            else:
                logger.warning(f"Search returned no results for {method.type} query '{method.query}'")
    except Exception as e:
        # 검색 계획에 실패하면 기본 검색 수행
        logger.error(f"Error in search planning: {e}")
        try:
            logger.info(f"Falling back to basic web search with query: {message.content.text}")
            result = await search_web(message.content.text, 3)
            if result.items:
                logger.info(f"Fallback search successful: {len(result.items)} results")
                search_results.append({
                    "type": "web",
                    "query": message.content.text,
                    "response": result
                })
            else:
                logger.warning("Fallback search returned no results")
        except Exception as e2:
            logger.error(f"Fallback search failed: {e2}")
    
    # 검색 결과를 문자열로 변환
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
    
    search_context = "\n\n".join(search_context_parts)
    logger.info(f"Created search context with {len(search_results)} search results")

    responder_prompt = f"""
대화방 ID: {message.channel.channel_id}

이전 대화 기록:
---
{history_str}
---

검색 결과:
---
{search_context}
---

새로 들어온 메시지:
{message.text_repr}

위 메시지와 검색 결과를 바탕으로 '나란잉여'의 응답을 생성하세요.
    """.strip()

    logger.info("Running responder agent")
    response = await responder_agent.run(responder_prompt)
    if isinstance(response, str):
        response_text = response
        logger.debug("Responder agent returned a string response")
    else:
        # 만약 responder_agent가 객체를 반환하면 텍스트 추출
        logger.debug(f"Responder agent returned a non-string response of type: {type(response)}")
        response_text = getattr(response, "output", "") or getattr(response, "text", "") or str(response)
    
    # 텍스트를 단락으로 분리
    contents = re.split(r'\n{2,}', response_text)
    logger.info(f"Split response into {len(contents)} paragraphs")
    
    paragraph_count = 0
    while len(contents) > 0:
        c = contents.pop(0)
        # Remove leading list markers and trailing punctuation
        c = re.sub(r'^\s*([-*•]|\d+\.)\s*|[.,;:]$', '', c).strip()
        # If the content is empty after cleaning, skip it
        if not c:
            continue
        
        paragraph_count += 1
        is_final = len(contents) == 0
        logger.debug(f"Yielding paragraph {paragraph_count}/{paragraph_count + len(contents)}, is_final={is_final}")
        
        yield TeamResponse(
            response=c,
            is_final=is_final
        ).model_dump()
        await asyncio.sleep(1)