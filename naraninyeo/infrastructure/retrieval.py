import asyncio
from datetime import datetime
import html
import re
from typing import List, Optional, override, Literal
from textwrap import dedent
from urllib.parse import urlparse
import uuid
from crawl4ai import AsyncLoggerBase, AsyncWebCrawler, BrowserConfig, CrawlResult, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter, SemaphoreDispatcher
import httpx
import dateparser
import logfire

from markdownify import markdownify as md
from pydantic import BaseModel, computed_field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult, RetrievalStatus, RetrievalStatusReason
from naraninyeo.domain.gateway.retrieval import RetrievalPlanExecutor, RetrievalPlanner

from naraninyeo.domain.model.reply import KnowledgeReference, ReplyContext
from naraninyeo.infrastructure.embedding import TextEmbedder
from naraninyeo.infrastructure.settings import Settings

class AgentBasedRetrievalPlan(RetrievalPlan, BaseModel):
    query: str
    search_type: Literal[
        "naver_web",
        "naver_news",
        "naver_blog",
        "naver_doc",
        "chat_history"
    ]

class ImplRetrievalResult(RetrievalResult, BaseModel):
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    content: str
    source_name: str
    source_timestamp: Optional[datetime]
    ref: str

    # additional fields
    key: str
    query: str
    # whether this retrieval result is relevant to the original query
    is_relevant: Optional[bool]
    

class RetrievalPlannerAgent(RetrievalPlanner):
    @override
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        message = dedent(
        f"""
        직전 대화 기록:
        ---
        {"\n".join([msg.text_repr for msg in context.latest_history])}
        ---

        새로 들어온 메시지:
        {context.last_message.text_repr}

        위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요? 참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요.
        """).strip()

        result = await self.agent.run(message)
        plans = result.output

        logfire.debug(f"Retrieval plans generated: {[p.model_dump() for p in plans]}")
        return list(plans)


    def __init__(self, settings: Settings):
        self.settings = settings
        self.agent = Agent(
            model=OpenAIModel(
                model_name="openai/gpt-5-mini",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY
                )
            ),
            output_type=NativeOutput(List[AgentBasedRetrievalPlan]),
            instrument=True,
            model_settings=OpenAIModelSettings(
                timeout=20,
                extra_body={
                    "reasoning": {
                        "effort": "minimal"
                    }
                }
            ),
            system_prompt=dedent(
                """
                당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
                사용자의 질문과 대화 기록을 바탕으로, 어떤 종류의 검색을 수행할지 계획해야 합니다.

                다음과 같은 검색 유형을 사용할 수 있습니다:
                - naver_news: 뉴스 기사 검색, 최신 뉴스나 시사 정보에 적합
                - naver_blog: 블로그 글 검색, 개인적인 경험이나 일상적인 정보에 적합
                - naver_web: 일반 웹 검색, 다양한 웹사이트 정보가 필요할 때 적합
                - naver_doc: 학술 문서 검색, 연구나 학술적 정보에 적합
                - chat_history: 채팅 기록 검색, 이전 대화 내용을 기반으로 정보 검색에 적합

                필요에 따라 여러 유형을 선택하고 각각에 맞는 검색어를 생성하세요.
                예시:
                - 최신 정치 뉴스를 찾을 때: 'naver_news' 타입에 '대한민국 최신 정치 이슈' 쿼리
                - 요리법을 찾을 때: 'naver_blog' 타입에 '간단한 김치찌개 만드는 법' 쿼리
                - 학술 정보를 찾을 때: 'naver_doc' 타입에 '인공지능 윤리적 이슈 연구' 쿼리
                - 강아지에 대한 과거 대화 내용을 찾을 때: 'chat_history' 타입에 '강아지' 쿼리

                검색이 필요하지 않은 경우, 빈 배열을 반환하세요.
                검색이 필요한 경우 되도록이면 다양한 검색 유형을 포함하여 계획을 세우세요.
                """.strip()
            )
        )

    
class LoggerWrapper(AsyncLoggerBase):
    def debug(self, message: str, tag: str = "DEBUG", **kwargs):
        logfire.debug(f"{tag}: {message}", **kwargs)

    def info(self, message: str, tag: str = "INFO", **kwargs):
        logfire.debug(f"{tag}: {message}", **kwargs)

    def success(self, message: str, tag: str = "SUCCESS", **kwargs):
        logfire.debug(f"{tag}: {message}", **kwargs)

    def warning(self, message: str, tag: str = "WARNING", **kwargs):
        logfire.debug(f"{tag}: {message}", **kwargs)

    def error(self, message: str, tag: str = "ERROR", **kwargs):
        logfire.debug(f"{tag}: {message}", **kwargs)

    def url_status(self, url: str, success: bool, timing: float, tag: str = "FETCH", url_length: int = 100):
        logfire.debug(f"{tag}: {url} - {'SUCCESS' if success else 'FAILURE'} ({timing:.2f}s, {url_length} chars)")

    def error_status(self, url: str, error: str, tag: str = "ERROR", url_length: int = 100):
        logfire.debug(f"{tag}: {url} - {error} ({url_length} chars)")

class Crawler:
    def __init__(self):
        # self.crawler = AsyncWebCrawler(
        #     logger=LoggerWrapper(),
        #     config=BrowserConfig()
        # )
        # self.text_embedder = text_embedder
        pass

    async def start(self):
        # await self.crawler.start()
        pass

    async def stop(self):
        # await self.crawler.close()
        pass

    async def get_markdown_from_url(self, url: str) -> str:
        # filter = PruningContentFilter(threshold=1.5, threshold_type="dynamic")
        # md_generator = DefaultMarkdownGenerator(content_filter=filter)
        # config = CrawlerRunConfig(
        #     markdown_generator=md_generator,
        #     only_text=True,
        #     excluded_tags=["a"],
        #     page_timeout=3000
        # )
        # result: CrawlResult = await self.crawler.arun(
        #     url=url,
        #     config=config
        # ) # pyright: ignore[reportAssignmentType]
        # return result.markdown.fit_markdown # pyright: ignore[reportOptionalMemberAccess]
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            return md(html, strip=["a"])


class ExtractionResult(BaseModel):
    content: str
    is_relevant: Optional[bool]

class Extractor:
    def __init__(self, settings: Settings, crawler: Crawler) -> None:
        self.settings = settings
        self.crawler = crawler
        self.agent = Agent(
            model=OpenAIModel(
                model_name="openai/gpt-5-nano",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY,
                )
            ),
            # Structured output so we can know when content is irrelevant
            output_type=NativeOutput(ExtractionResult),
            model_settings=OpenAIModelSettings(
                timeout=5,
                extra_body={
                    "reasoning": {
                        "effort": "minimal"
                    }
                }
            ),
            system_prompt=dedent(
            """
            당신은 주어진 웹 검색 결과 마크다운 텍스트에서 쿼리와 관련된 핵심 정보를 정확하게 추출하는 AI입니다.

            - 반드시 마크다운 텍스트에 있는 내용만을 기반으로 추출해야 합니다.
            - 관련된 내용을 1~2문장으로 짧고 간결하게 요약하세요.
            - 텍스트는 독립적이고 완전한 의미를 담고 있어야 합니다.
            - 불필요한 설명이나 서론을 추가하지 말고, 추출된 텍스트만 제공하세요.
            - 추출된 내용만 간결하게 반환하고, 어떤 부가적인 설명도 덧붙이지 마세요.
            - 만약 관련된 내용이 전혀 없다면 content는 빈 문자열로 두고 is_relevant를 false로 설정하세요.
            """).strip()
        )
    
    async def extract(self, url: str, query: str) -> ExtractionResult:
        markdown = await self.crawler.get_markdown_from_url(url)
        if not markdown:
            logfire.warn(f"Failed to retrieve markdown for {url}")
            return ExtractionResult(content="", is_relevant=False)
        enhancement_result = await self.agent.run(dedent(
            f"""
            [마크다운 텍스트]
            ---
            {markdown}
            ---

            [쿼리]
            {query}

            위 마크다운 텍스트에서 위 쿼리와 직접적으로 관련된 핵심 정보만 1~2문장으로 요약하여 ExtractionResult 형태로 반환하세요.
            - 관련성이 낮거나 추론이 필요한 정보는 제외하세요.
            - 관련된 내용이 없다면 content는 빈 문자열로 두고 is_relevant는 false로 설정하세요.
            - 관련된 내용이 있다면 content에 그 요약을 넣고 is_relevant는 true로 설정하세요.
            """
        ))
        # enhancement_result.output 는 ExtractionResult 타입
        extraction: ExtractionResult = enhancement_result.output
        # 안전장치: 모델이 is_relevant를 누락했을 경우 content 유무로 결정
        if extraction.is_relevant is None:
            extraction.is_relevant = bool(extraction.content.strip())
        if not extraction.content.strip():
            extraction.is_relevant = False
        return extraction



class NaverSearchClient:
    def __init__(self, settings: Settings):
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET

    async def search(self, query: str, api: Literal["news", "blog", "webkr", "doc"], limit: int = 5, sort: Literal["sim", "date"] = "sim") -> List[ImplRetrievalResult]:
        url = f"https://openapi.naver.com/v1/search/{api}.json"
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        params = {"query": query, "display": limit, "sort": sort}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            data = response.json()

        items = []
        
        for item in data.get("items", []):
            # HTML 태그 제거 및 특수문자 이스케이프 해제
            title = re.sub(r"</?b>", "", item.get("title", ""))
            description = re.sub(r"</?b>", "", item.get("description", ""))
            description = html.unescape(description)
            source_date = item.get("pubDate") or item.get("postdate", "")
            try:
                source_date = dateparser.parse(source_date)
            except (ValueError, TypeError):
                source_date = None

            link = item.get("link", "")
            domain = urlparse(link).netloc

            content_text = (title + "\n" + description).strip()
            items.append(
                ImplRetrievalResult(
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=domain,
                    source_timestamp=source_date,
                    content=content_text,
                    query=query,
                    key=link if link else str(uuid.uuid4()),
                    ref=link,
                    is_relevant=False if not content_text else None
                )
            )
        return items


class DefaultRetrievalPlanExecutor(RetrievalPlanExecutor):
    @override
    async def execute(self, plans: list[RetrievalPlan], context: ReplyContext) -> List[RetrievalResult]:
        result_queue = asyncio.Queue[ImplRetrievalResult]()

        try:
            async with asyncio.TaskGroup() as tg:
                for plan in plans:
                    if isinstance(plan, AgentBasedRetrievalPlan):
                        if plan.search_type.startswith("naver_"):
                            tg.create_task(self._search_naver(plan, result_queue))
                        elif plan.search_type == "chat_history":
                            tg.create_task(self._search_chat_history(plan, context, result_queue))
        except asyncio.CancelledError:
            logfire.warn("Retrieval tasks were cancelled, so some results may be missing.")

        result: dict[str, ImplRetrievalResult] = {}
        while not result_queue.empty():
            item = await result_queue.get()
            result[item.key] = item
        results = list([r for r in result.values() if r.is_relevant is not False])
        logfire.debug(
            "Retrieval execution completed with {retrieval_count} results",
            retrieval_count=len(results),
            result=[item.model_dump() for item in results]
        )
        return list(results)

    def __init__(
        self,
        settings: Settings,
        naver_search_client: NaverSearchClient,
        message_repository: MessageRepository,
        text_embedder: TextEmbedder,
        crawler: Crawler,
        extractor: Extractor
    ):
        self.naver_search_client = naver_search_client
        self.message_repository = message_repository
        self.text_embedder = text_embedder
        self.crawler = crawler
        self.extractor = extractor

    async def _search_naver(self, plan: AgentBasedRetrievalPlan, result_queue: asyncio.Queue[ImplRetrievalResult]):
        api_map: dict[str, Literal["news", "blog", "webkr", "doc"]] = {
            "naver_news": "news",
            "naver_blog": "blog",
            "naver_web": "webkr",
            "naver_doc": "doc"
        }
        api = api_map.get(plan.search_type, "doc")
        results = asyncio.as_completed([
            self.naver_search_client.search(query=plan.query, api=api, limit=7, sort="date"),
            self.naver_search_client.search(query=plan.query, api=api, limit=7, sort="sim")
        ])
        async def enrich(item: ImplRetrievalResult):
            try:
                extraction = await self.extractor.extract(item.ref, plan.query)
                new_item = item.model_copy(update={
                    "content": extraction.content,
                    "is_relevant": extraction.is_relevant if extraction.content else False
                })
                await result_queue.put(new_item)
            except Exception as e:
                logfire.warn(
                    f"Error enriching retrieval result for ref={item.ref}: {type(e).__name__}: {e}",
                    exc_info=e
                )

        async with asyncio.TaskGroup() as tg:
            for task in results:
                result = await task
                for item in result:
                    await result_queue.put(item)
                    tg.create_task(enrich(item))

    async def _search_chat_history(self, plan: AgentBasedRetrievalPlan, context: ReplyContext, result_queue: asyncio.Queue[ImplRetrievalResult]):
        messages = await self.message_repository.search_similar_messages(
            channel_id=context.last_message.channel.channel_id,
            keyword=plan.query,
            limit=3
        )
        chunks = [
            self.message_repository.get_surrounding_messages(
                message=message, before=3, after=3
            ) for message in messages
        ]
        for task in asyncio.as_completed(chunks):
            chunk = await task
            chunk_str = "\n".join(msg.text_repr for msg in chunk)
            await result_queue.put(
                ImplRetrievalResult(
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    content=chunk_str,
                    source_name=chunk[-1].channel.channel_id,
                    source_timestamp=chunk[-1].timestamp,
                    key=chunk[-1].message_id,
                    query=plan.query,
                    ref= f"chat_history:{chunk[-1].timestamp_str}",
                    is_relevant=True
                )
            )
