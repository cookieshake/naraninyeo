"""Dependency wiring for the simplified chat stack."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient

from naraninyeo.app.context import ReplyContextBuilder
from naraninyeo.app.pipeline import (
    DEFAULT_RETRIEVAL_TIMEOUT,
    DEFAULT_STEPS,
    ChatPipeline,
    PipelineStep,
    PipelineTools,
    StepRegistry,
    default_step_order,
)
from naraninyeo.app.reply import NewMessageHandler, ReplyGenerator
from naraninyeo.assistant.llm_toolkit import LLMToolFactory
from naraninyeo.assistant.memory_management import (
    ConversationMemoryExtractor,
    MemoryStore,
    MongoMemoryStore,
)
from naraninyeo.assistant.message_repository import (
    MessageRepository,
    MongoQdrantMessageRepository,
)
from naraninyeo.assistant.retrieval import (
    ChatHistoryStrategy,
    HeuristicRetrievalRanker,
    NaverSearchStrategy,
    RetrievalExecutor,
    RetrievalPlanner,
    RetrievalPostProcessor,
    RetrievalResultCollectorFactory,
    WikipediaStrategy,
)
from naraninyeo.embeddings import Qwen306TextEmbedder, TextEmbedder
from naraninyeo.plugins import AppRegistry, ChatMiddleware, PluginManager
from naraninyeo.settings import Settings


class MainProvider(Provider):
    scope = Scope.APP

    @provide
    async def settings(self) -> Settings:
        return Settings()

    @provide
    async def app_registry(self, settings: Settings) -> AppRegistry:
        registry = AppRegistry()
        # 설정에 명시된 플러그인 모듈을 로드해 LLM/검색 전략을 확장한다.
        PluginManager(settings).load_plugins(registry)
        return registry

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
    reply_generator = provide(source=ReplyGenerator, provides=ReplyGenerator)

    @provide
    async def mongo_message_repository(
        self,
        mongo_database: AsyncIOMotorDatabase,
        qdrant_client: AsyncQdrantClient,
        text_embedder: TextEmbedder,
    ) -> MongoQdrantMessageRepository:
        return MongoQdrantMessageRepository(mongo_database, qdrant_client, text_embedder)

    @provide
    async def message_repository(self, mongo_message_repository: MongoQdrantMessageRepository) -> MessageRepository:
        return mongo_message_repository

    @provide
    async def llm_tool_factory(self, settings: Settings, app_registry: AppRegistry) -> LLMToolFactory:
        return LLMToolFactory(settings, provider_registry=app_registry.llm_provider_registry)

    retrieval_planner = provide(source=RetrievalPlanner, provides=RetrievalPlanner)
    result_collector_factory = provide(source=RetrievalResultCollectorFactory, provides=RetrievalResultCollectorFactory)
    retrieval_ranker = provide(source=HeuristicRetrievalRanker, provides=HeuristicRetrievalRanker)
    retrieval_post_processor = provide(source=RetrievalPostProcessor, provides=RetrievalPostProcessor)

    @provide
    async def mongo_memory_store(self, mongo_database: AsyncIOMotorDatabase) -> MongoMemoryStore:
        return MongoMemoryStore(mongo_database)

    @provide
    async def memory_store(self, mongo_memory_store: MongoMemoryStore) -> MemoryStore:
        return mongo_memory_store

    @provide
    async def memory_extractor(
        self,
        settings: Settings,
        llm_tool_factory: LLMToolFactory,
    ) -> ConversationMemoryExtractor:
        return ConversationMemoryExtractor(settings, llm_tool_factory)

    naver_search_strategy = provide(source=NaverSearchStrategy, provides=NaverSearchStrategy)
    chat_history_strategy = provide(source=ChatHistoryStrategy, provides=ChatHistoryStrategy)
    wikipedia_strategy = provide(source=WikipediaStrategy, provides=WikipediaStrategy)

    @provide
    async def retrieval_executor(
        self,
        settings: Settings,
        naver_search_strategy: NaverSearchStrategy,
        chat_history_strategy: ChatHistoryStrategy,
        wikipedia_strategy: WikipediaStrategy,
        app_registry: AppRegistry,
        llm_tool_factory: LLMToolFactory,
    ) -> RetrievalExecutor:
        executor = RetrievalExecutor(max_concurrency=settings.RETRIEVAL_MAX_CONCURRENCY)
        enabled = set(getattr(settings, "ENABLED_RETRIEVAL_STRATEGIES", []))
        # 설정으로 켜둔 전략만 등록하고, 나머지는 비활성화 상태로 둔다.
        if "naver_search" in enabled:
            executor.register(naver_search_strategy)
        if "chat_history" in enabled:
            executor.register(chat_history_strategy)
        if "wikipedia" in enabled:
            executor.register(wikipedia_strategy)
        for builder in app_registry.retrieval_strategy_builders:
            try:
                strategy = builder(settings, llm_tool_factory)
                executor.register(strategy)
            except Exception as exc:
                logging.warning("Failed to initialize a plugin retrieval strategy", exc_info=exc)
        return executor

    reply_context_builder = provide(source=ReplyContextBuilder, provides=ReplyContextBuilder)

    @provide
    async def middlewares(self, settings: Settings, app_registry: AppRegistry) -> list[ChatMiddleware]:
        middlewares: list[ChatMiddleware] = []
        for builder in app_registry.chat_middleware_builders:
            try:
                middlewares.append(builder(settings))
            except Exception as exc:
                logging.warning("Failed to initialize a plugin chat middleware", exc_info=exc)
        return middlewares

    @provide
    async def pipeline_tools(
        self,
        settings: Settings,
        message_repository: MessageRepository,
        memory_store: MemoryStore,
        memory_extractor: ConversationMemoryExtractor,
        retrieval_planner: RetrievalPlanner,
        retrieval_executor: RetrievalExecutor,
        result_collector_factory: RetrievalResultCollectorFactory,
        retrieval_post_processor: RetrievalPostProcessor,
        reply_generator: ReplyGenerator,
        reply_context_builder: ReplyContextBuilder,
        middlewares: list[ChatMiddleware],
    ) -> PipelineTools:
        timeout = getattr(settings, "RETRIEVAL_EXECUTION_TIMEOUT", DEFAULT_RETRIEVAL_TIMEOUT)
        return PipelineTools(
            settings=settings,
            message_repository=message_repository,
            memory_store=memory_store,
            memory_extractor=memory_extractor,
            retrieval_planner=retrieval_planner,
            retrieval_executor=retrieval_executor,
            retrieval_collector_factory=result_collector_factory,
            retrieval_post_processor=retrieval_post_processor,
            reply_generator=reply_generator,
            context_builder=reply_context_builder,
            middlewares=middlewares,
            retrieval_timeout_seconds=float(timeout),
        )

    @provide
    async def step_registry(
        self,
        pipeline_tools: PipelineTools,
        app_registry: AppRegistry,
    ) -> StepRegistry:
        library = StepRegistry()
        library.register_many(DEFAULT_STEPS)
        for name, builder in app_registry.pipeline_step_builders.items():
            try:
                step = builder(pipeline_tools)
                if not isinstance(step, PipelineStep):
                    raise TypeError("Pipeline step builders must return PipelineStep")
                library.register(step)
            except Exception as exc:
                logging.warning("Failed to register plugin pipeline step '%s'", name, exc_info=exc)
        return library

    @provide
    async def chat_pipeline(
        self,
        pipeline_tools: PipelineTools,
        step_registry: StepRegistry,
    ) -> ChatPipeline:
        settings = pipeline_tools.settings
        order = settings.PIPELINE or default_step_order()
        return ChatPipeline(
            tools=pipeline_tools,
            step_registry=step_registry,
            step_order=order,
            reply_saver=pipeline_tools.message_repository.save,
        )

    @provide
    async def new_message_handler(self, chat_pipeline: ChatPipeline) -> NewMessageHandler:
        return NewMessageHandler(chat_pipeline)


container = make_async_container(MainProvider())

__all__ = ["container", "MainProvider"]
