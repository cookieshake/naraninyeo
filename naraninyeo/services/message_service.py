"""
핵심 비즈니스 로직만 담당하는 서비스
Infrastructure 의존성은 생성자로 주입받음
Dishka 스타일로 리팩토링
"""
from typing import AsyncIterator, List
from datetime import datetime

from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.adapters.repositories import MessageRepository
from naraninyeo.adapters.clients import LLMClient, EmbeddingClient

class MessageService:
    """메시지 처리 핵심 비즈니스 로직"""
    
    def __init__(
        self, 
        message_repo: MessageRepository,
        llm_client: LLMClient, 
        embedding_client: EmbeddingClient
    ):
        self.message_repo = message_repo
        self.llm_client = llm_client
        self.embedding_client = embedding_client
    
    async def save_message(self, message: Message) -> None:
        """메시지를 저장한다"""
        # 임베딩 생성
        embeddings = await self.embedding_client.get_embeddings([message.content.text])
        
        # 저장
        await self.message_repo.save(message, embeddings[0])
    
    async def should_respond_to(self, message: Message) -> bool:
        """이 메시지에 응답해야 하는지 판단하는 비즈니스 룰"""
        # LLMClient의 should_respond 사용
        return await self.llm_client.should_respond(message)
    
    async def generate_response(self, message: Message) -> AsyncIterator[Message]:
        """메시지에 대한 응답을 생성한다"""
        # 1. 대화 히스토리 가져오기
        history = await self.message_repo.get_history(
            message.channel.channel_id, 
            message.timestamp, 
            limit=10
        )
        # 히스토리를 문자열로 변환
        history_str = "\n".join([msg.text_repr for msg in history])
        
        # 2. 유사 메시지 검색
        embeddings = await self.embedding_client.get_embeddings([message.content.text])
        similar_messages = await self.message_repo.search_similar(
            embeddings[0], 
            message.channel.channel_id,
            limit=3
        )
        
        # 3. LLM 응답 생성
        i = 0
        async for response_text in self.llm_client.generate_response(
            message, history_str, similar_messages
        ):
            i += 1
            response_message = Message(
                message_id=f"{message.message_id}-reply-{i}",
                channel=message.channel,
                author=self._get_bot_author(),
                content=MessageContent(text=response_text),
                timestamp=datetime.now()
            )
            yield response_message
    
    def _get_bot_author(self) -> Author:
        """봇 작성자 정보"""
        from naraninyeo.core.config import settings
        return Author(
            author_id=settings.BOT_AUTHOR_ID,
            author_name=settings.BOT_AUTHOR_NAME
        )
