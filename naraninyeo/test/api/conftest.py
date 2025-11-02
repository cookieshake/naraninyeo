from typing import Iterator

import httpx
import pytest
from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def test_app(test_container: AsyncContainer) -> FastAPI:
    from naraninyeo.api import create_app
    app = create_app()
    setup_dishka(test_container, app)
    return app

@pytest.fixture
def test_client(test_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(test_app) as client:
        yield client
