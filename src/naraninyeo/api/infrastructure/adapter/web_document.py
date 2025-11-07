import asyncio
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from html_to_markdown import PreprocessingOptions, convert
from opentelemetry.trace import get_tracer
from pydantic import BaseModel


class FetchedDocument(BaseModel):
    url: str
    meta_tags: dict[str, str]
    html_content: str
    markdown_content: str


class WebDocumentFetcher:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            verify=False,
            timeout=10.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
            },
        )

    async def fetch_document(
        self,
        url: str,
    ) -> FetchedDocument:
        html_content = await self._fetch_document(url)
        soup = await self._preprocess_html(url, html_content)
        tags = {}
        meta_tags = soup.find_all("meta")
        for tag in meta_tags:
            if tag.get("name"):
                tags[tag.get("name").lower()] = tag.get("content", "")  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
            if tag.get("property"):
                tags[tag.get("property").lower()] = tag.get("content", "")  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
        markdown_content = await self._html_to_markdown(soup)
        return FetchedDocument(url=url, meta_tags=tags, html_content=html_content, markdown_content=markdown_content)

    async def _fetch_document(
        self,
        url: str,
    ) -> str:
        response = await self.client.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

    @get_tracer(__name__).start_as_current_span("preprocess_html")
    async def _preprocess_html(self, url: str, html_content: str) -> BeautifulSoup:
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        iframes = [iframe for iframe in soup.find_all("iframe") if isinstance(iframe.get("src"), str)]  # pyright: ignore[reportAttributeAccessIssue]
        if iframes:
            async with httpx.AsyncClient() as iframe_client:
                iframe_links = [urljoin(url, iframe.get("src")) for iframe in iframes]  # pyright: ignore[reportArgumentType, reportAttributeAccessIssue]
                iframe_htmls = await asyncio.gather(
                    *(iframe_client.get(link) for link in iframe_links),
                    return_exceptions=True,
                )
            for iframe, iframe_resp in zip(iframes, iframe_htmls, strict=False):
                if isinstance(iframe_resp, httpx.Response):
                    iframe_soup = BeautifulSoup(iframe_resp.text, "html.parser")
                    iframe.replace_with(iframe_soup)
        for tag in ["a", "button", "iframe"]:
            for element in soup.find_all(tag):
                element.decompose()
        return soup

    @get_tracer(__name__).start_as_current_span("html_to_markdown")
    async def _html_to_markdown(
        self,
        soup: BeautifulSoup,
    ) -> str:
        markdown_content = convert(
            soup.prettify(),
            preprocessing=PreprocessingOptions(
                enabled=True,
                preset="aggressive",
            ),
        )
        return markdown_content
