import re

import httpx
import pytest
from pytest_httpx import HTTPXMock

from naraninyeo.core.models import Ticker
from naraninyeo.infrastructure.adapter.finance_search import FinanceSearchClient

DOMESTIC_TICKER = Ticker(
    code="005930",
    reuter_code="005930",
    nation_code="KOR",
    type="stock",
    name="삼성전자",
    url="https://m.stock.naver.com/domestic/stock/005930/home",
    category="stock",
)

WORLD_TICKER = Ticker(
    code="AAPL",
    reuter_code="AAPL.O",
    nation_code="USA",
    type="NASDAQ",
    name="애플",
    url="https://m.stock.naver.com/worldstock/stock/AAPL.O/home",
    category="stock",
)

AUTOCOMPLETE_RESPONSE = {
    "result": {
        "items": [
            {
                "code": "005930",
                "reutersCode": "005930",
                "nationCode": "KOR",
                "typeCode": "stock",
                "name": "삼성전자",
                "url": "https://m.stock.naver.com/domestic/stock/005930/home",
                "category": "stock",
            }
        ]
    }
}


@pytest.fixture
async def finance_client(httpx_mock: HTTPXMock):
    async with httpx.AsyncClient() as client:
        yield FinanceSearchClient(client)


async def test_search_symbol_returns_ticker(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*autoComplete.*"),
        json=AUTOCOMPLETE_RESPONSE,
    )

    result = await finance_client.search_symbol("삼성전자")

    assert result is not None
    assert result.code == "005930"
    assert result.name == "삼성전자"


async def test_search_symbol_returns_none_for_empty(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*autoComplete.*"),
        json={"result": {"items": []}},
    )

    result = await finance_client.search_symbol("존재하지않는종목")
    assert result is None


async def test_search_symbol_cached(finance_client, httpx_mock: HTTPXMock):
    """같은 쿼리는 캐시되어 HTTP 호출이 1번만 발생해야 한다."""
    httpx_mock.add_response(
        url=re.compile(r".*autoComplete.*"),
        json=AUTOCOMPLETE_RESPONSE,
    )

    r1 = await finance_client.search_symbol("삼성전자")
    r2 = await finance_client.search_symbol("삼성전자")

    assert r1 == r2
    assert len(httpx_mock.get_requests()) == 1


async def test_search_symbol_raises_on_error(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=re.compile(r".*autoComplete.*"), status_code=500, text="Server Error")

    with pytest.raises(Exception, match="Failed to search symbol"):
        await finance_client.search_symbol("에러종목")


async def test_search_news_domestic(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*m\.stock\.naver\.com/api/news/stock.*"),
        json=[{"items": [{"officeName": "한겨레", "datetime": "2026-01-01", "title": "삼성 뉴스", "body": "내용"}]}],
    )

    results = await finance_client.search_news(DOMESTIC_TICKER)

    assert len(results) == 1
    assert results[0].title == "삼성 뉴스"
    assert results[0].source == "한겨레"


async def test_search_news_world(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*api\.stock\.naver\.com/news/worldStock.*"),
        json=[{"ohnm": "Reuters", "dt": "2026-01-01", "tit": "Apple News", "subcontent": "content"}],
    )

    results = await finance_client.search_news(WORLD_TICKER)

    assert len(results) == 1
    assert results[0].title == "Apple News"
    assert results[0].source == "Reuters"


async def test_search_current_price_domestic(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*polling\.finance\.naver\.com.*domestic.*"),
        json={"datas": [{"closePrice": "75000"}]},
    )

    result = await finance_client.search_current_price(DOMESTIC_TICKER)
    assert result == "75000"


async def test_search_current_price_empty(finance_client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(r".*polling\.finance\.naver\.com.*"),
        json={"datas": []},
    )

    result = await finance_client.search_current_price(DOMESTIC_TICKER)
    assert result is None
