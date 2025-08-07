"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""
from typing import Optional, Iterable
from collections.abc import AsyncIterator
import asyncio

from dishka import Provider, Scope, make_async_container, provide, AnyOf

from naraninyeo.adapters.repositories import MessageRepository, AttachmentRepository
from naraninyeo.adapters.clients import LLMClient, EmbeddingClient, APIClient
from naraninyeo.adapters.search_client import SearchClient
from naraninyeo.adapters.crawler import Crawler
from naraninyeo.agents.extractor import Extractor
from naraninyeo.core.config import Settings
from naraninyeo.services.conversation_service import ConversationService
from naraninyeo.services.random_responder import RandomResponderService
from naraninyeo.adapters.database import DatabaseAdapter
from naraninyeo.adapters.vectorstore import VectorStoreAdapter
from naraninyeo.agents.planner import Planner
from naraninyeo.agents.responder import Responder


class InfrastructureProvider(Provider):
    """인프라 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정 - 모든 프로바이더에 적용
    scope = Scope.APP
    
    @provide
    async def settings(self) -> Settings:
        return Settings()
    
    # DatabaseAdapter를 의존성 주입 시스템에 추가
    @provide
    async def database_adapter(self, settings: Settings) -> AsyncIterator[DatabaseAdapter]:
        # 데이터베이스 어댑터 인스턴스 생성
        adapter = DatabaseAdapter(settings)
        yield adapter
        # 컨테이너가 종료될 때 데이터베이스 연결도 종료
        await adapter.disconnect()

    @provide
    async def crawler(self, embedding_client: EmbeddingClient) -> AsyncIterator[Crawler]:
        crawler = Crawler(embedding_client=embedding_client)
        await crawler.start()
        yield crawler
        await crawler.stop()
    
    # 에이전트 제공
    @provide
    async def planner_agent(self, settings: Settings) -> Planner:
        return Planner(settings)

    @provide
    async def responder_agent(self, settings: Settings) -> Responder:
        return Responder(settings)
    
    @provide
    async def extractor_agent(self, settings: Settings) -> Extractor:
        return Extractor(settings)

    vector_store_adapter = provide(VectorStoreAdapter)
    message_repository = provide(MessageRepository)
    attachment_repository = provide(AttachmentRepository)
    llm_client = provide(LLMClient)
    embedding_client = provide(EmbeddingClient)
    api_client = provide(APIClient)
    search_client = provide(SearchClient)


class ServiceProvider(Provider):
    """서비스 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정
    scope = Scope.APP

    random_responder = provide(RandomResponderService)
    conversation_service = provide(ConversationService)


# 글로벌 컨테이너 - main.py에서 사용
# 다른 파일에서는 이 컨테이너를 직접 import하여 사용
# 예: from naraninyeo.di import container
container = make_async_container(
    InfrastructureProvider(),
    ServiceProvider()
)
