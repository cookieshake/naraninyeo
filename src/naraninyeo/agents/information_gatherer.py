import asyncio
from typing import List, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.function import FunctionToolset

from naraninyeo.agents.base import StructuredAgent
from naraninyeo.core.interfaces import FinanceSearch, MessageRepository, NaverSearch, WebDocumentFetch
from naraninyeo.core.models import Bot, MemoryItem, Message, TenancyContext
from naraninyeo.toolsets.code_mode import CodeModeToolset


class InformationGathererDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    tctx: TenancyContext
    bot: Bot
    incoming_message: Message
    latest_messages: list[Message]
    memories: list[MemoryItem]
    message_repository: MessageRepository
    naver_search_client: NaverSearch
    finance_search_client: FinanceSearch
    web_document_fetcher: WebDocumentFetch
    use_tool_calls: bool
    prior_evaluation_feedback: str | None = None


class InformationGathererOutput(BaseModel):
    source: str
    content: str


_tools: FunctionToolset[InformationGathererDeps] = FunctionToolset()


@_tools.tool
async def naver_search(
    ctx: RunContext[InformationGathererDeps],
    search_type: Literal["general", "news", "blog", "document", "encyclopedia"],
    query: str,
    limit: int,
    order: Literal["sim", "date"] = "sim",
) -> str:
    """
    네이버 검색 도구입니다. 최신 뉴스, 백과사전 지식, 블로그 리뷰 등 외부 정보가 필요할 때 사용합니다.
    search_type:
      - "news": 시사, 사건, 최근 이슈 (order="date" 권장)
      - "encyclopedia": 사실, 개념, 정의, 인물 정보
      - "blog": 후기, 리뷰, 경험담, 맛집/여행 정보
      - "general": 위 카테고리에 해당하지 않는 일반 검색
      - "document": 공식 문서, 학술 자료
    query: 검색 쿼리 (핵심 키워드만, 조사/어미 제거. 예: "삼성전자의 주가가" → "삼성전자 주가")
    limit: 검색 결과 수 (최대 30, 보통 5-10이면 충분)
    order: 정렬 기준 (sim: 정확도순, date: 최신순)
    """
    nv_client = ctx.deps.naver_search_client
    results = await nv_client.search(
        search_type=search_type,
        query=query,
        limit=limit,
        order=order,
    )
    return "\n\n".join(
        f"Title: {result.title}\n"
        f"Link: {result.link}\n"
        f"Description: {result.description}\n"
        f"Published At: {result.published_at or 'N/A'}"
        for result in results
    )


@_tools.tool
async def fetch_webpage(ctx: RunContext[InformationGathererDeps], url: str) -> str:
    """
    웹페이지 내용을 가져오는 도구입니다. naver_search 결과의 링크를 열어 상세 내용을 확인할 때 사용합니다.
    url: 웹페이지 URL
    """
    fetcher = ctx.deps.web_document_fetcher
    content = await fetcher.fetch_document(url)
    return content.markdown_content


@_tools.tool
async def financial_data_lookup(
    ctx: RunContext[InformationGathererDeps],
    stock_name: str,
) -> str:
    """
    금융 데이터 조회 도구입니다. 주식, 지수, ETF 등 금융 데이터가 필요할 때 사용합니다.
    현재 가격, 단기/장기 가격 추이, 관련 뉴스를 함께 반환합니다.
    stock_name: 종목명 또는 회사명 (예: "삼성전자", "KODEX 200", "S&P500"). 코인·환율은 지원하지 않습니다.
    """
    fsc = ctx.deps.finance_search_client
    ticker = await fsc.search_symbol(stock_name)
    if ticker is None:
        return "종목을 찾을 수 없습니다."
    price = asyncio.create_task(fsc.search_current_price(ticker))
    short_term_price = asyncio.create_task(fsc.get_short_term_price(ticker))
    long_term_price = asyncio.create_task(fsc.get_long_term_price(ticker))
    news = asyncio.create_task(fsc.search_news(ticker))
    await asyncio.gather(price, short_term_price, long_term_price, news, return_exceptions=True)
    if price.exception():
        price_str = f"Error fetching price: {price.exception()}"
    else:
        price_str = price.result() or ""

    if short_term_price.exception():
        short_term_str = f"Error fetching short term price: {short_term_price.exception()}"
    else:
        short_term_str = "\n".join(f"{item.local_date}: {item.close_price}" for item in short_term_price.result())

    if long_term_price.exception():
        long_term_str = f"Error fetching long term price: {long_term_price.exception()}"
    else:
        long_term_str = "\n".join(f"{item.local_date}: {item.close_price}" for item in long_term_price.result())

    if news.exception():
        news_str = f"Error fetching news: {news.exception()}"
    else:
        news_str = "\n".join(f"[{item.source}, {item.timestamp}] {item.title}\n{item.body}" for item in news.result())
    return (
        f"Ticker Info:\n"
        f"Code: {ticker.code}\n"
        f"Type: {ticker.type}\n"
        f"Name: {ticker.name}\n"
        f"Current Price: {price_str}\n"
        f"Short Term Price Info:\n{short_term_str}\n\n"
        f"Long Term Price Info:\n{long_term_str}\n\n"
        f"Related News:\n{news_str}"
    )


@_tools.tool
async def chat_history_lookup(
    ctx: RunContext[InformationGathererDeps],
    keyword: str,
    limit: int,
) -> str:
    """
    대화 기록 조회 도구입니다. 사용자가 이전 대화를 언급하거나 ("아까", "전에 말한", "그거"),
    과거에 나눈 특정 주제에 대한 맥락이 필요할 때 사용합니다.
    keyword: 검색 키워드 (핵심 단어)
    limit: 검색 결과 수 (보통 5-10이면 충분)
    """
    results = await ctx.deps.message_repository.text_search_messages(
        tctx=ctx.deps.tctx,
        channel_id=ctx.deps.incoming_message.channel.channel_id,
        query=keyword,
        limit=limit,
    )
    return "\n\n".join(f"Timestamp: {msg.timestamp_iso}\nContent Preview: {msg.preview}" for msg in results)


async def _block_toolset_if_needed(
    ctx: RunContext[InformationGathererDeps], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition] | None:
    if not ctx.deps.use_tool_calls:
        return []
    return tool_defs


_code_mode_toolset = CodeModeToolset(_tools).prepared(_block_toolset_if_needed)

information_gatherer = StructuredAgent(
    name="Information Gatherer",
    model=OpenRouterModel("google/gemini-3.1-flash-lite-preview"),
    model_settings=OpenRouterModelSettings(
        openrouter_reasoning=OpenRouterReasoning(
            effort="low",
            enabled=False,
        ),
    ),
    deps_type=InformationGathererDeps,
    output_type=List[InformationGathererOutput],
    toolsets=[_code_mode_toolset],
)


@information_gatherer.instructions
async def instructions(ctx: RunContext[InformationGathererDeps]) -> str:
    return f"""
당신은 사용자의 질문에 답하기 위해 필요한 정보를 수집하는 AI입니다.
사용자의 질문, 대화 기록, 단기 기억 등 응답에 필요한 모든 정보를 수집하세요.
응답이 가능할 정도로 충분한 정보가 모이면, 수집을 중단하세요.

현재 위치는 대한민국의 수도 서울입니다.
현재 시간은 {ctx.deps.incoming_message.timestamp_iso} 입니다.

아래의 지침을 따르세요:
- 정보 수집이 필요하면 execute_code 도구를 사용해 Python 코드를 작성하세요.
- 코드 안에서 naver_search, fetch_webpage, financial_data_lookup, chat_history_lookup 함수를 직접 호출할 수 있습니다.
- 여러 정보를 한 번에 수집할 때는 asyncio.gather()를 활용해 병렬로 호출하세요.
- 수학 계산, 단위 변환, 데이터 변환 등 연산도 코드로 처리할 수 있습니다.
- 쿼리에 현재 시간이 필요할 경우 이를 반영하세요.
- '오늘', '최근' 등의 표현은 사용하지 말고 구체적인 날짜를 명시하세요.
- 날짜는 년, 월 등의 인간에게 친숙한 형식을 사용하세요.
- 도구 실행 결과를 검토한 뒤, 최종 답변에 필요한 핵심 정보만 주어진 형식의 목록으로 최종 반환하세요.

## 도구 선택 가이드
- 이전 대화 언급 ("아까", "전에 말한", "그거", "우리가 얘기한") → chat_history_lookup 먼저
- 주식/지수/ETF 질문 → financial_data_lookup (코인·환율은 지원 안 함, 대신 naver_search 사용)
- 시사/뉴스/최근 사건 → naver_search(search_type="news", order="date")
- 사실/개념/정의/인물 → naver_search(search_type="encyclopedia")
- 후기/리뷰/맛집/여행 → naver_search(search_type="blog")
- 검색 결과에서 상세 내용이 필요하면 → fetch_webpage로 링크 열기

## 도구가 불필요한 경우
- 단순 인사, 감사, 감정 표현 (예: "ㅋㅋ", "ㄱㅅ", "ㅎㅇ", "안녕")
- 대화 기록과 기억만으로 충분히 답변 가능한 경우
→ 도구를 호출하지 말고 빈 목록([])을 바로 반환하세요.
"""


@information_gatherer.user_prompt
async def user_prompt(deps: InformationGathererDeps) -> str:
    latest_messages_str = "\n".join(msg.preview for msg in deps.latest_messages)
    memories_str = "\n".join(
        f"- [{mem.kind}] {mem.content} ({mem.updated_at.strftime('%Y-%m-%d')})" for mem in deps.memories
    )
    return f"""
## 봇 정보
```
이름: {deps.bot.bot_name}
```

## 기억
```
{memories_str}
```

## 직전 대화 기록
```
{latest_messages_str}
```

## 새로 들어온 메시지
```
{deps.incoming_message.preview}
```

위 새로 들어온 메시지에 답하기 위해 필요한 모든 정보를 수집하세요.
{
        "## 이전 평가 피드백\\n이전 응답이 부적절하여 정보를 재수집합니다. 다른 검색어나 다른 도구를 활용하세요."
        if deps.prior_evaluation_feedback
        else ""
    }
"""
