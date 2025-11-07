import math
from datetime import datetime
from typing import List, Literal

import dateparser
import httpx
from bs4 import BeautifulSoup
from opentelemetry.trace import get_current_span, get_tracer
from pydantic import BaseModel

from naraninyeo.core.settings import Settings


class SearchResult(BaseModel):
    link: str | None
    title: str
    description: str
    published_at: str | None


class NaverSearchClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @get_tracer(__name__).start_as_current_span("naver_search")
    async def search(
        self, search_type: Literal["general", "news", "blog", "document", "encyclopedia"], query: str, limit: int
    ) -> List[SearchResult]:
        span = get_current_span()
        span.set_attribute("search.type", search_type)
        span.set_attribute("search.query", query)
        span.set_attribute("search.limit", limit)
        return [self._parse_result(item) for item in await self._request(search_type, query, limit)]

    async def _request(
        self, search_type: Literal["general", "news", "blog", "document", "encyclopedia"], query: str, limit: int
    ) -> list[dict[str, str]]:
        base_url = "https://openapi.naver.com/v1/search/"
        match search_type:
            case "general":
                endpoint = "webkr.json"
                params = [
                    {"query": query, "display": math.ceil(limit / 2.0), "sort": "sim"},
                    {"query": query, "display": math.floor(limit / 2.0), "sort": "date"},
                ]
            case "news":
                endpoint = "news.json"
                params = [
                    {"query": query, "display": math.ceil(limit / 2.0), "sort": "sim"},
                    {"query": query, "display": math.floor(limit / 2.0), "sort": "date"},
                ]
            case "blog":
                endpoint = "blog.json"
                params = [
                    {"query": query, "display": math.ceil(limit / 2.0), "sort": "sim"},
                    {"query": query, "display": math.floor(limit / 2.0), "sort": "date"},
                ]
            case "document":
                endpoint = "doc.json"
                params = [{"query": query, "display": limit}]
            case "encyclopedia":
                endpoint = "encyc.json"
                params = [{"query": query, "display": limit}]

        url = f"{base_url}{endpoint}"
        headers = {
            "X-Naver-Client-Id": self.settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": self.settings.NAVER_CLIENT_SECRET,
        }
        result = []
        async with httpx.AsyncClient() as client:
            for param in params:
                response = await client.get(url, headers=headers, params=param, timeout=10)
                response.raise_for_status()
                payload = response.json()
                result.extend(payload.get("items", []))
        return result

    @get_tracer(__name__).start_as_current_span("parse_result")
    def _parse_result(self, item: dict[str, str]) -> SearchResult:
        title = BeautifulSoup(item.get("title", ""), "html.parser").get_text().strip()
        description = BeautifulSoup(item.get("description", ""), "html.parser").get_text().strip()
        link = item.get("link") or item.get("originallink")
        timestamp = self._parse_datetime(item.get("pubDate") or item.get("postdate"))

        return SearchResult(
            link=link,
            title=title,
            description=description,
            published_at=timestamp.isoformat() if timestamp else None,
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return dateparser.parse(value)
