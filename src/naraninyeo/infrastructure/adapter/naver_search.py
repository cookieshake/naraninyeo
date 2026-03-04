import asyncio
import math
from datetime import datetime
from typing import List, Literal, Optional

import dateparser
import httpx
from bs4 import BeautifulSoup
from opentelemetry.trace import get_current_span, get_tracer

from naraninyeo.core.models import SearchResult
from naraninyeo.core.settings import Settings


class NaverSearchClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self._client = client

    @get_tracer(__name__).start_as_current_span("naver_search")
    async def search(
        self,
        search_type: Literal["general", "news", "blog", "document", "encyclopedia"],
        query: str,
        limit: int,
        order: Optional[Literal["sim", "date"]] = None,
    ) -> List[SearchResult]:
        span = get_current_span()
        span.set_attribute("search.type", search_type)
        span.set_attribute("search.query", query)
        span.set_attribute("search.limit", limit)
        return [self._parse_result(item) for item in await self._request(search_type, query, limit, order)]

    async def _request(
        self,
        search_type: Literal["general", "news", "blog", "document", "encyclopedia"],
        query: str,
        limit: int,
        order: Optional[Literal["sim", "date"]],
    ) -> list[dict[str, str]]:
        base_url = "https://openapi.naver.com/v1/search/"
        match search_type:
            case "general":
                endpoint = "webkr.json"
                if order:
                    params = [{"query": query, "display": limit, "sort": order}]
                else:
                    params = [
                        {"query": query, "display": math.ceil(limit / 2.0), "sort": "sim"},
                        {"query": query, "display": math.floor(limit / 2.0), "sort": "date"},
                    ]
            case "news":
                endpoint = "news.json"
                if order:
                    params = [{"query": query, "display": limit, "sort": order}]
                else:
                    params = [
                        {"query": query, "display": math.ceil(limit / 2.0), "sort": "sim"},
                        {"query": query, "display": math.floor(limit / 2.0), "sort": "date"},
                    ]
            case "blog":
                endpoint = "blog.json"
                if order:
                    params = [{"query": query, "display": limit, "sort": order}]
                else:
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

        async def _single_request(param: dict) -> list[dict]:
            response = await self._client.get(url, headers=headers, params=param, timeout=10)
            response.raise_for_status()
            return response.json().get("items", [])

        results = await asyncio.gather(*[_single_request(p) for p in params])
        return [item for items in results for item in items]

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
