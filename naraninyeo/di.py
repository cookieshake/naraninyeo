"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient

from naraninyeo.domain.application.new_message_handler import NewMessageHandler
from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.gateway.retrieval import (
    RetrievalPlanExecutor,
    RetrievalPlanner,
    RetrievalResultCollectorFactory,
)
from naraninyeo.domain.usecase.message import MessageUseCase
from naraninyeo.domain.usecase.reply import ReplyUseCase
from naraninyeo.domain.usecase.retrieval import RetrievalUseCase
from naraninyeo.infrastructure.embedding import Qwen306TextEmbedder, TextEmbedder
from naraninyeo.infrastructure.message import MongoQdrantMessageRepository
from naraninyeo.infrastructure.reply import ReplyGeneratorAgent
from naraninyeo.infrastructure.retrieval.plan_executor import LocalPlanExecutor
from naraninyeo.infrastructure.retrieval.plan_strategy.history import ChatHistoryStrategy
from naraninyeo.infrastructure.retrieval.plan_strategy.naver_search import NaverSearchStrategy
from naraninyeo.infrastructure.retrieval.planner import RetrievalPlannerAgent
from naraninyeo.infrastructure.retrieval.result import InMemoryRetrievalResultCollectorFactory
from naraninyeo.infrastructure.settings import Settings


class MainProvider(Provider):
    scope = Scope.APP

    @provide
    async def settings(self) -> Settings:
        return Settings()

    @provide
    async def mongo_database(self, settings: Settings) -> AsyncIterator[AsyncIOMotorDatabase]:
        client = AsyncIOMotorClient(settings.MONGODB_URL, tz_aware=True)
        db = client.get_database(settings.MONGODB_DB_NAME)
        yield db
        client.close()

    @provide
    async def qdrant_client(self, settings: Settings) -> AsyncIterator[AsyncQdrantClient]:
        client = AsyncQdrantClient(url=settings.QDRANT_URL)
        yield client
        await client.close()

    text_embedder = provide(source=Qwen306TextEmbedder, provides=TextEmbedder)
    message_repository = provide(source=MongoQdrantMessageRepository, provides=MessageRepository)
    reply_generator = provide(source=ReplyGeneratorAgent, provides=ReplyGenerator)
    retrieval_planner = provide(source=RetrievalPlannerAgent, provides=RetrievalPlanner)
    result_collector_factory = provide(
        source=InMemoryRetrievalResultCollectorFactory, provides=RetrievalResultCollectorFactory
    )

    naver_search_strategy = provide(source=NaverSearchStrategy, provides=NaverSearchStrategy)
    chat_history_strategy = provide(source=ChatHistoryStrategy, provides=ChatHistoryStrategy)

    @provide
    async def retrieval_plan_executor(
        self, naver_search_strategy: NaverSearchStrategy, chat_history_strategy: ChatHistoryStrategy
    ) -> RetrievalPlanExecutor:
        executor = LocalPlanExecutor()
        executor.register_strategy(naver_search_strategy)
        executor.register_strategy(chat_history_strategy)
        return executor

    message_use_case = provide(source=MessageUseCase, provides=MessageUseCase)
    reply_use_case = provide(source=ReplyUseCase, provides=ReplyUseCase)
    retrieval_use_case = provide(source=RetrievalUseCase, provides=RetrievalUseCase)

    new_message_handler = provide(source=NewMessageHandler, provides=NewMessageHandler)

container = make_async_container(MainProvider())
