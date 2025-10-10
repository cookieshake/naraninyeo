"""Optional testcontainer wiring for local end-to-end testing."""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
from dishka import Scope, make_async_container, provide

from naraninyeo.container import MainProvider
from naraninyeo.settings import Settings

try:  # pragma: no cover - optional dependency
    from testcontainers.core.container import DockerContainer
    from testcontainers.mongodb import MongoDbContainer
    from testcontainers.qdrant import QdrantContainer
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError(
        "testcontainers package is required for local integration testing. "
        "Install it via `pip install 'testcontainers>=4.12.0'` or include the 'dev' dependency group."
    ) from exc

from qdrant_client.http.models import Distance, VectorParams

from dishka import Provider


class LlamaCppContainer(DockerContainer):
    """Llama.cpp embedding server test container (embeddings only)."""

    def __init__(self) -> None:  # pragma: no cover - infra bootstrap
        super().__init__(
            image="ghcr.io/ggml-org/llama.cpp:server",
            command=" ".join(
                [
                    "--host 0.0.0.0",
                    "--port 8080",
                    "--hf-repo Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0",
                    "--embedding",
                    "--pooling last",
                    "--ubatch-size 8192",
                    "--parallel 5",
                    "--verbose-prompt",
                ]
            ),
            env={"LLAMA_CACHE": "/tmp/llamacpp/cache"},
        )
        self.with_exposed_ports(8080)
        self.with_volume_mapping("/tmp/llamacpp/cache", "/tmp/llamacpp/cache", mode="rw")

    def get_connection_url(self) -> str:  # pragma: no cover
        return f"http://{self.get_container_host_ip()}:{self.get_exposed_port(8080)}"


class TestProvider(Provider):
    scope = Scope.APP

    @provide
    def mongodb_container(self) -> Iterator[MongoDbContainer]:  # pragma: no cover
        mongo = MongoDbContainer()
        mongo.start()
        try:
            yield mongo
        finally:
            mongo.stop()

    @provide
    def qdrant_container(self) -> Iterator[QdrantContainer]:  # pragma: no cover
        qdrant = QdrantContainer(image="qdrant/qdrant:v1.15.1")
        qdrant.start()
        try:
            client = qdrant.get_client()
            client.create_collection(
                collection_name="naraninyeo-messages",
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            yield qdrant
        finally:
            qdrant.stop()

    @provide
    def llamacpp_container(self) -> Iterator[LlamaCppContainer]:  # pragma: no cover
        llamacpp = LlamaCppContainer()
        llamacpp.start()
        try:
            for _ in range(50):
                try:
                    with httpx.Client() as sync_client:
                        resp = sync_client.get(f"{llamacpp.get_connection_url()}/health")
                        if resp.status_code == 200:
                            break
                except httpx.RequestError:
                    pass
                time.sleep(2)
            yield llamacpp
        finally:
            llamacpp.stop()

    @provide(override=True)
    async def settings(
        self,
        mongodb_container: MongoDbContainer,
        llamacpp_container: LlamaCppContainer,
        qdrant_container: QdrantContainer,
    ) -> Settings:  # pragma: no cover
        base = Settings()
        return base.model_copy(
            update={
                "MONGODB_URL": mongodb_container.get_connection_url(),
                "LLAMA_CPP_EMBEDDINGS_URL": llamacpp_container.get_connection_url(),
                "QDRANT_URL": f"http://{qdrant_container.rest_host_address}",
            }
        )


async def make_test_container():  # pragma: no cover - helper
    """Build a Dishka container with testcontainers-provided infrastructure."""

    return make_async_container(MainProvider(), TestProvider())
