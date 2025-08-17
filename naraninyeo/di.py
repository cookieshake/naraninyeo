"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""
from typing import Optional, Iterable
from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide, AnyOf
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient

from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.gateway.retrieval import RetrievalPlanner, RetrievalPlanExecutor
from naraninyeo.domain.usecase.message import MessageUseCase
from naraninyeo.domain.usecase.reply import ReplyUseCase
from naraninyeo.domain.usecase.retrieval import RetrievalUseCase
from naraninyeo.domain.application.new_message_handler import NewMessageHandler

from naraninyeo.infrastructure.settings import Settings
from naraninyeo.infrastructure.embedding import TextEmbedder, Qwen306TextEmbedder
from naraninyeo.infrastructure.message import MongoQdrantMessageRepository
from naraninyeo.infrastructure.reply import ReplyGeneratorAgent
from naraninyeo.infrastructure.retrieval import NaverSearchClient, RetrievalPlannerAgent, DefaultRetrievalPlanExecutor



class InfrastructureProvider(Provider):
    """인프라 의존성을 제공하는 프로바이더"""
    # 기본 스코프 설정 - 모든 프로바이더에 적용
    scope = Scope.APP
    
    @provide
    async def settings(self) -> Settings:
        return Settings()
    
    @provide
    async def mongo_database(self, settings: Settings) -> AsyncIterator[AsyncIOMotorDatabase]:
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client.get_database(settings.MONGODB_DB_NAME)
        yield db
        client.close()

    @provide
    async def qdrant_client(self, settings: Settings) -> AsyncIterator[AsyncQdrantClient]:
        client = AsyncQdrantClient(url=settings.QDRANT_URL)
        yield client
        await client.close()

    text_embedder = provide(source=Qwen306TextEmbedder, provides=TextEmbedder)
    naver_search_client = provide(source=NaverSearchClient, provides=NaverSearchClient)
    message_repository = provide(source=MongoQdrantMessageRepository, provides=MessageRepository)
    reply_generator = provide(source=ReplyGeneratorAgent, provides=ReplyGenerator)
    retrieval_planner = provide(source=RetrievalPlannerAgent, provides=RetrievalPlanner)
    retrieval_executor = provide(source=DefaultRetrievalPlanExecutor, provides=RetrievalPlanExecutor)

    message_use_case = provide(source=MessageUseCase, provides=MessageUseCase)
    reply_use_case = provide(source=ReplyUseCase, provides=ReplyUseCase)
    retrieval_use_case = provide(source=RetrievalUseCase, provides=RetrievalUseCase)

    new_message_handler = provide(source=NewMessageHandler, provides=NewMessageHandler)

container = make_async_container(
    InfrastructureProvider(),
)
