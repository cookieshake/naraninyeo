"""LLM 에이전트 핵심 로직"""

import asyncio
import re
from typing import AsyncIterator, List, Dict, Any

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.core.config import settings
from naraninyeo.models.message import Message, Author
from .schemas import TeamResponse, SearchMethod, SearchPlan
from .prompts import (
    get_planner_system_prompt, 
    get_responder_system_prompt,
    create_planner_prompt,
    create_responder_prompt
)

# 봇 정보
bot_author = Author(
    author_id=settings.BOT_AUTHOR_ID,
    author_name=settings.BOT_AUTHOR_NAME
)

def create_agents() -> tuple[Agent, Agent]:
    """플래너와 응답자 에이전트를 생성합니다."""
    planner_agent = Agent(
        model=OpenAIModel(
            model_name="google/gemini-2.5-flash-lite",
            provider=OpenRouterProvider(
                api_key=settings.OPENROUTER_API_KEY,
                
            )
        ),
        output_type=SearchPlan,
        instrument=True
    )

    responder_agent = Agent(
        model=OpenAIModel(
            model_name="openai/gpt-4.1-mini",
            provider=OpenRouterProvider(
                api_key=settings.OPENROUTER_API_KEY,
            )
        ),
        instrument=True
    )
    
    # 시스템 프롬프트 설정
    planner_agent.system_prompt = get_planner_system_prompt
    responder_agent.system_prompt = get_responder_system_prompt
    
    return planner_agent, responder_agent

planner_agent, responder_agent = create_agents()

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
    
    if request.author.author_name == settings.BOT_AUTHOR_NAME:
        logger.debug(f"Message {request.message_id} is from bot itself, no response needed")
        return False
        
    if request.content.text.startswith('/'):
        logger.debug(f"Message {request.message_id} starts with '/', response needed")
        return True
        
    logger.debug(f"Message {request.message_id} does not need a response")
    return False

async def generate_llm_response(
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
    search_context = format_search_results(search_results)
    logger.info(f"Created search context with {len(search_results)} search results")
    
    # 응답 생성
    responder_prompt = create_responder_prompt(message, conversation_history, reference_conversations, search_context)

    logger.info("Running responder agent")
    response = await responder_agent.run(responder_prompt)
    response_text = extract_response_text(response)
    
    # 응답을 단락별로 분리하여 스트리밍
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
        
        await asyncio.sleep(settings.RESPONSE_DELAY)

async def create_search_plan(
    message: Message,
    conversation_history: str, 
    reference_conversations: str
) -> SearchPlan:
    """검색 계획을 생성합니다."""
    planner_prompt = create_planner_prompt(message, conversation_history, reference_conversations)
    
    logger.info(f"Running planner agent for message: {message.message_id}")
    search_plan = (await planner_agent.run(planner_prompt)).output
    logger.info(f"Search plan generated with {len(search_plan.methods)} methods")
    
    return search_plan

def format_search_results(search_results: List[Dict[str, Any]]) -> str:
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
