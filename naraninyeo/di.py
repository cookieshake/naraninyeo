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
from naraninyeo.services.message_service import MessageService
from naraninyeo.services.conversation_service import ConversationService
from naraninyeo.services.random_responder import RandomResponderService
from naraninyeo.adapters.database import DatabaseAdapter
from naraninyeo.adapters.vectorstore import VectorStoreAdapter


class InfrastructureProvider(Provider):
    """인프라 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정 - 모든 프로바이더에 적용
    scope = Scope.APP
    
    # DatabaseAdapter를 의존성 주입 시스템에 추가
    @provide
    async def database_adapter(self) -> AsyncIterator[DatabaseAdapter]:
        # 데이터베이스 어댑터 인스턴스 생성
        adapter = DatabaseAdapter()
        # 연결 설정
        await adapter.connect()
        # 인스턴스를 yield
        yield adapter
        # 컨테이너가 종료될 때 데이터베이스 연결도 종료
        await adapter.disconnect()
    
    # 어댑터와 레포지토리 의존성들을 간결하게 속성으로 제공
    vector_store_adapter = provide(VectorStoreAdapter)
    
    # 복잡한 의존성 주입이 필요한 레포지토리는 recursive=True로 자동 해결
    message_repository = provide(MessageRepository)
    attachment_repository = provide(AttachmentRepository)
    
    # 간단한 의존성은 속성으로 직접 등록
    llm_client = provide(LLMClient)
    embedding_client = provide(EmbeddingClient)
    api_client = provide(APIClient)
    search_client = provide(SearchClient)


class ServiceProvider(Provider):
    """서비스 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정
    scope = Scope.APP
    
    # 단순한 서비스는 직접 속성으로 제공
    random_responder = provide(RandomResponderService)
    
    # 복잡한 서비스도 recursive=True를 사용하면 자동으로 의존성 해결 가능
    # 생성자의 타입 힌트를 통해 자동으로 의존성 주입
    message_service = provide(MessageService)
    conversation_service = provide(ConversationService)


# 글로벌 컨테이너 - main.py에서 사용
# 다른 파일에서는 이 컨테이너를 직접 import하여 사용
# 예: from naraninyeo.di import container
container = make_async_container(
    InfrastructureProvider(),
    ServiceProvider()
)
