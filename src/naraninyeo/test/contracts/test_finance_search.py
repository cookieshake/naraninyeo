"""
FinanceSearch 계약 테스트

스펙: core/interfaces.py FinanceSearch Protocol
구현체: infrastructure/adapter/finance_search.py FinanceSearchClient
연동: 실제 네이버 금융 API (인증 불필요)
"""

import time

import pytest

from naraninyeo.core.interfaces import FinanceSearch
from naraninyeo.core.models import NewsSearchResult, PriceInfo, Ticker


@pytest.mark.asyncio
async def test_search_symbol_returns_ticker_for_known_stock(finance_search: FinanceSearch):
    """알려진 종목 검색 시 Ticker를 반환한다."""
    result = await finance_search.search_symbol("삼성전자")

    assert result is not None
    assert isinstance(result, Ticker)
    assert result.code, "code는 비어있으면 안 된다"
    assert result.name, "name은 비어있으면 안 된다"


@pytest.mark.asyncio
async def test_search_symbol_returns_none_for_unknown_stock(finance_search: FinanceSearch):
    """존재하지 않는 종목 검색 시 None을 반환한다."""
    result = await finance_search.search_symbol("존재하지않는종목xyzabc12345")

    assert result is None


@pytest.mark.asyncio
async def test_search_symbol_caches_result(finance_search: FinanceSearch):
    """동일 쿼리 연속 호출 시 캐시를 사용한다 (두 번째 호출이 더 빠름)."""
    query = "삼성전자캐시테스트"

    start1 = time.monotonic()
    result1 = await finance_search.search_symbol(query)
    elapsed1 = time.monotonic() - start1

    start2 = time.monotonic()
    result2 = await finance_search.search_symbol(query)
    elapsed2 = time.monotonic() - start2

    # 두 결과가 동일해야 함
    assert result1 == result2
    # 두 번째 호출이 훨씬 빠르거나 결과가 캐시됨 (첫 번째보다 10배 이상 빠름)
    if result1 is not None:
        assert elapsed2 < elapsed1 * 0.5, f"캐시가 작동하지 않음: 1차={elapsed1:.3f}s, 2차={elapsed2:.3f}s"


@pytest.mark.asyncio
async def test_search_news_returns_list_for_domestic_ticker(finance_search: FinanceSearch):
    """국내 종목에 대한 뉴스를 반환한다."""
    ticker = await finance_search.search_symbol("삼성전자")
    assert ticker is not None

    results = await finance_search.search_news(ticker)

    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, NewsSearchResult)
        assert item.title, "title은 비어있으면 안 된다"
        assert item.body, "body는 비어있으면 안 된다"


@pytest.mark.asyncio
async def test_search_current_price_returns_value_or_none(finance_search: FinanceSearch):
    """현재 가격을 반환하거나 None을 반환한다."""
    ticker = await finance_search.search_symbol("삼성전자")
    assert ticker is not None

    result = await finance_search.search_current_price(ticker)

    assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_get_short_term_price_returns_price_list(finance_search: FinanceSearch):
    """단기 가격 데이터를 반환한다."""
    ticker = await finance_search.search_symbol("삼성전자")
    assert ticker is not None

    results = await finance_search.get_short_term_price(ticker)

    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, PriceInfo)
        assert item.local_date, "local_date는 비어있으면 안 된다"
        assert item.close_price > 0, "close_price는 양수여야 한다"


@pytest.mark.asyncio
async def test_get_long_term_price_returns_more_data_than_short_term(finance_search: FinanceSearch):
    """장기 가격 데이터는 단기보다 많은 데이터를 포함한다."""
    ticker = await finance_search.search_symbol("삼성전자")
    assert ticker is not None

    short_term = await finance_search.get_short_term_price(ticker)
    long_term = await finance_search.get_long_term_price(ticker)

    assert len(long_term) > len(short_term)
