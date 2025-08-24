import asyncio
import html
import logging
import re
from datetime import datetime
from textwrap import dedent
from typing import List, Literal, Optional, override
from urllib.parse import urljoin, urlparse

import dateparser
import httpx
import nanoid
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from opentelemetry.trace import get_tracer
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.domain.gateway.retrieval import PlanExecutorStrategy, RetrievalResultCollector
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import (
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.infrastructure.settings import Settings


class Crawler:
    def __init__(self):
        self.markdown_converter = MarkdownConverter()

    @get_tracer(__name__).start_as_current_span("get markdown from url")
    async def get_markdown_from_url(self, url: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            # make http request to all iframes and insert html into original
            for iframe in soup.find_all("iframe"):
                iframe_url: str = iframe.get("src")  # pyright: ignore[reportAttributeAccessIssue, reportAssignmentType]
                try:
                    iframe_url = urljoin(url, iframe_url)
                    if iframe_url:
                        response = await client.get(iframe_url)
                        response.raise_for_status()
                        iframe_html = response.text
                        iframe.replace_with(BeautifulSoup(iframe_html, "html.parser"))
                except Exception as e:
                    logging.warning(f"Failed to retrieve iframe {iframe_url}: {e}")
            for a in soup.find_all("a"):
                a.decompose()
            return self.markdown_converter.convert_soup(soup)


class ExtractionResult(BaseModel):
    content: str
    is_relevant: Optional[bool]


class Extractor:
    def __init__(self, settings: Settings, crawler: Crawler) -> None:
        self.settings = settings
        self.crawler = crawler
        self.agent = Agent(
            model=OpenAIModel(
                model_name="openai/gpt-4.1-nano",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY,
                ),
            ),
            # Structured output so we can know when content is irrelevant
            output_type=NativeOutput(ExtractionResult),
            instrument=True,
            model_settings=OpenAIModelSettings(timeout=5, extra_body={"reasoning": {"effort": "minimal"}}),
            system_prompt=dedent(
                """
            당신은 주어진 웹 검색 결과 마크다운 텍스트에서 쿼리와 관련된 핵심 정보를 정확하게 추출하는 AI입니다.

            - 반드시 마크다운 텍스트에 있는 내용만을 기반으로 추출해야 합니다.
            - 관련된 내용을 1~2문장으로 짧고 간결하게 요약하세요.
            - 텍스트는 독립적이고 완전한 의미를 담고 있어야 합니다.
            - 불필요한 설명이나 서론을 추가하지 말고, 추출된 텍스트만 제공하세요.
            - 추출된 내용만 간결하게 반환하고, 어떤 부가적인 설명도 덧붙이지 마세요.
            """
            ).strip(),
        )

    @get_tracer(__name__).start_as_current_span("extract from markdown")
    async def extract(self, url: str, query: str) -> ExtractionResult:
        markdown = await self.crawler.get_markdown_from_url(url)
        if not markdown:
            logging.warning(f"Failed to retrieve markdown for {url}")
            return ExtractionResult(content="", is_relevant=False)
        enhancement_result = await self.agent.run(
            dedent(
                f"""
            [마크다운 텍스트]
            ---
            {markdown}
            ---

            [쿼리]
            {query}

            위 마크다운 텍스트에서 위 쿼리와 직접적으로 관련된 핵심 정보만
            1~2문장으로 요약하여 ExtractionResult 형태로 반환하세요.
            - 관련성이 낮거나 추론이 필요한 정보는 제외하세요.
            - 관련된 내용이 없다면 content는 빈 문자열로 두고 is_relevant는 false로 설정하세요.
            - 관련된 내용이 있다면 content에 그 요약을 넣고 is_relevant는 true로 설정하세요.
            """
            )
        )
        # enhancement_result.output 는 ExtractionResult 타입
        extraction: ExtractionResult = enhancement_result.output
        # 안전장치: 모델이 is_relevant를 누락했을 경우 content 유무로 결정
        if extraction.is_relevant is None:
            extraction.is_relevant = bool(extraction.content.strip())
        if not extraction.content.strip():
            extraction.is_relevant = False
        return extraction


class NaverSearchResult(BaseModel):
    title: str
    description: str
    link: str
    pub_date: Optional[datetime]


class NaverSearchClient:
    def __init__(self, settings: Settings):
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET

    @get_tracer(__name__).start_as_current_span("search naver")
    async def search(
        self,
        query: str,
        api: Literal["news", "blog", "webkr", "doc"],
        limit: int = 5,
        sort: Literal["sim", "date"] = "sim",
    ) -> List[NaverSearchResult]:
        url = f"https://openapi.naver.com/v1/search/{api}.json"
        headers = {"X-Naver-Client-Id": self.client_id, "X-Naver-Client-Secret": self.client_secret}
        params = {"query": query, "display": limit, "sort": sort}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            data = response.json()

        items = []

        for item in data.get("items", []):
            # HTML 태그 제거 및 특수문자 이스케이프 해제
            title = re.sub(r"</?b>", "", item.get("title", ""))
            title = html.unescape(title)
            description = re.sub(r"</?b>", "", item.get("description", ""))
            description = html.unescape(description)
            source_date = item.get("pubDate") or item.get("postdate", "")
            try:
                source_date = dateparser.parse(source_date)
            except (ValueError, TypeError):
                source_date = None

            link = item.get("link", "")
            items.append(NaverSearchResult(title=title, description=description, link=link, pub_date=source_date))
        return items


class NaverSearchStrategy(PlanExecutorStrategy):
    def __init__(self, settings: Settings):
        self.client = NaverSearchClient(settings=settings)
        self.crawler = Crawler()
        self.extractor = Extractor(settings=settings, crawler=self.crawler)

    @get_tracer(__name__).start_as_current_span("execute naver search")
    async def execute(self, plan: RetrievalPlan, context: ReplyContext, collector: RetrievalResultCollector):
        match plan.search_type:
            case "naver_web":
                search_api = "webkr"
            case "naver_news":
                search_api = "news"
            case "naver_blog":
                search_api = "blog"
            case "naver_doc":
                search_api = "doc"
            case _:
                logging.warning(f"NaverSearchStrategy does not support plan: {plan}")
                raise ValueError("Unsupported plan type")

        search_tasks = [
            asyncio.create_task(self.client.search(query=plan.query, api=search_api, limit=7, sort="sim")),
            asyncio.create_task(self.client.search(query=plan.query, api=search_api, limit=7, sort="date")),
        ]
        search_results_raw = await asyncio.gather(*search_tasks, return_exceptions=True)

        search_results = []
        for res in search_results_raw:
            if isinstance(res, Exception):
                logging.info("Naver search API call failed", exc_info=res)
            elif res:
                search_results.append(res)

        async def extract_worker(rid: str, search_result: NaverSearchResult):
            extraction = await self.extractor.extract(url=search_result.link, query=plan.query)
            if not extraction.content.strip():
                extraction.is_relevant = False
            await collector.add(
                RetrievalResult(
                    plan=plan,
                    result_id=rid,
                    content=extraction.content,
                    ref=UrlRef(value=search_result.link),
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=urlparse(search_result.link).netloc,
                    source_timestamp=search_result.pub_date,
                )
            )

        tasks = []
        for results in search_results:
            for result in results:
                rid = nanoid.generate()
                rresult = RetrievalResult(
                    plan=plan,
                    result_id=rid,
                    content=result.title + "\n" + result.description,
                    ref=UrlRef(value=result.link),
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=urlparse(result.link).netloc,
                    source_timestamp=result.pub_date,
                )
                tasks.append(asyncio.create_task(collector.add(rresult)))
                tasks.append(asyncio.create_task(extract_worker(rid, result)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logging.info("Extraction worker failed", exc_info=result)

    @override
    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type in ("naver_web", "naver_news", "naver_blog", "naver_doc")
