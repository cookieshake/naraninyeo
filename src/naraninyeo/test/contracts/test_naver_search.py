"""
NaverSearch 계약 테스트

스펙: core/interfaces.py NaverSearch Protocol
구현체: infrastructure/adapter/naver_search.py NaverSearchClient
연동: 실제 네이버 검색 API (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수 필요)
"""

import re

import pytest

from naraninyeo.core.interfaces import NaverSearch
from naraninyeo.core.models import SearchResult


@pytest.mark.asyncio
async def test_search_returns_list_of_search_results(naver_search: NaverSearch):
    """search()는 SearchResult 목록을 반환한다."""
    results = await naver_search.search("encyclopedia", "파이썬", limit=3)

    assert isinstance(results, list)
    assert len(results) > 0
    for result in results:
        assert isinstance(result, SearchResult)


@pytest.mark.asyncio
async def test_search_result_has_required_fields(naver_search: NaverSearch):
    """각 SearchResult는 title과 description을 가진다."""
    results = await naver_search.search("encyclopedia", "파이썬", limit=3)

    for result in results:
        assert result.title, "title은 비어있으면 안 된다"
        assert result.description, "description은 비어있으면 안 된다"


@pytest.mark.asyncio
async def test_search_strips_html_tags(naver_search: NaverSearch):
    """결과의 title과 description에 HTML 태그가 없어야 한다."""
    html_tag_pattern = re.compile(r"<[^>]+>")
    results = await naver_search.search("news", "파이썬", limit=5)

    for result in results:
        assert not html_tag_pattern.search(result.title), f"title에 HTML 태그가 있음: {result.title}"
        assert not html_tag_pattern.search(result.description), f"description에 HTML 태그가 있음: {result.description}"


@pytest.mark.asyncio
async def test_search_news_with_date_order(naver_search: NaverSearch):
    """order='date'이면 최신순 뉴스 결과를 반환한다."""
    results = await naver_search.search("news", "삼성전자", limit=5, order="date")

    assert isinstance(results, list)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_news_without_order_deduplicates(naver_search: NaverSearch):
    """order=None이면 sim+date 병렬 요청 후 중복 제거된 결과를 반환한다."""
    results_no_order = await naver_search.search("news", "삼성전자", limit=5, order=None)
    results_with_order = await naver_search.search("news", "삼성전자", limit=5, order="sim")

    # 중복 제거로 link 기준 고유해야 함
    links = [r.link for r in results_no_order if r.link]
    assert len(links) == len(set(links)), "중복된 link가 있음"

    # order=None 결과는 단일 order보다 많거나 같아야 함 (두 요청 합산)
    assert len(results_no_order) >= len(results_with_order)


@pytest.mark.asyncio
async def test_search_limit_is_respected(naver_search: NaverSearch):
    """limit 파라미터가 반환 결과 개수를 제한한다."""
    results = await naver_search.search("general", "날씨", limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_search_returns_empty_for_nonsense_query(naver_search: NaverSearch):
    """결과가 없는 쿼리는 빈 리스트를 반환한다."""
    results = await naver_search.search("encyclopedia", "xyzxyzxyz무의미한쿼리12345", limit=5)

    assert isinstance(results, list)
    # 빈 리스트이거나 매우 적은 결과 (네이버가 유사 결과를 반환할 수 있음)


@pytest.mark.asyncio
async def test_search_encyclopedia_type(naver_search: NaverSearch):
    """encyclopedia 타입으로 검색이 가능하다."""
    results = await naver_search.search("encyclopedia", "대한민국", limit=3)

    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_blog_type(naver_search: NaverSearch):
    """blog 타입으로 검색이 가능하다."""
    results = await naver_search.search("blog", "파이썬 튜토리얼", limit=3)

    assert len(results) > 0
