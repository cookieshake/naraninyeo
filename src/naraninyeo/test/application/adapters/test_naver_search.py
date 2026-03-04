import re

import httpx
import pytest
from pytest_httpx import HTTPXMock

from naraninyeo.core.settings import Settings
from naraninyeo.infrastructure.adapter.naver_search import NaverSearchClient


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("VCHORD_URI", "postgresql://test")
    monkeypatch.setenv("LLAMA_CPP_EMBEDDINGS_URI", "http://localhost:8080")
    return Settings()


@pytest.fixture
async def naver_client(settings, httpx_mock: HTTPXMock):
    async with httpx.AsyncClient() as client:
        yield NaverSearchClient(settings=settings, client=client)


async def test_search_encyclopedia_single_request(naver_client, httpx_mock: HTTPXMock):
    """encyclopedia는 단일 요청을 보낸다."""
    httpx_mock.add_response(
        url=re.compile(r".*encyc\.json.*"),
        json={"items": [{"title": "파이썬", "link": "https://example.com", "description": "프로그래밍 언어"}]},
    )

    results = await naver_client.search("encyclopedia", "파이썬", 5, order="sim")

    assert len(results) == 1
    assert results[0].title == "파이썬"
    assert results[0].link == "https://example.com"


async def test_search_news_parallel_requests(naver_client, httpx_mock: HTTPXMock):
    """order=None이면 sim + date 2건이 병렬로 요청된다."""
    httpx_mock.add_response(
        url=re.compile(r".*news\.json.*"),
        json={"items": [{"title": "뉴스1", "link": "https://news1.com", "description": "내용1"}]},
    )
    httpx_mock.add_response(
        url=re.compile(r".*news\.json.*"),
        json={"items": [{"title": "뉴스2", "link": "https://news2.com", "description": "내용2"}]},
    )

    results = await naver_client.search("news", "AI", 10)

    assert len(results) == 2
    titles = {r.title for r in results}
    assert "뉴스1" in titles
    assert "뉴스2" in titles


async def test_search_strips_html_tags(naver_client, httpx_mock: HTTPXMock):
    """HTML 태그가 제거되어야 한다."""
    httpx_mock.add_response(
        url=re.compile(r".*webkr\.json.*"),
        json={"items": [{"title": "<b>굵은 제목</b>", "link": "https://example.com", "description": "<em>강조</em>"}]},
    )

    results = await naver_client.search("general", "테스트", 5, order="sim")

    assert results[0].title == "굵은 제목"
    assert results[0].description == "강조"


async def test_search_raises_on_error(naver_client, httpx_mock: HTTPXMock):
    """API 에러 시 예외가 전파된다."""
    httpx_mock.add_response(url=re.compile(r".*news\.json.*"), status_code=401)

    with pytest.raises(httpx.HTTPStatusError):
        await naver_client.search("news", "테스트", 5, order="sim")
