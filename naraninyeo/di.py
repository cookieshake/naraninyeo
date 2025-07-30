"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""
from typing import Optional, Iterable
from collections.abc import AsyncIterator
import asyncio

from dishka import Provider, Scope, make_async_container, provide, AnyOf

from naraninyeo.adapters.repositories import MessageRepository
from naraninyeo.adapters.clients import LLMClient, EmbeddingClient, APIClient
from naraninyeo.services.message_service import MessageService
from naraninyeo.services.conversation_service import ConversationService
from naraninyeo.services.random_responder import RandomResponderService
from naraninyeo.adapters.database import database_adapter


class InfrastructureProvider(Provider):
    """인프라 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정 - 모든 프로바이더에 적용
    scope = Scope.APP
    
    # 간단한 의존성은 속성으로 직접 등록
    message_repository = provide(MessageRepository)
    llm_client = provide(LLMClient)
    embedding_client = provide(EmbeddingClient)
    api_client = provide(APIClient)
    
    # 비동기 및 정리 로직이 필요한 의존성은 여전히 메서드로 제공
    @provide
    async def database(self) -> AsyncIterator[None]:
        # 데이터베이스 연결 설정 (AsyncIterator를 사용하여 정리 로직도 추가)
        await database_adapter.connect()
        yield
        # 컨테이너가 종료될 때 데이터베이스 연결도 종료
        await database_adapter.disconnect()


class ServiceProvider(Provider):
    """서비스 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정
    scope = Scope.APP
    
    # 단순한 서비스는 직접 속성으로 제공
    random_responder = provide(RandomResponderService)
    
    # 복잡한 서비스도 recursive=True를 사용하면 자동으로 의존성 해결 가능
    # 생성자의 타입 힌트를 통해 자동으로 의존성 주입
    message_service = provide(MessageService, recursive=True)
    conversation_service = provide(ConversationService, recursive=True)


# 글로벌 컨테이너 - main.py에서 사용
# 다른 파일에서는 이 컨테이너를 직접 import하여 사용
# 예: from naraninyeo.di import container
container = make_async_container(
    InfrastructureProvider(),
    ServiceProvider()
)
