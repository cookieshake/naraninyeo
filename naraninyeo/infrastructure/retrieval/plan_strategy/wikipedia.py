import asyncio
import logging
from textwrap import dedent
from typing import List, Optional, override

import httpx
import nanoid
from opentelemetry.trace import get_tracer

from naraninyeo.core.llm.agent import Agent
from naraninyeo.core.llm.spec import native
from naraninyeo.domain.gateway.retrieval import PlanExecutorStrategy, RetrievalResultCollector
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import (
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.settings import Settings


class WikiSearchResult:
    def __init__(self, title: str, pageid: int, snippet: str):
        self.title = title
        self.pageid = pageid
        self.snippet = snippet


class WikipediaClient:
    def __init__(self):
        self.base = "https://en.wikipedia.org/w/api.php"

    @get_tracer(__name__).start_as_current_span("wikipedia search")
    async def search(self, query: str, limit: int = 5) -> List[WikiSearchResult]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.base, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("query", {}).get("search", []):
            results.append(
                WikiSearchResult(
                    title=item.get("title", ""), pageid=item.get("pageid", 0), snippet=item.get("snippet", "")
                )
            )
        return results

    @get_tracer(__name__).start_as_current_span("wikipedia page extract")
    async def get_extract(self, pageid: int) -> str:
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "pageids": pageid,
            "format": "json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.base, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        return page.get("extract", "")


class WikipediaExtractor:
    def __init__(self, llm_factory: LLMAgentFactory):
        # reuse extractor agent prompt suited for text relevance/summary
        from pydantic import BaseModel

        class ExtractionResult(BaseModel):
            content: str
            is_relevant: Optional[bool]

        self.ExtractionResult = ExtractionResult
        self.agent: Agent[ExtractionResult] = llm_factory.extractor_agent(output_type=native(ExtractionResult))

    async def summarize(self, text: str, query: str) -> str:
        if not text:
            return ""
        message = dedent(
            f"""
            [쿼리]
            {query}

            [문서 일부]
            ---
            {text[:6000]}
            ---
            위 내용 중 쿼리와 직접 관련된 핵심만 1~2문장으로 한국어로 간결히 요약하세요.
            없으면 빈 내용으로 반환하세요.
            """
        ).strip()
        try:
            result = await self.agent.run(message)
            extraction = result.output
            if extraction and getattr(extraction, "content", "").strip():
                return extraction.content
            return ""
        except Exception:
            return ""


class WikipediaStrategy(PlanExecutorStrategy):
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.client = WikipediaClient()
        self.extractor = WikipediaExtractor(llm_factory)

    @override
    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type == "wikipedia"

    @get_tracer(__name__).start_as_current_span("execute wikipedia search")
    async def execute(self, plan: RetrievalPlan, context: ReplyContext, collector: RetrievalResultCollector):
        try:
            results = await self.client.search(plan.query, limit=5)
        except Exception as e:
            logging.info("Wikipedia search failed", exc_info=e)
            results = []

        async def worker(res: WikiSearchResult):
            try:
                extract = await self.client.get_extract(res.pageid)
                summary = await self.extractor.summarize(extract, plan.query)
                content = summary or extract[:500]
                await collector.add(
                    RetrievalResult(
                        plan=plan,
                        result_id=nanoid.generate(),
                        content=content,
                        ref=UrlRef(value=f"https://en.wikipedia.org/?curid={res.pageid}"),
                        status=RetrievalStatus.SUCCESS,
                        status_reason=RetrievalStatusReason.SUCCESS,
                        source_name="wikipedia.org",
                        source_timestamp=None,
                    )
                )
            except Exception as e:
                logging.info("Wikipedia worker failed", exc_info=e)

        await asyncio.gather(*[worker(r) for r in results], return_exceptions=True)
