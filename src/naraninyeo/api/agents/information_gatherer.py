import asyncio
from typing import List, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import ModelHTTPError, ModelSettings, PromptedOutput, RunContext
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.api.agents.financial_summarizer import FinancialSummarizerDeps
from naraninyeo.api.infrastructure.adapter.finance_search import FinanceSearchClient
from naraninyeo.api.infrastructure.adapter.naver_search import NaverSearchClient
from naraninyeo.api.infrastructure.interfaces import MessageRepository
from naraninyeo.core.container import container
from naraninyeo.core.models import ActionType, Bot, MemoryItem, Message, ResponsePlan, TenancyContext


class InformationGathererDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    tctx: TenancyContext
    bot: Bot
    incoming_message: Message
    latest_messages: list[Message]
    memories: list[MemoryItem]
    message_repository: MessageRepository
    naver_search_client: NaverSearchClient

class InformationGathererOutput(BaseModel):
    source: str
    content: str


information_gatherer = StructuredAgent(
    name="Information Gatherer",
    model=FallbackModel(
        OpenAIChatModel("z-ai/glm-4.5-air", provider=OpenRouterProvider()),
        OpenAIChatModel("google/gemini-2.5-flash", provider=OpenRouterProvider()),
        fallback_on=lambda err: isinstance(err, ModelHTTPError) and err.status_code > 500,
    ),
    model_settings=ModelSettings(
        parallel_tool_calls=True,
        extra_body={
            "reasoning": {
                "effort": "none",
                "enabled": False,
            },
        }
    ),
    deps_type=InformationGathererDeps,
    output_type=List[InformationGathererOutput],
)


@information_gatherer.instructions
async def instructions(ctx: RunContext[InformationGathererDeps]) -> str:
    return f"""
당신은 사용자의 질문에 답하기 위해 필요한 정보를 수집하는 AI입니다.
사용자의 질문, 대화 기록, 단기 기억 등 응답에 필요한 모든 정보를 수집하세요.
응답이 가능할 정도로 충분한 정보가 모이면, 수집을 중단하세요.

현재 시간은 {ctx.deps.incoming_message.timestamp_iso} 입니다.

아래의 지침을 따르세요:
- 필요 없으면 빈 배열을 반환하고, 필요한 경우 여러 타입을 조합할 수 있습니다.
- query를 포함하지 않은 검색은 계획에 포함하지 말고 설명도 작성하지 마세요.
- 각 계획에는 적절한 query와 description을 포함하세요.
- 쿼리에 현재 시간이 필요할 경우 이를 반영하세요.
- '오늘', '최근' 등의 표현은 사용하지 말고 구체적인 날짜를 명시하세요.
- 날짜는 년, 월 등의 인간에게 친숙한 형식을 사용하세요.
- 다양한 검색 타입을 조합하여 사용자의 질문에 답할 수 있도록 계획하세요.
"""


@information_gatherer.user_prompt
async def user_prompt(deps: InformationGathererDeps) -> str:
    latest_messages_str = "\n".join(msg.preview for msg in deps.latest_messages)
    memories_str = "\n".join(f"- {mem.content}" for mem in deps.memories)
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
"""

@information_gatherer.tool
async def naver_search(
    ctx: RunContext[InformationGathererDeps],
    search_type:  Literal["general", "news", "blog", "document", "encyclopedia"],
    query: str,
    limit: int,
    order: Literal["sim", "date"] = "sim",
) -> List[InformationGathererOutput]:
    '''
    네이버 검색 도구입니다.
    search_type: 검색 유형 (general, news, blog, document, encyclopedia)
    query: 검색 쿼리
    limit: 검색 결과 수 (최대 30)
    order: 정렬 기준 (sim: 정확도순, date: 최신순)
    '''
    nv_client = ctx.deps.naver_search_client
    results = await nv_client.search(
        search_type=search_type,
        query=query,
        limit=limit,
        order=order,
    )
    return [
        InformationGathererOutput(
            source=f"Naver {search_type} Search (Query: {query})",
            content=f"Title: {result.title}\n"
                    f"Description: {result.description}\n"
                    f"Published At: {result.published_at or 'N/A'}"
        )
        for result in results
    ]

@information_gatherer.tool_plain
async def financial_data_lookup(
    stock_name: str,
) -> InformationGathererOutput:
    '''
    금융 데이터 조회 도구입니다.
    stock_name: 종목명
    '''
    fsc = FinanceSearchClient()
    ticker = await fsc.search_symbol(stock_name)
    if ticker is None:
        raise ValueError("Ticker not found for query: {}".format(stock_name))
    price = asyncio.create_task(fsc.search_current_price(ticker))
    short_term_price = asyncio.create_task(fsc.get_short_term_price(ticker))
    long_term_price = asyncio.create_task(fsc.get_long_term_price(ticker))
    news = asyncio.create_task(fsc.search_news(ticker))
    await asyncio.gather(price, short_term_price, long_term_price, news, return_exceptions=True)

    if isinstance(price, Exception):
        price = ""
    else:
        price = price.result() or ""

    if isinstance(short_term_price, Exception):
        short_term_price = ""
    else:
        short_term_price = short_term_price.result()
        short_term_price = "\n".join(f"{item.local_date}: {item.close_price}" for item in short_term_price)

    if isinstance(long_term_price, Exception):
        long_term_price = ""
    else:
        long_term_price = long_term_price.result()
        long_term_price = "\n".join(f"{item.local_date}: {item.close_price}" for item in long_term_price)

    if isinstance(news, Exception):
        news = ""
    else:
        news = news.result()
        news = "\n".join(f"[{item.source}, {item.timestamp}] {item.title}\n{item.body}" for item in news)
    content = f"Ticker Info:\n" \
              f"Code: {ticker.code}\n" \
              f"Type: {ticker.type}\n" \
              f"Name: {ticker.name}\n" \
              f"Nation: {ticker.nation}\n" \
              f"Current Price: {price}\n" \
              f"Short Term Price Info:\n{short_term_price}\n\n" \
              f"Long Term Price Info:\n{long_term_price}\n\n" \
              f"Related News:\n{news}"
    return InformationGathererOutput(
        source=f"Financial Data Lookup (Stock Name: {stock_name})",
        content=content,
    )

@information_gatherer.tool
async def chat_history_lookup(
    ctx: RunContext[InformationGathererDeps],
    keyword: str,
    limit: int,
) -> List[InformationGathererOutput]:
    '''
    대화 기록 조회 도구입니다.
    keyword: 검색 키워드
    limit: 검색 결과 수
    '''
    results = await ctx.deps.message_repository.text_search_messages(
        tctx=ctx.deps.tctx,
        channel_id=ctx.deps.incoming_message.channel.channel_id,
        query=keyword,
        limit=limit,
    )
    return [
        InformationGathererOutput(
            source="Chat History Lookup",
            content=f"Timestamp: {msg.timestamp_iso}\n"
                    f"Content Preview: {msg.preview}"
        )
        for msg in results
    ]
