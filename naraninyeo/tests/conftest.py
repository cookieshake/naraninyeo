import time
from collections.abc import AsyncIterator
from typing import Iterator

import httpx
import pytest_asyncio
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from qdrant_client.http.models import Distance, VectorParams
from testcontainers.core.container import DockerContainer
from testcontainers.mongodb import MongoDbContainer
from testcontainers.qdrant import QdrantContainer

from naraninyeo.di import MainProvider
from naraninyeo.infrastructure.settings import Settings


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


@pytest_asyncio.fixture(scope="package")
async def test_container() -> AsyncIterator[AsyncContainer]:
    container = make_async_container(MainProvider(), TestProvider())
    yield container
    await container.close()
