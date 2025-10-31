from fastapi import FastAPI
from fastapi.testclient import TestClient
from dishka.integrations.fastapi import setup_dishka
import httpx
import pytest

from dishka import AsyncContainer

@pytest.fixture(scope="session")
def test_app(test_container: AsyncContainer) -> FastAPI:
    from naraninyeo.api import create_app
    app = create_app()
    setup_dishka(test_container, app)
    return app

@pytest.fixture(scope="session")
def test_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)
