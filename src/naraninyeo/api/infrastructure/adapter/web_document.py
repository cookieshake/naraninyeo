import asyncio
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from html_to_markdown import PreprocessingOptions, convert


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
    ) -> str:
        html_content = await self._fetch_document(url)
        soup = await self._preprocess_html(url, html_content)
        markdown_content = await self._html_to_markdown(soup)
        return markdown_content

    async def _fetch_document(
        self,
        url: str,
    ) -> str:
        response = await self.client.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

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
