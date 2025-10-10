"""Concrete retrieval strategies backed by history, Naver search, and Wikipedia."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urljoin, urlparse

import dateparser
import httpx
import nanoid
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from opentelemetry.trace import get_tracer
from pydantic import BaseModel
from pydantic_ai.output import NativeOutput

from naraninyeo.assistant.llm_toolkit import LLMTool, LLMToolFactory
from naraninyeo.assistant.message_repository import MongoQdrantMessageRepository
from naraninyeo.assistant.models import (
    ChatHistoryRef,
    ReplyContext,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.assistant.prompts import ExtractorPrompt
from naraninyeo.settings import Settings


class ChatHistoryStrategy:
    def __init__(self, message_repository: MongoQdrantMessageRepository):
        self.message_repository = message_repository

    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type == "chat_history"

    @get_tracer(__name__).start_as_current_span("execute chat history retrieval")
    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: "RetrievalResultCollector",
    ) -> None:
        from naraninyeo.assistant.retrieval.execution import RetrievalResultCollector

        if not isinstance(collector, RetrievalResultCollector):
            raise TypeError("collector must be a RetrievalResultCollector")

        messages = await self.message_repository.search_similar_messages(
            channel_id=context.last_message.channel.channel_id,
            keyword=plan.query,
            limit=3,
        )
        chunks = [
            self.message_repository.get_surrounding_messages(message=message, before=3, after=3) for message in messages
        ]
        for task in asyncio.as_completed(chunks):
            chunk = await task
            if not chunk:
                continue
            ref = ChatHistoryRef(value=chunk)
            # 유사 메시지 주변 대화까지 묶어서 반환해 LLM이 흐름을 이해하도록 돕는다.
            await collector.add(
                RetrievalResult(
                    plan=plan,
                    result_id=nanoid.generate(),
                    content=ref.as_text,
                    ref=ref,
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=f"chat_history_{chunk[-1].timestamp_str}",
                    source_timestamp=chunk[-1].timestamp if chunk else None,
                )
            )


class MarkdownCrawler:
    def __init__(self) -> None:
        self.markdown_converter = MarkdownConverter()

    @get_tracer(__name__).start_as_current_span("get markdown from url")
    async def get_markdown_from_url(self, url: str) -> str:
        async with httpx.AsyncClient() as client:
            last_exc: Exception | None = None
            for _ in range(3):
                try:
                    response = await client.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        follow_redirects=True,
                        timeout=20.0,
                    )
                    response.raise_for_status()
                    html_text = response.text
                    soup = BeautifulSoup(html_text, "html.parser")
                    break
                except Exception as exc:
                    last_exc = exc
                    await asyncio.sleep(0.5)
            else:
                logging.info("Failed to fetch url after retries", exc_info=last_exc)
                return ""

        iframes = [iframe for iframe in soup.find_all("iframe") if isinstance(iframe.get("src"), str)]  # pyright: ignore[reportAttributeAccessIssue]
        if iframes:
            # iframe 내용도 추가로 불러와 본문에 합쳐준다.
            async with httpx.AsyncClient() as iframe_client:
                iframe_links = [urljoin(url, iframe.get("src")) for iframe in iframes]  # pyright: ignore[reportArgumentType, reportAttributeAccessIssue]
                iframe_htmls = await asyncio.gather(
                    *(iframe_client.get(link) for link in iframe_links),
                    return_exceptions=True,
                )
            for iframe, iframe_resp in zip(iframes, iframe_htmls, strict=False):
                if isinstance(iframe_resp, BaseException):
                    logging.warning(
                        "Failed to retrieve iframe %s: %s",
                        iframe.get("src"),  # pyright: ignore[reportAttributeAccessIssue]
                        iframe_resp,
                    )
                    continue
                iframe_soup = BeautifulSoup(iframe_resp.text, "html.parser")
                iframe.replace_with(iframe_soup)

        for tag in ["a", "button", "iframe"]:
            for element in soup.find_all(tag):
                element.decompose()

        return self.markdown_converter.convert_soup(soup)


class DocumentExtractionResult(BaseModel):
    content: str
    is_relevant: bool | None


class DocumentExtractor:
    def __init__(self, settings: Settings, crawler: MarkdownCrawler, llm_factory: LLMToolFactory) -> None:
        self.settings = settings
        self.crawler = crawler
        self.tool: LLMTool[ExtractorPrompt, DocumentExtractionResult] = llm_factory.extractor_tool(
            output_type=NativeOutput(DocumentExtractionResult)
        )

    async def extract(
        self,
        url: str,
        plan: RetrievalPlan,
    ) -> DocumentExtractionResult | None:
        markdown = await self.crawler.get_markdown_from_url(url)
        if not markdown:
            return None
        prompt = ExtractorPrompt(markdown=markdown, query=plan.query)
        try:
            # 크롤링한 문서를 LLM이 요약/필터링하도록 요청한다.
            return await self.tool.run(prompt)
        except Exception as exc:  # pragma: no cover - network/LLM failures are noisy already
            logging.debug("Extractor failed", exc_info=exc)
            return None


class NaverSearchStrategy:
    def __init__(self, settings: Settings, llm_factory: LLMToolFactory) -> None:
        self.settings = settings
        self.extractor = DocumentExtractor(settings, MarkdownCrawler(), llm_factory)

    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type.startswith("naver_")

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: "RetrievalResultCollector",
    ) -> None:
        from naraninyeo.assistant.retrieval.execution import RetrievalResultCollector

        if not isinstance(collector, RetrievalResultCollector):
            raise TypeError("collector must be a RetrievalResultCollector")

        results = await self._search(plan)
        tasks = [self._handle_result(plan, collector, item) for item in results]
        await asyncio.gather(*tasks)

    async def _search(self, plan: RetrievalPlan) -> list[dict[str, str]]:
        base_url = "https://openapi.naver.com/v1/search/"
        match plan.search_type:
            case "naver_news":
                endpoint = "news.json"
            case "naver_blog":
                endpoint = "blog.json"
            case "naver_web":
                endpoint = "webkr.json"
            case "naver_doc":
                endpoint = "doc.json"
            case _:
                raise ValueError(f"Unsupported search type: {plan.search_type}")
        url = f"{base_url}{endpoint}"
        # 네이버 오픈 API는 타입별로 엔드포인트가 달라 매핑이 필요하다.
        headers = {
            "X-Naver-Client-Id": self.settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": self.settings.NAVER_CLIENT_SECRET,
        }
        params = {"query": plan.query, "display": 5}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
        return payload.get("items", [])

    async def _handle_result(
        self,
        plan: RetrievalPlan,
        collector: "RetrievalResultCollector",
        item: dict[str, str],
    ) -> None:
        from naraninyeo.assistant.retrieval.execution import RetrievalResultCollector

        if not isinstance(collector, RetrievalResultCollector):
            raise TypeError("collector must be a RetrievalResultCollector")

        link = item.get("link") or item.get("originallink")
        if not link:
            return
        cleaned_title = BeautifulSoup(item.get("title", ""), "html.parser").get_text().strip()
        summary = BeautifulSoup(item.get("description", ""), "html.parser").get_text().strip()
        extraction = await self.extractor.extract(link, plan)
        if not extraction or extraction.is_relevant is False:
            return
        content = summary
        if extraction.content:
            content = f"{summary}\n{extraction.content}" if summary else extraction.content
        timestamp = self._parse_datetime(item.get("pubDate"))
        # 검색 결과 요약과 추출 내용을 합쳐 하나의 지식 조각으로 저장한다.
        await collector.add(
            RetrievalResult(
                plan=plan,
                result_id=nanoid.generate(),
                content=content,
                ref=UrlRef(value=link),
                status=RetrievalStatus.SUCCESS,
                status_reason=RetrievalStatusReason.SUCCESS,
                source_name=cleaned_title or urlparse(link).netloc,
                source_timestamp=timestamp,
            )
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = dateparser.parse(value)
        if parsed is None:
            return None
        return parsed.astimezone(timezone.utc)


class WikipediaStrategy:
    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type == "wikipedia"

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: "RetrievalResultCollector",
    ) -> None:
        from naraninyeo.assistant.retrieval.execution import RetrievalResultCollector

        if not isinstance(collector, RetrievalResultCollector):
            raise TypeError("collector must be a RetrievalResultCollector")

        summary = await self._summary(plan.query)
        if not summary:
            return
        await collector.add(
            RetrievalResult(
                plan=plan,
                result_id=nanoid.generate(),
                content=summary,
                ref=UrlRef(value=f"https://ko.wikipedia.org/wiki/{plan.query}"),
                status=RetrievalStatus.SUCCESS,
                status_reason=RetrievalStatusReason.SUCCESS,
                source_name="wikipedia",
                source_timestamp=datetime.now(timezone.utc),
            )
        )

    async def _summary(self, query: str) -> str | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://ko.wikipedia.org/api/rest_v1/page/summary/" + query,
                timeout=10,
            )
        if response.status_code != 200:
            return None
        data = response.json()
        extract = data.get("extract")
        if not extract:
            return None
        # 위키 API가 주는 요약 텍스트만 추려 사용한다.
        return extract
