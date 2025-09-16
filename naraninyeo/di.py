"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient

from naraninyeo.core.application.new_message_handler import NewMessageHandler
from naraninyeo.core.contracts.memory import MemoryExtractor
from naraninyeo.core.middleware import ChatMiddleware
from naraninyeo.core.pipeline.runner import PipelineRunner
from naraninyeo.core.pipeline.steps import StepRegistry
from naraninyeo.core.plugins import AppRegistry, PluginManager
from naraninyeo.infrastructure.embedding import Qwen306TextEmbedder, TextEmbedder
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.memory.extractor_llm import LLMMemoryExtractor
from naraninyeo.infrastructure.memory.store import MongoMemoryStore
from naraninyeo.infrastructure.message import MongoQdrantMessageRepository
from naraninyeo.infrastructure.pipeline.context import ReplyContextBuilder
from naraninyeo.infrastructure.pipeline.steps import (
    AfterReplyStreamHookStep,
    AfterRetrievalHookStep,
    AttachReferencesStep,
    BeforeReplyStreamHookStep,
    BeforeRetrievalHookStep,
    BuildContextStep,
    ExecuteRetrievalStep,
    FinalizeBackgroundStep,
    IngestMemoryStep,
    PipelineDeps,
    PlanRetrievalStep,
    SaveIncomingMessageStep,
    ShouldReplyStep,
    StreamReplyStep,
    default_pipeline_order,
)
from naraninyeo.infrastructure.reply import ReplyGeneratorAgent
from naraninyeo.infrastructure.retrieval.plan_executor import LocalPlanExecutor
from naraninyeo.infrastructure.retrieval.plan_strategy.history import ChatHistoryStrategy
from naraninyeo.infrastructure.retrieval.plan_strategy.naver_search import NaverSearchStrategy
from naraninyeo.infrastructure.retrieval.plan_strategy.wikipedia import WikipediaStrategy
from naraninyeo.infrastructure.retrieval.planner import RetrievalPlannerAgent
from naraninyeo.infrastructure.retrieval.post import DefaultRetrievalPostProcessor
from naraninyeo.infrastructure.retrieval.rank import HeuristicRetrievalRanker
from naraninyeo.infrastructure.retrieval.result import InMemoryRetrievalResultCollectorFactory
from naraninyeo.infrastructure.settings import Settings


class MainProvider(Provider):
    scope = Scope.APP

    @provide
    async def settings(self) -> Settings:
        return Settings()

    @provide
    async def app_registry(self, settings: Settings) -> AppRegistry:
        """Create and populate the app registry via plugin discovery."""
        registry = AppRegistry()
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
    message_repository = provide(source=MongoQdrantMessageRepository, provides=MongoQdrantMessageRepository)
    reply_generator = provide(source=ReplyGeneratorAgent, provides=ReplyGeneratorAgent)

    @provide
    async def llm_agent_factory(self, settings: Settings, app_registry: AppRegistry) -> LLMAgentFactory:
        return LLMAgentFactory(settings, provider_registry=app_registry.llm_provider_registry)

    retrieval_planner = provide(source=RetrievalPlannerAgent, provides=RetrievalPlannerAgent)
    result_collector_factory = provide(
        source=InMemoryRetrievalResultCollectorFactory, provides=InMemoryRetrievalResultCollectorFactory
    )
    retrieval_ranker = provide(source=HeuristicRetrievalRanker, provides=HeuristicRetrievalRanker)
    retrieval_post_processor = provide(source=DefaultRetrievalPostProcessor, provides=DefaultRetrievalPostProcessor)

    # Memory
    @provide
    async def memory_store(self, mongo_database: AsyncIOMotorDatabase) -> MongoMemoryStore:
        return MongoMemoryStore(mongo_database)

    @provide
    async def memory_extractor(self, settings: Settings, llm_agent_factory: LLMAgentFactory) -> MemoryExtractor:
        return LLMMemoryExtractor(settings, llm_agent_factory)

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
        app_registry: AppRegistry,
        llm_agent_factory: LLMAgentFactory,
    ) -> LocalPlanExecutor:
        executor = LocalPlanExecutor(max_concurrency=settings.RETRIEVAL_MAX_CONCURRENCY)
        enabled = set(getattr(settings, "ENABLED_RETRIEVAL_STRATEGIES", []))
        if "naver_search" in enabled:
            executor.register_strategy(naver_search_strategy)
        if "chat_history" in enabled:
            executor.register_strategy(chat_history_strategy)
        if "wikipedia" in enabled:
            executor.register_strategy(wikipedia_strategy)
        # Load plugin-provided retrieval strategies
        for builder in app_registry.retrieval_strategy_builders:
            try:
                strategy = builder(settings, llm_agent_factory)
                executor.register_strategy(strategy)
            except Exception as e:
                # Avoid failing startup if a plugin misbehaves
                import logging

                logging.warning("Failed to initialize a plugin retrieval strategy", exc_info=e)
        return executor

    reply_context_builder = provide(source=ReplyContextBuilder, provides=ReplyContextBuilder)

    @provide
    async def middlewares(self, settings: Settings, app_registry: AppRegistry) -> list[ChatMiddleware]:
        mws: list[ChatMiddleware] = []
        for builder in app_registry.chat_middleware_builders:
            try:
                mws.append(builder(settings))
            except Exception as e:
                import logging

                logging.warning("Failed to initialize a plugin chat middleware", exc_info=e)
        return mws

    @provide
    async def pipeline_deps(
        self,
        settings: Settings,
        message_repository: MongoQdrantMessageRepository,
        memory_store: MongoMemoryStore,
        memory_extractor: MemoryExtractor,
        retrieval_planner: RetrievalPlannerAgent,
        retrieval_plan_executor: LocalPlanExecutor,
        result_collector_factory: InMemoryRetrievalResultCollectorFactory,
        retrieval_post_processor: DefaultRetrievalPostProcessor,
        reply_generator: ReplyGeneratorAgent,
        reply_context_builder: ReplyContextBuilder,
        middlewares: list[ChatMiddleware],
    ) -> PipelineDeps:
        return PipelineDeps(
            settings=settings,
            message_repository=message_repository,
            memory_store=memory_store,
            memory_extractor=memory_extractor,
            retrieval_planner=retrieval_planner,
            retrieval_executor=retrieval_plan_executor,
            retrieval_collector_factory=result_collector_factory,
            retrieval_post_processor=retrieval_post_processor,
            reply_generator=reply_generator,
            context_builder=reply_context_builder,
            middlewares=middlewares,
        )

    @provide
    async def pipeline_step_registry(self, pipeline_deps: PipelineDeps, app_registry: AppRegistry) -> StepRegistry:
        registry = StepRegistry()
        # Built-in steps
        for step in (
            SaveIncomingMessageStep(pipeline_deps),
            IngestMemoryStep(pipeline_deps),
            ShouldReplyStep(pipeline_deps),
            BuildContextStep(pipeline_deps),
            BeforeRetrievalHookStep(pipeline_deps),
            PlanRetrievalStep(pipeline_deps),
            ExecuteRetrievalStep(pipeline_deps),
            AfterRetrievalHookStep(pipeline_deps),
            AttachReferencesStep(pipeline_deps),
            BeforeReplyStreamHookStep(pipeline_deps),
            StreamReplyStep(pipeline_deps),
            AfterReplyStreamHookStep(pipeline_deps),
            FinalizeBackgroundStep(pipeline_deps),
        ):
            registry.register(step)

        # Plugin-provided steps
        for name, builder in app_registry.pipeline_step_builders.items():
            try:
                registry.register(builder(pipeline_deps))
            except Exception as e:
                import logging

                logging.warning(f"Failed to register plugin pipeline step '{name}'", exc_info=e)
        return registry

    @provide
    async def pipeline_runner(
        self,
        settings: Settings,
        message_repository: MongoQdrantMessageRepository,
        pipeline_step_registry: StepRegistry,
        middlewares: list[ChatMiddleware],
    ) -> PipelineRunner:
        order = settings.PIPELINE or default_pipeline_order()
        return PipelineRunner(
            settings=settings,
            step_registry=pipeline_step_registry,
            step_order=order,
            middlewares=middlewares,
            reply_saver=message_repository.save,
        )

    @provide
    async def new_message_handler(self, pipeline_runner: PipelineRunner) -> NewMessageHandler:
        return NewMessageHandler(pipeline_runner)


container = make_async_container(MainProvider())
