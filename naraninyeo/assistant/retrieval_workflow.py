"""Retrieval planning, execution, and post-processing utilities."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Protocol, runtime_checkable
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
from naraninyeo.assistant.prompts import ExtractorPrompt, PlannerPrompt
from naraninyeo.settings import Settings


@dataclass
class RetrievalPlanLog:
    plan: RetrievalPlan
    matched: bool


class RetrievalPlanner:
    def __init__(self, settings: Settings, llm_factory: LLMToolFactory):
        self.settings = settings
        self.tool: LLMTool[PlannerPrompt, list[RetrievalPlan]] = llm_factory.planner_tool()

    @get_tracer(__name__).start_as_current_span("plan retrieval")
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        prompt = PlannerPrompt(context=context)
        plans = await self.tool.run(prompt)
        logging.debug("Retrieval plans generated: %s", [p.model_dump() for p in plans or []])
        return list(plans or [])


class RetrievalResultCollector:
    """Collects retrieval results in memory for later post-processing."""

    def __init__(self) -> None:
        self._results: dict[str, RetrievalResult] = {}

    async def add(self, item: RetrievalResult) -> None:
        self._results[item.result_id] = item

    async def snapshot(self) -> list[RetrievalResult]:
        return list(self._results.values())


class RetrievalResultCollectorFactory:
    def create(self) -> RetrievalResultCollector:
        return RetrievalResultCollector()


@runtime_checkable
class RetrievalStrategy(Protocol):
    def supports(self, plan: RetrievalPlan) -> bool: ...

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None: ...


class RetrievalExecutor:
    def __init__(self, max_concurrency: int | None = None) -> None:
        self._strategies: list[RetrievalStrategy] = []
        self._semaphore = asyncio.Semaphore(max_concurrency or 999999)

    def register(self, strategy: RetrievalStrategy) -> None:
        if not isinstance(strategy, RetrievalStrategy):
            raise TypeError("Strategy must define 'supports' and 'execute' methods")
        self._strategies.append(strategy)

    @property
    def strategies(self) -> list[RetrievalStrategy]:
        return list(self._strategies)

    async def execute(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        tasks: list[asyncio.Task[None]] = []
        logs: list[RetrievalPlanLog] = []
        try:
            for plan in plans:
                matched = False
                for strategy in self._strategies:
                    if strategy.supports(plan):
                        matched = True

                        async def run_with_sem(s=strategy, p=plan) -> None:
                            async with self._semaphore:
                                await s.execute(p, context, collector)

                        tasks.append(asyncio.create_task(run_with_sem()))
                        break
                logs.append(RetrievalPlanLog(plan=plan, matched=matched))
                if not matched:
                    logging.warning("No executor found for plan: %s", plan.model_dump())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logging.info("A retrieval strategy failed", exc_info=result)
        except asyncio.CancelledError:
            logging.info("Retrieval tasks were cancelled, so some results may be missing.")
        return logs

    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        timeout_seconds: float,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        try:
            return await asyncio.wait_for(
                self.execute(plans, context, collector),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logging.info("Retrieval execution timed out; returning partial results")
            return []


class HeuristicRetrievalRanker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, item: RetrievalResult) -> float:
        score = 1.0
        search_type = getattr(item.plan, "search_type", None)
        score += float(self.settings.RANK_WEIGHTS.get(search_type or "", 0.0))
        ts = item.source_timestamp
        if isinstance(ts, datetime):
            try:
                now = datetime.now(ts.tzinfo or timezone.utc)
                window = timedelta(hours=int(self.settings.RECENCY_WINDOW_HOURS))
                age = now - ts
                if age <= window:
                    fraction = max(0.0, 1.0 - age.total_seconds() / window.total_seconds())
                    score += float(self.settings.RECENCY_BONUS_MAX) * fraction
            except Exception:
                pass
        return score


class RetrievalPostProcessor:
    def __init__(self, settings: Settings, ranker: HeuristicRetrievalRanker):
        self.settings = settings
        self.ranker = ranker

    def process(self, results: list[RetrievalResult], context: ReplyContext) -> list[RetrievalResult]:
        filtered = [r for r in results if r.content and r.content.strip()]
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievalResult] = []
        for item in filtered:
            try:
                ref_attr = getattr(item.ref, "as_text", None)
                if isinstance(ref_attr, str):
                    ref_text = ref_attr
                elif callable(ref_attr):
                    ref_text = str(ref_attr())
                else:
                    ref_text = str(item.ref)
            except Exception:
                ref_text = str(item.ref)
            key = (ref_text, item.content.strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        try:
            deduped.sort(key=lambda r: self.ranker.score(r), reverse=True)
        except Exception:
            deduped.sort(key=lambda r: r.result_id)
        return deduped[: max(1, self.settings.MAX_KNOWLEDGE_REFERENCES)]


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
        collector: RetrievalResultCollector,
    ) -> None:
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
        collector: RetrievalResultCollector,
    ) -> None:
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
        collector: RetrievalResultCollector,
        item: dict[str, str],
    ) -> None:
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
        collector: RetrievalResultCollector,
    ) -> None:
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
        return extract


class RetrievalLogger:
    """Simple observer that records which plans were matched."""

    def __init__(self) -> None:
        self.entries: list[RetrievalPlanLog] = []

    def record(self, entries: Iterable[RetrievalPlanLog]) -> None:
        self.entries.extend(entries)
