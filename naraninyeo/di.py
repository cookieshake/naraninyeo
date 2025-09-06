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
from naraninyeo.domain.usecase.memory import MemoryUseCase
from naraninyeo.domain.usecase.reply import ReplyUseCase
from naraninyeo.domain.usecase.retrieval import RetrievalUseCase
from naraninyeo.infrastructure.embedding import Qwen306TextEmbedder, TextEmbedder
from naraninyeo.domain.gateway.memory import MemoryExtractor, MemoryStore
from naraninyeo.infrastructure.memory.extractor import RuleBasedMemoryExtractor
from naraninyeo.infrastructure.memory.extractor_llm import LLMMemoryExtractor
from naraninyeo.infrastructure.memory.store import MongoMemoryStore
from naraninyeo.infrastructure.message import MongoQdrantMessageRepository
from naraninyeo.infrastructure.reply import ReplyGeneratorAgent
from naraninyeo.infrastructure.retrieval.plan_executor import LocalPlanExecutor
from naraninyeo.infrastructure.retrieval.plan_strategy.history import ChatHistoryStrategy
from naraninyeo.infrastructure.retrieval.plan_strategy.naver_search import NaverSearchStrategy
from naraninyeo.infrastructure.retrieval.plan_strategy.wikipedia import WikipediaStrategy
from naraninyeo.infrastructure.retrieval.planner import RetrievalPlannerAgent
from naraninyeo.infrastructure.retrieval.result import InMemoryRetrievalResultCollectorFactory
from naraninyeo.infrastructure.retrieval.post import DefaultRetrievalPostProcessor
from naraninyeo.infrastructure.retrieval.rank import HeuristicRetrievalRanker
from naraninyeo.infrastructure.settings import Settings
from naraninyeo.domain.application.context_builder import ReplyContextBuilder
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.domain.gateway.retrieval_post import RetrievalPostProcessor
from naraninyeo.domain.gateway.retrieval_rank import RetrievalRanker


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
    llm_agent_factory = provide(source=LLMAgentFactory, provides=LLMAgentFactory)
    retrieval_planner = provide(source=RetrievalPlannerAgent, provides=RetrievalPlanner)
    result_collector_factory = provide(
        source=InMemoryRetrievalResultCollectorFactory, provides=RetrievalResultCollectorFactory
    )
    retrieval_ranker = provide(source=HeuristicRetrievalRanker, provides=RetrievalRanker)
    retrieval_post_processor = provide(source=DefaultRetrievalPostProcessor, provides=RetrievalPostProcessor)

    # Memory
    @provide
    async def memory_store(self, mongo_database: AsyncIOMotorDatabase) -> MemoryStore:
        return MongoMemoryStore(mongo_database)

    @provide
    async def memory_extractor(self, settings: Settings, llm_agent_factory: LLMAgentFactory) -> MemoryExtractor:
        if settings.ENABLE_LLM_MEMORY:
            return LLMMemoryExtractor(settings, llm_agent_factory)
        return RuleBasedMemoryExtractor(ttl_hours=settings.MEMORY_TTL_HOURS)

    naver_search_strategy = provide(source=NaverSearchStrategy, provides=NaverSearchStrategy)
    chat_history_strategy = provide(source=ChatHistoryStrategy, provides=ChatHistoryStrategy)
    wikipedia_strategy = provide(source=WikipediaStrategy, provides=WikipediaStrategy)

    @provide
    async def retrieval_plan_executor(
        self,
        settings: Settings,
        naver_search_strategy: NaverSearchStrategy,
        chat_history_strategy: ChatHistoryStrategy,
        wikipedia_strategy: WikipediaStrategy,
    ) -> RetrievalPlanExecutor:
        executor = LocalPlanExecutor(max_concurrency=settings.RETRIEVAL_MAX_CONCURRENCY)
        enabled = set(getattr(settings, "ENABLED_RETRIEVAL_STRATEGIES", []))
        if "naver_search" in enabled:
            executor.register_strategy(naver_search_strategy)
        if "chat_history" in enabled:
            executor.register_strategy(chat_history_strategy)
        if "wikipedia" in enabled:
            executor.register_strategy(wikipedia_strategy)
        return executor

    message_use_case = provide(source=MessageUseCase, provides=MessageUseCase)
    memory_use_case = provide(source=MemoryUseCase, provides=MemoryUseCase)
    reply_use_case = provide(source=ReplyUseCase, provides=ReplyUseCase)
    retrieval_use_case = provide(source=RetrievalUseCase, provides=RetrievalUseCase)

    reply_context_builder = provide(source=ReplyContextBuilder, provides=ReplyContextBuilder)

    new_message_handler = provide(source=NewMessageHandler, provides=NewMessageHandler)


container = make_async_container(MainProvider())
