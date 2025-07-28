"""대화 관련 오케스트레이션 서비스"""

import asyncio
from typing import List, Dict, Any

from loguru import logger

from naraninyeo.models.message import Message
from naraninyeo.core.config import settings
from naraninyeo.repository.message import get_history, search_similar_message_clusters
from naraninyeo.services.embedding_service import get_embeddings
from naraninyeo.services.search_service import (
    search_news, search_blog, search_web, 
    search_encyclopedia, search_cafe, search_doc
)
from naraninyeo.llm import create_search_plan

async def get_conversation_history(channel_id: str, timestamp: int, exclude_message_id: str) -> str:
    """대화 기록을 가져와 문자열로 변환합니다."""
    history = await get_history(channel_id, timestamp, settings.HISTORY_LIMIT)
    history = [msg for msg in history if msg.message_id != exclude_message_id]
    return "\n".join([m.text_repr for m in history])

async def get_reference_conversations(channel_id: str, query: str) -> str:
    """참고할만한 예전 대화 기록을 검색합니다."""
    embeddings = await get_embeddings([query])
    reference_clusters = await search_similar_message_clusters(channel_id, embeddings[0])
    
    if not reference_clusters:
        return "참고할만한 예전 대화 기록이 없습니다."
    
    reference_conversations = []
    for i, cluster in enumerate(reference_clusters):
        cluster_str = "\n".join([m.text_repr for m in cluster])
        reference_conversations.append(f"--- 참고 대화 #{i+1} ---\n{cluster_str}")
    
    return "\n\n".join(reference_conversations)

async def _execute_search_method(method):
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

async def perform_search_with_plan(search_plan, message: Message) -> List[Dict[str, Any]]:
    """검색 계획에 따라 검색을 수행합니다."""
    search_results = []
    try:
        # 여러 검색을 병렬로 실행
        search_tasks = [_execute_search_method(method) for method in search_plan.methods]
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # 검색 결과를 정리
        for i, method in enumerate(search_plan.methods):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Search failed for {method.type}: {result}")
                continue
            elif hasattr(result, 'items') and result.items:
                search_results.append({
                    "type": method.type,
                    "query": method.query,
                    "response": result
                })
                
    except Exception as e:
        # 검색 계획에 실패하면 기본 검색 수행
        logger.error(f"Search plan execution failed: {e}")
        try:
            result = await search_web(message.content.text, settings.DEFAULT_SEARCH_LIMIT)
            if result.items:
                search_results.append({
                    "type": "web",
                    "query": message.content.text,
                    "response": result
                })
        except Exception as e2:
            logger.error(f"Fallback search failed: {e2}")
    
    return search_results

async def prepare_llm_context(message: Message) -> Dict[str, Any]:
    """LLM 응답 생성에 필요한 모든 컨텍스트를 준비합니다."""
    # 1. 대화 기록 수집
    history_str = await get_conversation_history(
        message.channel.channel_id, 
        message.timestamp, 
        message.message_id
    )
    
    # 2. 참고할만한 예전 메시지 검색
    reference_conversations_str = await get_reference_conversations(
        message.channel.channel_id, 
        message.content.text
    )
    
    # 3. 검색 계획 생성
    search_plan = await create_search_plan(message, history_str, reference_conversations_str)
    
    # 4. 검색 수행
    search_results = await perform_search_with_plan(search_plan, message)
    
    return {
        "history": history_str,
        "reference_conversations": reference_conversations_str,
        "search_results": search_results
    }
