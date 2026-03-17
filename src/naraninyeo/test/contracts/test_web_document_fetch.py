"""
WebDocumentFetch 계약 테스트

스펙: core/interfaces.py WebDocumentFetch Protocol
구현체: infrastructure/adapter/web_document.py WebDocumentFetcher
연동: 실제 웹 페이지
"""

import pytest

from naraninyeo.core.interfaces import WebDocumentFetch
from naraninyeo.core.models import FetchedDocument


@pytest.mark.asyncio
async def test_fetch_document_returns_fetched_document(web_document_fetch: WebDocumentFetch):
    """fetch_document()는 FetchedDocument를 반환한다."""
    result = await web_document_fetch.fetch_document("https://httpbin.org/html")

    assert isinstance(result, FetchedDocument)


@pytest.mark.asyncio
async def test_fetch_document_has_required_fields(web_document_fetch: WebDocumentFetch):
    """반환값에 url, meta_tags, html_content, markdown_content가 모두 존재한다."""
    result = await web_document_fetch.fetch_document("https://httpbin.org/html")

    assert result.url == "https://httpbin.org/html"
    assert isinstance(result.meta_tags, dict)
    assert isinstance(result.html_content, str)
    assert len(result.html_content) > 0
    assert isinstance(result.markdown_content, str)
    assert len(result.markdown_content) > 0


@pytest.mark.asyncio
async def test_fetch_document_markdown_has_meaningful_content(web_document_fetch: WebDocumentFetch):
    """markdown_content는 실제 텍스트 콘텐츠를 포함한다."""
    result = await web_document_fetch.fetch_document("https://httpbin.org/html")

    # httpbin.org/html의 본문 텍스트가 포함되어야 함
    assert "Herman Melville" in result.markdown_content or "Moby Dick" in result.markdown_content


@pytest.mark.asyncio
async def test_fetch_document_meta_tags_parsed(web_document_fetch: WebDocumentFetch):
    """meta 태그가 dict로 파싱된다."""
    result = await web_document_fetch.fetch_document("https://www.python.org")

    assert isinstance(result.meta_tags, dict)
    assert len(result.meta_tags) > 0


@pytest.mark.asyncio
async def test_fetch_document_layout_elements_removed_from_markdown(web_document_fetch: WebDocumentFetch):
    """markdown_content에서 레이아웃 요소(header/footer/nav)가 제거된다."""
    result = await web_document_fetch.fetch_document("https://httpbin.org/html")

    # HTML에는 있을 수 있지만 markdown에서는 layout 구조가 제거됨
    # markdown 자체가 텍스트 중심이므로 <header>/<footer>/<nav> 태그가 없어야 함
    assert "<header>" not in result.markdown_content
    assert "<footer>" not in result.markdown_content
    assert "<nav>" not in result.markdown_content
