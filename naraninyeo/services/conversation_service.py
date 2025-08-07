"""대화 관련 통합 서비스 - 메시지 처리 + 대화 오케스트레이션"""

import asyncio
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime

from loguru import logger

from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.core.config import Settings
from naraninyeo.adapters.repositories import MessageRepository
from naraninyeo.adapters.clients import EmbeddingClient, LLMClient
from naraninyeo.adapters.agents.planner import SearchMethod, SearchPlan
from naraninyeo.adapters.search_client import SearchClient

class ConversationService:
    """통합 대화 서비스 - 메시지 처리 + 대화 오케스트레이션"""
    
    def __init__(
        self, 
        settings: Settings,
        message_repo: MessageRepository, 
        embedding_client: EmbeddingClient, 
        llm_client: LLMClient, 
        search_client: SearchClient
    ):
        self.settings = settings
        self.message_repo = message_repo
        self.embedding_client = embedding_client
        self.llm_client = llm_client
        self.search_client = search_client
    
    # ===== MessageService 기능들 =====
    
    async def save_message(self, message: Message) -> None:
        """메시지를 저장한다"""
        # 임베딩 생성
        embeddings = await self.embedding_client.get_embeddings([message.content.text])
        
        # 저장
        await self.message_repo.save(message, embeddings[0])
    
    async def should_respond_to(self, message: Message) -> bool:
        """이 메시지에 응답해야 하는지 판단하는 비즈니스 룰"""
        logger.debug(f"Checking if message {message.message_id} from '{message.author.author_name}' needs a response")

        if message.author.author_name == self.settings.BOT_AUTHOR_NAME:
            logger.debug(f"Message {message.message_id} is from bot itself, no response needed")
            return False

        if message.content.text.startswith('/'):
            logger.debug(f"Message {message.message_id} starts with '/', response needed")
            return True

        logger.debug(f"Message {message.message_id} does not need a response")
        return False
    
    async def generate_response(self, message: Message) -> AsyncIterator[Message]:
        """메시지에 대한 응답을 생성한다 - 고급 컨텍스트 사용"""
        # 고급 컨텍스트 준비 사용
        context = await self.prepare_llm_context(message)
        
        # LLM 응답 생성 (고급 컨텍스트 포함)
        i = 0
        async for response_text in self.llm_client.generate_response(
            message, 
            context["history"], 
            context["reference_conversations"],
            context["search_results"]
        ):
            i += 1
            response_message = Message(
                message_id=f"{message.message_id}-reply-{i}",
                channel=message.channel,
                author=Author(
                    author_id=self.settings.BOT_AUTHOR_ID,
                    author_name=self.settings.BOT_AUTHOR_NAME
                ),
                content=MessageContent(text=response_text),
                timestamp=datetime.now()
            )
            yield response_message
    
    # ===== 대화 오케스트레이션 기능들 =====
    
    async def get_conversation_history(self, channel_id: str, timestamp, exclude_message_id: str) -> str:
        """대화 기록을 가져와 문자열로 변환합니다."""
        if isinstance(timestamp, int):
            dt_timestamp = datetime.fromtimestamp(timestamp)
        else:
            dt_timestamp = timestamp
        
        history = await self.message_repo.get_history(channel_id, dt_timestamp, self.settings.HISTORY_LIMIT)
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
                        self.settings.DEFAULT_SEARCH_LIMIT
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

    async def _execute_search_method(self, method: SearchMethod) -> Any:
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
    
    # ===== 통합 메시지 처리 =====
    
    async def process_message(self, message: Message) -> AsyncIterator[Message]:
        """메시지를 처리하는 통합 메서드 - 저장 → 응답 여부 확인 → 응답 생성"""
        # 1. 메시지 저장
        await self.save_message(message)
        
        # 2. 응답 필요한지 확인
        if await self.should_respond_to(message):
            # 3. 응답 생성 및 반환
            async for response in self.generate_response(message):
                yield response
