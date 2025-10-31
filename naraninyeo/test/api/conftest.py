from fastapi import FastAPI
from fastapi.testclient import TestClient
from dishka.integrations.fastapi import setup_dishka
import httpx
import pytest

from dishka import AsyncContainer


@pytest.fixture
def test_app(anyio_backend, test_container: AsyncContainer) -> FastAPI:
    from naraninyeo.api import create_app
    app = create_app()
    setup_dishka(test_container, app)
    return app

@pytest.fixture
def test_client(anyio_backend, test_app: FastAPI) -> TestClient:
    return TestClient(test_app)
