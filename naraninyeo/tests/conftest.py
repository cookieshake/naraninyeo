from collections.abc import AsyncIterator

import pytest_asyncio
from dishka import AsyncContainer, make_async_container

from naraninyeo.di import MainProvider, TestProvider


@pytest_asyncio.fixture(scope="package")
async def test_container() -> AsyncIterator[AsyncContainer]:
    container = make_async_container(MainProvider(), TestProvider())
    yield container
    await container.close()
