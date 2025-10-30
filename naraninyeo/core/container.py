
from collections.abc import AsyncIterable
from dishka import Provider, Scope, make_async_container, provide

from asyncpg import Pool, create_pool

from naraninyeo.core.settings import Settings

from naraninyeo.api.infrastructure.interfaces import (
    BotRepository,
    Clock,
    IdGenerator,
    MemoryRepository,
    MessageRepository,
    TextEmbedder,
)
from naraninyeo.api.infrastructure.adapter.llamacpp_gemma_embedder import LlamaCppGemmaEmbedder
from naraninyeo.api.infrastructure.repository.vchord_bot import VchordBotRepository
from naraninyeo.api.infrastructure.repository.vchord_memory import VchordMemoryRepository
from naraninyeo.api.infrastructure.repository.vchord_message import VchordMessageRepository
from naraninyeo.api.infrastructure.util.simple_clock import SimpleClock
from naraninyeo.api.infrastructure.util.nanoid_generator import NanoidGenerator

class CoreProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return Settings()

class ConnectionProvider(Provider):
    scope = Scope.APP

    @provide
    async def database_pool(self, settings: Settings) -> AsyncIterable[Pool]:
        pool = await create_pool(dsn=settings.VCHORD_URI)
        yield pool
        await pool.close()

class RepositoryProvider(Provider):
    scope = Scope.APP

    bot_repository = provide(source=VchordBotRepository, provides=BotRepository)
    memory_repository = provide(source=VchordMemoryRepository, provides=MemoryRepository)
    message_repository = provide(source=VchordMessageRepository, provides=MessageRepository)

class UtilProvider(Provider):
    scope = Scope.APP

    clock = provide(source=SimpleClock, provides=Clock)
    id_generator = provide(source=NanoidGenerator, provides=IdGenerator)
    text_embedder = provide(source=LlamaCppGemmaEmbedder, provides=TextEmbedder)

container = make_async_container(
    CoreProvider(),
    ConnectionProvider(),
    RepositoryProvider(),
    UtilProvider(),
)