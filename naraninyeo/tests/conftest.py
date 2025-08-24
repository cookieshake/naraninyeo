from collections.abc import AsyncIterator
from dishka import AsyncContainer, make_async_container
import pytest_asyncio

from naraninyeo.di import MainProvider, TestProvider


@pytest_asyncio.fixture(scope="package")
async def test_container() -> AsyncIterator[AsyncContainer]:
    container = make_async_container(MainProvider(), TestProvider())
    yield container
    await container.close()
