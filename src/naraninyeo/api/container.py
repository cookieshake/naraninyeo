from collections.abc import AsyncIterable

import httpx
from asyncpg import Pool, create_pool
from dishka import Provider, Scope, make_async_container, provide

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
from naraninyeo.core.settings import Settings
from naraninyeo.infrastructure.adapter.finance_search import FinanceSearchClient
from naraninyeo.infrastructure.adapter.llamacpp_gemma_embedder import LlamaCppGemmaEmbedder
from naraninyeo.infrastructure.adapter.naver_search import NaverSearchClient
from naraninyeo.infrastructure.adapter.web_document import WebDocumentFetcher
from naraninyeo.infrastructure.repository.bot import VchordBotRepository
from naraninyeo.infrastructure.repository.memory import VchordMemoryRepository
from naraninyeo.infrastructure.repository.message import VchordMessageRepository
from naraninyeo.infrastructure.util.nanoid_generator import NanoidGenerator
from naraninyeo.infrastructure.util.simple_clock import SimpleClock


class CoreProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return Settings()


class ConnectionProvider(Provider):
    scope = Scope.APP

    @provide
    async def database_pool(self, settings: Settings) -> AsyncIterable[Pool]:
        # Rely on asyncpg choosing the active loop so the pool stays usable across drivers like AnyIO.
        pool = await create_pool(dsn=settings.VCHORD_URI, min_size=5, max_size=20, command_timeout=30.0)
        yield pool
        await pool.close()

    @provide
    async def http_client(self) -> AsyncIterable[httpx.AsyncClient]:
        async with httpx.AsyncClient() as client:
            yield client


class RepositoryProvider(Provider):
    scope = Scope.APP

    bot_repository = provide(source=VchordBotRepository, provides=BotRepository)
    memory_repository = provide(source=VchordMemoryRepository, provides=MemoryRepository)
    message_repository = provide(source=VchordMessageRepository, provides=MessageRepository)


class AdapterProvider(Provider):
    scope = Scope.APP

    naver_search = provide(source=NaverSearchClient, provides=NaverSearch)
    finance_search = provide(source=FinanceSearchClient, provides=FinanceSearch)
    web_document_fetch = provide(source=WebDocumentFetcher, provides=WebDocumentFetch)


class UtilProvider(Provider):
    scope = Scope.APP

    clock = provide(source=SimpleClock, provides=Clock)
    id_generator = provide(source=NanoidGenerator, provides=IdGenerator)
    text_embedder = provide(source=LlamaCppGemmaEmbedder, provides=TextEmbedder)


container = make_async_container(
    CoreProvider(),
    ConnectionProvider(),
    RepositoryProvider(),
    AdapterProvider(),
    UtilProvider(),
)
