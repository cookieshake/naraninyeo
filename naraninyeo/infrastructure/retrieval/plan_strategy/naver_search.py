import asyncio
import html
import logging
import re
from datetime import datetime
from textwrap import dedent
from typing import List, Literal, Optional
from urllib.parse import urljoin, urlparse

import dateparser
import httpx
import nanoid
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from opentelemetry.trace import get_tracer
from pydantic import BaseModel

from naraninyeo.core.contracts.retrieval import PlanExecutorStrategy, RetrievalResultCollector
from naraninyeo.core.llm.agent import Agent
from naraninyeo.core.llm.spec import native
from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import (
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.settings import Settings


class Crawler:
    def __init__(self):
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
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        follow_redirects=True,
                        timeout=20.0,
                    )
                    response.raise_for_status()
                    html = response.text
                    soup = BeautifulSoup(html, "html.parser")
                    break
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(0.5)
            else:
                logging.info("Failed to fetch url after retries", exc_info=last_exc)
                return ""

            # make http request to all iframes and insert html into original
            async def get_soup_from_iframe(iframe_url: str) -> BeautifulSoup:
                async with httpx.AsyncClient() as client:
                    response = await client.get(iframe_url)
                    response.raise_for_status()
                    iframe_html = response.text
                    return BeautifulSoup(iframe_html, "html.parser")

            iframes_to_process = [iframe for iframe in soup.find_all("iframe") if isinstance(iframe.get("src"), str)]  # type: ignore
            if iframes_to_process:
                # Using a single client for all iframe requests is more efficient.
                # For even better performance and consistency (e.g. User-Agent), consider
                # creating one client for the entire get_markdown_from_url function.
                async with httpx.AsyncClient() as iframe_client:

                    async def get_soup_from_iframe(iframe_url: str) -> BeautifulSoup:
                        response = await iframe_client.get(iframe_url)
                        response.raise_for_status()
                        iframe_html = response.text
                        return BeautifulSoup(iframe_html, "html.parser")

                    iframe_links = [urljoin(url, iframe.get("src")) for iframe in iframes_to_process]  # type: ignore
                    iframe_htmls = await asyncio.gather(
                        *[get_soup_from_iframe(iframe_url) for iframe_url in iframe_links],
                        return_exceptions=True,
                    )
                for iframe, iframe_html in zip(iframes_to_process, iframe_htmls, strict=False):
                    if isinstance(iframe_html, BeautifulSoup):
                        iframe.replace_with(iframe_html)
                    else:
                        logging.warning(f"Failed to retrieve iframe {iframe.get('src')}: {iframe_html}")  # type: ignore
            tags_to_remove = ["a", "button", "iframe"]
            for tag in tags_to_remove:
                for element in soup.find_all(tag):
                    element.decompose()
            return self.markdown_converter.convert_soup(soup)


class ExtractionResult(BaseModel):
    content: str
    is_relevant: Optional[bool]


class Extractor:
    def __init__(self, settings: Settings, crawler: Crawler, llm_factory: LLMAgentFactory) -> None:
        self.settings = settings
        self.crawler = crawler
        self.agent: Agent[ExtractionResult] = llm_factory.extractor_agent(output_type=native(ExtractionResult))

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
            {markdown[:4000]}
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
        extraction: ExtractionResult = enhancement_result.output  # pyright: ignore[reportAssignmentType]
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
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.client = NaverSearchClient(settings=settings)
        self.crawler = Crawler()
        self.extractor = Extractor(settings=settings, crawler=self.crawler, llm_factory=llm_factory)

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

    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type in ("naver_web", "naver_news", "naver_blog", "naver_doc")
