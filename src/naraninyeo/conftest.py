import time
from datetime import UTC, datetime
from typing import AsyncIterable, Iterator  # noqa: F401

import httpx
import pytest
from asyncpg import create_pool
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer

from naraninyeo.api.container import (
    AdapterProvider,
    ConnectionProvider,
    RepositoryProvider,
    UtilProvider,
)
from naraninyeo.core.interfaces import (
    BotRepository,
    Clock,
    FinanceSearch,
    IdGenerator,
    MemoryRepository,
    MessageRepository,
    NaverSearch,
    TextEmbedder,
    WebDocumentFetch,
)
from naraninyeo.core.models import (
    Attachment,
    Author,
    Bot,
    Channel,
    MemoryItem,
    Message,
    MessageContent,
    TenancyContext,
)
from naraninyeo.core.settings import Settings
from naraninyeo.infrastructure.repository.init_db import VchordInit
from naraninyeo.infrastructure.util.nanoid_generator import NanoidGenerator


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
        vchord = PostgresContainer(image="tensorchord/vchord-suite:pg17-20251101", driver="")
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
        copy.HTTP_SSL_VERIFY = False
        copy.LLAMA_CPP_EMBEDDINGS_URI = llamacpp_container.get_connection_url()
        copy.VCHORD_URI = vchord_container.get_connection_url()
        return copy


async def _test_container() -> AsyncContainer:
    container = make_async_container(
        TestProvider(),
        ConnectionProvider(),
        RepositoryProvider(),
        AdapterProvider(),
        UtilProvider(),
    )
    settings = await container.get(Settings)
    temp_pool = await create_pool(dsn=settings.VCHORD_URI)
    try:
        await VchordInit(temp_pool).run()
    finally:
        await temp_pool.close()
    return container


@pytest.fixture(scope="session")
async def test_container() -> AsyncIterable[AsyncContainer]:
    container = await _test_container()
    yield container
    await container.close()


async def _test_app(test_container: AsyncContainer) -> FastAPI:
    from naraninyeo.api import create_app

    app = create_app()
    setup_dishka(test_container, app)
    return app


@pytest.fixture(scope="session")
async def test_app(test_container: AsyncContainer) -> FastAPI:
    return await _test_app(test_container)


# Individual service fixtures (resolved from DI container)


@pytest.fixture(scope="session")
async def naver_search(test_container: AsyncContainer) -> NaverSearch:
    return await test_container.get(NaverSearch)


@pytest.fixture(scope="session")
async def finance_search(test_container: AsyncContainer) -> FinanceSearch:
    return await test_container.get(FinanceSearch)


@pytest.fixture(scope="session")
async def web_document_fetch(test_container: AsyncContainer) -> WebDocumentFetch:
    return await test_container.get(WebDocumentFetch)


@pytest.fixture(scope="session")
async def text_embedder(test_container: AsyncContainer) -> TextEmbedder:
    return await test_container.get(TextEmbedder)


@pytest.fixture(scope="session")
async def bot_repository(test_container: AsyncContainer) -> BotRepository:
    return await test_container.get(BotRepository)


@pytest.fixture(scope="session")
async def memory_repository(test_container: AsyncContainer) -> MemoryRepository:
    return await test_container.get(MemoryRepository)


@pytest.fixture(scope="session")
async def message_repository(test_container: AsyncContainer) -> MessageRepository:
    return await test_container.get(MessageRepository)


@pytest.fixture(scope="session")
async def clock(test_container: AsyncContainer) -> Clock:
    return await test_container.get(Clock)


@pytest.fixture(scope="session")
async def id_generator(test_container: AsyncContainer) -> IdGenerator:
    return await test_container.get(IdGenerator)


# Test data factories


@pytest.fixture
def default_tctx() -> TenancyContext:
    return TenancyContext(tenant_id="test-tenant")


def _nanoid() -> str:
    return NanoidGenerator().generate_id()


@pytest.fixture
def make_bot():
    def _make(*, bot_id: str | None = None, bot_name: str = "테스트봇") -> Bot:
        return Bot(
            bot_id=bot_id or _nanoid(),
            bot_name=bot_name,
            author_id="author-1",
            created_at=datetime.now(UTC),
        )

    return _make


@pytest.fixture
def make_message():
    def _make(
        *,
        message_id: str | None = None,
        text: str = "안녕하세요",
        channel_id: str = "channel-1",
        author_id: str = "user-1",
        author_name: str = "테스터",
        timestamp: datetime | None = None,
        attachments: list[Attachment] | None = None,
    ) -> Message:
        return Message(
            message_id=message_id or _nanoid(),
            channel=Channel(channel_id=channel_id, channel_name="테스트채널"),
            author=Author(author_id=author_id, author_name=author_name),
            content=MessageContent(text=text, attachments=attachments or []),
            timestamp=timestamp or datetime.now(UTC),
        )

    return _make


@pytest.fixture
def make_memory_item():
    def _make(
        *,
        memory_id: str | None = None,
        bot_id: str = "bot-1",
        channel_id: str = "channel-1",
        kind: str = "short_term",
        content: str = "테스트 메모리",
        expires_at: datetime | None = None,
    ) -> MemoryItem:
        now = datetime.now(UTC)
        return MemoryItem(
            memory_id=memory_id or _nanoid(),
            bot_id=bot_id,
            channel_id=channel_id,
            kind=kind,  # type: ignore[arg-type]
            content=content,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

    return _make
