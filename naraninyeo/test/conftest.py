import time
from typing import AsyncIterable, Iterator

import httpx
import pytest
from asyncpg import create_pool
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer

from naraninyeo.api.infrastructure.repository.vchord_init import VchordInit
from naraninyeo.core.container import ConnectionProvider, RepositoryProvider, UtilProvider
from naraninyeo.core.settings import Settings


class LlamaCppContainer(DockerContainer):
    """Llama.cpp embedding server test container (embeddings only)."""

    def __init__(self) -> None:  # pragma: no cover - infra bootstrap
        super().__init__(
            image="ghcr.io/ggml-org/llama.cpp:server-b6881",
            command=" ".join(
                [
                    "--host 0.0.0.0",
                    "--port 8080",
                    "--hf-repo ggml-org/embeddinggemma-300m-qat-q8_0-GGUF:Q8_0",
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

    @provide
    def vchord_container(self) -> Iterator[PostgresContainer]:  # pragma: no cover
        vchord = PostgresContainer(
            image="tensorchord/vchord-suite:pg18-20251001",
            driver=""
        )
        vchord.start()
        try:
            yield vchord
        finally:
            vchord.stop()

    @provide(override=True)
    async def settings(
        self,
        llamacpp_container: LlamaCppContainer,
        vchord_container: PostgresContainer,
    ) -> Settings:  # pragma: no cover
        base = Settings()
        copy = base.model_copy()
        copy.DEBUG_MODE = True
        copy.LLAMA_CPP_EMBEDDINGS_URI = llamacpp_container.get_connection_url()
        copy.VCHORD_URI = vchord_container.get_connection_url()
        return copy


async def _test_container() -> AsyncContainer:
    container = make_async_container(
        TestProvider(),
        ConnectionProvider(),
        RepositoryProvider(),
        UtilProvider(),
    )
    settings = await container.get(Settings)
    temp_pool = await create_pool(dsn=settings.VCHORD_URI)
    try:
        await VchordInit(temp_pool).run()
    finally:
        await temp_pool.close()
    return container

@pytest.fixture
async def test_container() -> AsyncIterable[AsyncContainer]:
    container = await _test_container()
    yield container
    await container.close()

async def _test_app(test_container: AsyncContainer) -> FastAPI:
    from naraninyeo.api import create_app
    app = create_app()
    setup_dishka(test_container, app)
    return app

@pytest.fixture
async def test_app(test_container: AsyncContainer) -> FastAPI:
    return await _test_app(test_container)

def _test_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)

@pytest.fixture
def test_client(test_app: FastAPI) -> Iterator[TestClient]:
    with _test_client(test_app) as client:
        yield client
