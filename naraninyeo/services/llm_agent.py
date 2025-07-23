import asyncio
from datetime import datetime
import re
from typing import AsyncIterator, Literal
from zoneinfo import ZoneInfo

from loguru import logger
from pydantic_ai import Agent
from pydantic import BaseModel, Field, field_validator

from naraninyeo.core.config import settings
from naraninyeo.repository.message import get_history, search_similar_messages
from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.services.search_service import (
    search_news, search_blog, search_web, 
    search_encyclopedia, search_cafe, search_doc,
    SearchResponse
)

# 상수 정의
HISTORY_LIMIT = 10
DEFAULT_SEARCH_LIMIT = 3
RESPONSE_DELAY = 1.0  # seconds
TIMEZONE = "Asia/Seoul"
LOCATION = "Seoul, South Korea"

# 모델 설정
PLANNER_MODEL = 'google-gla:gemini-2.5-flash-lite'
RESPONDER_MODEL = 'google-gla:gemini-2.5-flash'

# 봇 정보
bot_author = Author(
    author_id="bot-naraninyeo",
    author_name="나란잉여"
)

# 모델 정의
class TeamResponse(BaseModel):
    """팀 응답 모델"""
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

class SearchMethod(BaseModel):
    """검색 방법 모델"""
    type: Literal["news", "blog", "web", "encyclopedia", "cafe", "doc"] = Field(description="검색 유형")
    query: str = Field(description="검색어")
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, description="결과 수")
    sort: Literal["sim", "date"] = Field(default="sim", description="정렬 방식")

class SearchPlan(BaseModel):
    """검색 계획 모델"""
    methods: list[SearchMethod] = Field(description="수행할 검색 목록")

    @field_validator('methods')
    def methods_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("하나 이상의 검색 방법이 필요합니다.")
        return v

# 에이전트 초기화
def create_agents() -> tuple[Agent, Agent]:
    """플래너와 응답자 에이전트를 생성합니다."""
    planner_agent = Agent(
        PLANNER_MODEL,
        output_type=SearchPlan
    )
    
    responder_agent = Agent(
        RESPONDER_MODEL
    )
    
    return planner_agent, responder_agent

planner_agent, responder_agent = create_agents()

# 프롬프트 생성 함수들
def get_current_time_info() -> str:
    """현재 시간 정보를 반환합니다."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    return f"""현재 시각: {now.strftime("%Y-%m-%d %H:%M:%S %A")}
현재 위치: "{LOCATION}" """

@planner_agent.system_prompt
def get_planner_system_prompt() -> str:
    """플래너 에이전트의 시스템 프롬프트를 생성합니다."""
    return f"""{get_current_time_info()}

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

@responder_agent.system_prompt
def get_responder_system_prompt() -> str:
    """응답자 에이전트의 시스템 프롬프트를 생성합니다."""
    return f"""{get_current_time_info()}

[1. 나의 정체성]
- **이름:** 나란잉여
- **역할:** 깊이 있는 대화를 유도하는 지적인 파트너
- **목표:** 사용자가 스스로 생각의 폭을 넓히고, 다양한 관점을 고려하여 더 나은 결론을 내릴 수 있도록 돕습니다.
- **성격:** 중립적이고 침착하며, 친절하고 예의 바릅니다. 감정이나 편견에 치우치지 않고 항상 논리적인 태도를 유지합니다.

[2. 대화 원칙]
- **제공된 정보 활용:** 사용자의 질문에 답변하기 위해 항상 주어진 '검색 결과'와 '참고할만한 예전 대화 기록'을 최대한 활용하여 사실에 기반한 답변을 제공합니다.
- **예전 대화 참고:** 과거 대화 중 현재 질문과 관련된 대화 내용이 있다면 이를 참고하여 일관성 있는 답변을 제공합니다. 다른 사용자가 물었던 유사한 질문과 그에 대한 답변을 고려하세요.
- **대화 맥락 유지:** 참고할만한 예전 대화 기록에서 나왔던 정보를 활용하되, 현재 대화의 맥락에 맞게 적절히 조정하여 답변합니다.
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
- 답변은 항상 한국어로 작성합니다."""

# 유틸리티 함수들
async def get_conversation_history(channel_id: str, timestamp: int, exclude_message_id: str) -> str:
    """대화 기록을 가져와 문자열로 변환합니다."""
    history = await get_history(channel_id, timestamp, HISTORY_LIMIT)
    history = [msg for msg in history if msg.message_id != exclude_message_id]
    return "\n".join([m.text_repr for m in history])

async def get_reference_conversations(channel_id: str, query: str) -> str:
    """참고할만한 예전 대화 기록을 검색합니다."""
    reference_clusters = await search_similar_messages(channel_id, query)
    
    if not reference_clusters:
        return "참고할만한 예전 대화 기록이 없습니다."
    
    reference_conversations = []
    for i, cluster in enumerate(reference_clusters):
        cluster_str = "\n".join([m.text_repr for m in cluster])
        reference_conversations.append(f"--- 참고 대화 #{i+1} ---\n{cluster_str}")
    
    return "\n\n".join(reference_conversations)

async def execute_search_method(method: SearchMethod):
    """개별 검색 방법을 실행합니다."""
    search_functions = {
        "news": search_news,
        "blog": search_blog,
        "web": search_web,
        "encyclopedia": search_encyclopedia,
        "cafe": search_cafe,
        "doc": search_doc
    }
    
    search_func = search_functions.get(method.type)
    if not search_func:
        raise ValueError(f"Unknown search type: {method.type}")
    
    return await search_func(method.query, method.limit, method.sort)

async def perform_search(message: Message, history_str: str, reference_conversations_str: str) -> list[dict]:
    """검색을 수행하고 결과를 반환합니다."""
    planner_prompt = f"""대화방 ID: {message.channel.channel_id}

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

    search_results = []
    try:
        logger.info(f"Running planner agent for message: {message.message_id}")
        search_plan = (await planner_agent.run(planner_prompt)).output
        logger.info(f"Search plan generated with {len(search_plan.methods)} methods")
        
        # 여러 검색을 병렬로 실행
        search_tasks = [execute_search_method(method) for method in search_plan.methods]
        
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
            result = await search_web(message.content.text, DEFAULT_SEARCH_LIMIT)
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
    
    return search_results

def format_search_results(search_results: list[dict]) -> str:
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

def extract_response_text(response) -> str:
    """AI 응답에서 텍스트를 추출합니다."""
    if isinstance(response, str):
        return response
    
    # 응답 객체에서 텍스트 추출
    return getattr(response, "output", "") or getattr(response, "text", "") or str(response)

def clean_paragraph(paragraph: str) -> str:
    """단락을 정리합니다."""
    # Remove leading list markers and trailing punctuation
    cleaned = re.sub(r'^\s*([-*•]|\d+\.)\s*|[.,;:]$', '', paragraph).strip()
    return cleaned

async def should_respond(request: Message) -> bool:
    """메시지가 응답이 필요한지 확인합니다."""
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
        message: 사용자의 입력 메시지
        
    Yields:
        dict: TeamResponse 객체의 딕셔너리 표현
    """
    logger.info(f"Generating response for message: {message.message_id} in channel: {message.channel.channel_id}")
    
    # 1. 대화 기록 수집
    history_str = await get_conversation_history(
        message.channel.channel_id, 
        message.timestamp, 
        message.message_id
    )
    logger.debug(f"Retrieved conversation history")
    
    # 2. 참고할만한 예전 메시지 검색
    logger.info(f"Searching for reference messages for: {message.content.text}")
    reference_conversations_str = await get_reference_conversations(
        message.channel.channel_id, 
        message.content.text
    )
    logger.info("Retrieved reference conversations")
    
    # 3. 검색 수행
    search_results = await perform_search(message, history_str, reference_conversations_str)
    search_context = format_search_results(search_results)
    logger.info(f"Created search context with {len(search_results)} search results")
    
    # 4. 응답 생성
    responder_prompt = f"""대화방 ID: {message.channel.channel_id}

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

위 메시지와 검색 결과, 그리고 참고할만한 예전 대화 기록을 바탕으로 '나란잉여'의 응답을 생성하세요. 
참고할만한 예전 대화 기록에서 관련 정보나 이전에 한 대답들을 활용하여 더 일관성 있고 정확한 답변을 제공하세요."""

    logger.info("Running responder agent")
    response = await responder_agent.run(responder_prompt)
    response_text = extract_response_text(response)
    
    # 5. 응답을 단락별로 분리하여 스트리밍
    contents = re.split(r'\n{2,}', response_text)
    logger.info(f"Split response into {len(contents)} paragraphs")
    
    paragraph_count = 0
    while contents:
        paragraph = contents.pop(0)
        cleaned_paragraph = clean_paragraph(paragraph)
        
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
        
        await asyncio.sleep(RESPONSE_DELAY)