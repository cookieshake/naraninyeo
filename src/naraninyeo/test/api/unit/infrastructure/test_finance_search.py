import pytest

from naraninyeo.api.infrastructure.adapter.finance_search import FinanceSearchClient


@pytest.fixture
async def finance_search_client():
    client = FinanceSearchClient()
    return client


test_queries = [
    "애플",
    "MSFT",
    "삼성전자",
]


async def test_search_symbol(finance_search_client: FinanceSearchClient):
    result = await finance_search_client.search_symbol("애플")
    assert result is not None
    assert result.code == "AAPL.O"
    assert result.type == "NASDAQ"
    assert result.name == "애플"
    assert result.nation == "USA"


@pytest.mark.parametrize("query", test_queries)
async def test_search_news(finance_search_client: FinanceSearchClient, query: str):
    symbol = await finance_search_client.search_symbol(query)
    if symbol is None:
        pytest.skip("Symbol not found for query: {}".format(query))
    result = await finance_search_client.search_news(symbol)
    assert result is not None
    assert len(result) > 0


@pytest.mark.parametrize("query", test_queries)
async def test_search_current_price(finance_search_client: FinanceSearchClient, query: str):
    symbol = await finance_search_client.search_symbol(query)
    if symbol is None:
        pytest.skip("Symbol not found for query: {}".format(query))
    result = await finance_search_client.search_current_price(symbol)
    assert result is not None


@pytest.mark.parametrize("query", test_queries)
async def test_get_short_term_price(finance_search_client: FinanceSearchClient, query: str):
    symbol = await finance_search_client.search_symbol(query)
    if symbol is None:
        pytest.skip("Symbol not found for query: {}".format(query))
    result = await finance_search_client.get_short_term_price(symbol)
    assert result is not None
    assert len(result) > 0


@pytest.mark.parametrize("query", test_queries)
async def test_get_long_term_price(finance_search_client: FinanceSearchClient, query: str):
    symbol = await finance_search_client.search_symbol(query)
    if symbol is None:
        pytest.skip("Symbol not found for query: {}".format(query))
    result = await finance_search_client.get_long_term_price(symbol)
    assert result is not None
    assert len(result) > 0
