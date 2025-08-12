"""
테스트 전용 설정과 공통 fixture를 제공하는 모듈
모든 테스트 파일에서 공유하여 사용
"""
from typing import AsyncGenerator, Iterator
import time
import httpx
import pytest_asyncio

from testcontainers.core.container import DockerContainer
from testcontainers.mongodb import MongoDbContainer
from testcontainers.qdrant import QdrantContainer
from testcontainers.core.waiting_utils import wait_container_is_ready
from dishka import Provider, Scope, provide, Container
from qdrant_client.http.models import VectorParams, Distance

from naraninyeo.adapters.clients import EmbeddingClient
from naraninyeo.core.config import Settings
from naraninyeo.di import make_async_container, InfrastructureProvider, ServiceProvider

class LlamaCppContainer(DockerContainer):
    """LlamaCpp 테스트 컨테이너를 위한 클래스"""
    def __init__(self):
        super().__init__(
            image="ghcr.io/ggml-org/llama.cpp:server",
            env={
                "LLAMA_CACHE": "/tmp/llamacpp/cache"
            },
            command=[
                "--host", "0.0.0.0",
                "--port", "8080",
                "--parallel", "5",
                "--hf-repo", "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0",
                "--embedding",
                "--pooling", "last",
                "--ubatch-size", "8192"
                "--verbose-prompt"
            ]
        )
        self.with_exposed_ports(8080)
        self.with_volume_mapping("/tmp/llamacpp/cache", "/tmp/llamacpp/cache", mode="rw")

    def get_connection_url(self) -> str:
        return f"http://{self.get_container_host_ip()}:{self.get_exposed_port(8080)}"

class TestContainerProvider(Provider):
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
        qdrant = QdrantContainer()
        qdrant.start()
        yield qdrant
        qdrant.stop()

    @provide
    def llamacpp_container(self) -> Iterator[LlamaCppContainer]:
        """LlamaCpp 테스트 컨테이너를 제공하는 fixture"""
        llamacpp = LlamaCppContainer()
        llamacpp.start()
        for _ in range(100):
            with httpx.Client() as client:
                time.sleep(1)
                response = client.get(f"{llamacpp.get_connection_url()}/health")
                if response.status_code == 200:
                    break
        yield llamacpp
        llamacpp.stop()

class TestProvider(InfrastructureProvider):
    """테스트용 제공자"""
    @provide(override=True)
    async def settings(
        self,
        mongodb_container: MongoDbContainer,
        llamacpp_container: LlamaCppContainer,
        qdrant_container: QdrantContainer
    ) -> Settings:
        settings = Settings()
        settings = settings.model_copy(update={
            "MONGODB_URL": mongodb_container.get_connection_url(),
            "LLAMA_CPP_MODELS_URL": llamacpp_container.get_connection_url(),
            "QDRANT_URL": f"http://{qdrant_container.rest_host_address}"
        })

        client = qdrant_container.get_client()
        client.create_collection("naraninyeo-messages", vectors_config=VectorParams(size=1024, distance=Distance.COSINE))

        return settings
    
container = make_async_container(
    InfrastructureProvider(),
    ServiceProvider(),
    TestContainerProvider(),
    TestProvider(),
)

@pytest_asyncio.fixture(scope="module")
async def test_container() -> AsyncGenerator[Container]:
    """테스트용 DI 컨테이너를 제공하는 fixture"""
    # 테스트용 DI 컨테이너 생성
    yield container
    # 테스트 종료 후 컨테이너 정리
    await container.close()
