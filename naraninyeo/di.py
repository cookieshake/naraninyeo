"""
Dishka 기반 의존성 주입 컨테이너 설정
- 간소화된 Provide 사용 방식 적용
"""

import time
from collections.abc import AsyncIterator
from typing import Iterator

import httpx
from dishka import Provider, Scope, make_async_container, provide
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, VectorParams
from testcontainers.core.container import DockerContainer
from testcontainers.mongodb import MongoDbContainer
from testcontainers.qdrant import QdrantContainer

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


class LlamaCppContainer(DockerContainer):
    """LlamaCpp 테스트 컨테이너를 위한 클래스"""

    def __init__(self):
        super().__init__(
            image="ghcr.io/ggml-org/llama.cpp:server",
            env={"LLAMA_CACHE": "/tmp/llamacpp/cache"},
            command=" ".join(
                [
                    "--host 0.0.0.0",
                    "--port 8080",
                    "--parallel 5",
                    "--hf-repo Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0",
                    "--embedding",
                    "--pooling last",
                    "--ubatch-size 8192",
                    "--verbose-prompt",
                ]
            ),
        )
        self.with_exposed_ports(8080)
        self.with_volume_mapping("/tmp/llamacpp/cache", "/tmp/llamacpp/cache", mode="rw")

    def get_connection_url(self) -> str:
        return f"http://{self.get_container_host_ip()}:{self.get_exposed_port(8080)}"


class TestProvider(Provider):
    scope = Scope.APP

    @provide
    def mongodb_container(self) -> Iterator[MongoDbContainer]:
        """MongoDB 테스트 컨테이너를 제공하는 fixture"""
        mongo = MongoDbContainer()
        mongo.start()
        yield mongo
        mongo.stop()

    @provide
    def qdrant_container(self) -> Iterator[QdrantContainer]:
        """Qdrant 테스트 컨테이너를 제공하는 fixture"""
        qdrant = QdrantContainer(image="qdrant/qdrant:v1.15.1")
        qdrant.start()
        client = qdrant.get_client()
        client.create_collection(
            "naraninyeo-messages", vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
        )
        yield qdrant
        qdrant.stop()

    @provide
    def llamacpp_container(self) -> Iterator[LlamaCppContainer]:
        """LlamaCpp 테스트 컨테이너를 제공하는 fixture"""
        llamacpp = LlamaCppContainer()
        llamacpp.start()
        for _ in range(50):
            with httpx.Client() as client:
                try:
                    response = client.get(f"{llamacpp.get_connection_url()}/health")
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(2)
        yield llamacpp
        llamacpp.stop()

    @provide(override=True)
    async def settings(
        self,
        mongodb_container: MongoDbContainer,
        llamacpp_container: LlamaCppContainer,
        qdrant_container: QdrantContainer,
    ) -> Settings:
        settings = Settings()
        settings = settings.model_copy(
            update={
                "MONGODB_URL": mongodb_container.get_connection_url(),
                "LLAMA_CPP_EMBEDDINGS_URL": llamacpp_container.get_connection_url(),
                "QDRANT_URL": f"http://{qdrant_container.rest_host_address}",
            }
        )

        return settings


container = make_async_container(MainProvider())
