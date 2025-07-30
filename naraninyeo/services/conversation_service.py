"""대화 관련 오케스트레이션 서비스 - 완전 구현"""

import asyncio
from typing import List, Dict, Any, Optional

from loguru import logger

from naraninyeo.models.message import Message
from naraninyeo.core.config import settings
from naraninyeo.adapters.repositories import MessageRepository
from naraninyeo.adapters.clients import EmbeddingClient, LLMClient
from naraninyeo.llm.schemas import SearchPlan
from naraninyeo.adapters.search_client import SearchClient

class ConversationService:
    """대화 관련 서비스 - DI 적용"""
    
    def __init__(
        self, 
        message_repo: MessageRepository, 
        embedding_client: EmbeddingClient, 
        llm_client: LLMClient, 
        search_client: SearchClient
    ):
        self.message_repo = message_repo
        self.embedding_client = embedding_client
        self.llm_client = llm_client
        self.search_client = search_client
    
    async def get_conversation_history(self, channel_id: str, timestamp, exclude_message_id: str) -> str:
        """대화 기록을 가져와 문자열로 변환합니다."""
        from datetime import datetime
        if isinstance(timestamp, int):
            dt_timestamp = datetime.fromtimestamp(timestamp)
        else:
            dt_timestamp = timestamp
        
        history = await self.message_repo.get_history(channel_id, dt_timestamp, settings.HISTORY_LIMIT)
        history = [msg for msg in history if msg.message_id != exclude_message_id]
        return "\n".join([m.text_repr for m in history])
    
    async def get_reference_conversations(self, channel_id: str, query: str) -> str:
        """참고할만한 예전 대화 기록을 검색합니다."""
        try:
            # 1. 쿼리를 임베딩으로 변환
            embeddings = await self.embedding_client.get_embeddings([query])
            
            # 2. 유사한 메시지 검색
            similar_messages = await self.message_repo.search_similar(
                embeddings[0], 
                channel_id, 
                limit=5
            )
            
            if not similar_messages:
                return "참고할만한 예전 대화 기록이 없습니다."
            
            # 3. 메시지들을 그룹화 (간단히 시간순으로)
            reference_conversations = []
            for i, msg in enumerate(similar_messages):
                reference_conversations.append(f"--- 참고 대화 #{i+1} ---\n{msg.text_repr}")
            
            return "\n\n".join(reference_conversations)
            
        except Exception as e:
            logger.error(f"Failed to get reference conversations: {e}")
            return "참고할만한 예전 대화 기록을 가져오는 중 오류가 발생했습니다."
    
    async def perform_search_with_plan(self, search_plan: SearchPlan, message: Message) -> List[Dict[str, Any]]:
        """검색 계획에 따라 검색을 수행합니다."""
        search_results = []
        
        if not self.search_client:
            logger.warning("Search client not available, skipping search")
            return search_results
            
        try:
            # 여러 검색을 병렬로 실행
            search_tasks = []
            for method in search_plan.methods:
                task = self._execute_search_method(method)
                search_tasks.append(task)
            
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
            logger.error(f"Search plan execution failed: {e}")
            # 기본 검색으로 폴백
            try:
                if self.search_client:
                    result = await self.search_client.search(
                        message.content.text, 
                        "web",
                        settings.DEFAULT_SEARCH_LIMIT
                    )
                    if result and result.items:
                        search_results.append({
                            "type": "web",
                            "query": message.content.text,
                            "response": result
                        })
            except Exception as e2:
                logger.error(f"Fallback search failed: {e2}")
        
        return search_results
    
    async def _execute_search_method(self, method) -> Any:
        """개별 검색 방법을 실행합니다."""
        if not self.search_client:
            raise RuntimeError("Search client not available")
        
        # 통합 search 메서드 사용
        return await self.search_client.search(method.query, method.type, method.limit, method.sort)
    
    async def prepare_llm_context(self, message: Message) -> Dict[str, Any]:
        """LLM 응답 생성에 필요한 모든 컨텍스트를 준비합니다."""
        # 1. 대화 기록 수집
        history_str = await self.get_conversation_history(
            message.channel.channel_id, 
            message.timestamp, 
            message.message_id
        )
        
        # 2. 참고할만한 예전 메시지 검색
        reference_conversations_str = await self.get_reference_conversations(
            message.channel.channel_id, 
            message.content.text
        )
        
        # 3. 검색 계획 생성 (LLM 사용)
        search_results = []
        try:
            search_plan = await self.llm_client.create_search_plan(
                message, 
                history_str, 
                reference_conversations_str
            )
            
            # 4. 검색 수행
            search_results = await self.perform_search_with_plan(search_plan, message)
            
        except Exception as e:
            logger.error(f"Failed to create/execute search plan: {e}")
        
        return {
            "history": history_str,
            "reference_conversations": reference_conversations_str,
            "search_results": search_results
        }


# 하위 호환성을 위한 기존 함수들 (deprecated)
_message_repo = None
_embedding_client = None

async def get_conversation_history(channel_id: str, timestamp, exclude_message_id: str) -> str:
    """Deprecated: ConversationService 사용 권장"""
    logger.warning("get_conversation_history is deprecated, use ConversationService instead")
    global _message_repo
    if not _message_repo:
        from naraninyeo.adapters.repositories import MessageRepository
        _message_repo = MessageRepository()
    
    service = ConversationService(_message_repo, None, None)
    return await service.get_conversation_history(channel_id, timestamp, exclude_message_id)

async def prepare_llm_context(message: Message) -> Dict[str, Any]:
    """Deprecated: ConversationService 사용 권장"""
    logger.warning("prepare_llm_context is deprecated, use ConversationService instead")
    # 간단한 버전만 제공
    history_str = await get_conversation_history(
        message.channel.channel_id, 
        message.timestamp, 
        message.message_id
    )
    
    return {
        "history": history_str,
        "reference_conversations": "참고할만한 예전 대화 기록이 없습니다.",
        "search_results": []
    }
