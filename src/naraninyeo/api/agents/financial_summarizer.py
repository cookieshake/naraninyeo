from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import PlanAction


class FinancialSummarizerDeps(BaseModel):
    action: PlanAction
    price: str
    short_term_price: str
    long_term_price: str
    news: str


financial_summarizer = StructuredAgent(
    name="Financial Summarizer",
    model=OpenRouterModel("x-ai/grok-4-fast"),
    model_settings=OpenRouterModelSettings(
        openrouter_reasoning=OpenRouterReasoning(
            effort="low",
            enabled=False,
        ),
    ),
    deps_type=FinancialSummarizerDeps,
    output_type=str,
)


@financial_summarizer.instructions
async def instructions(_: RunContext[FinancialSummarizerDeps]) -> str:
    return """
당신은 증권/금융 정보 요약 전문가입니다.

## 역할
사용자의 질문에 답변하기 위해 수집된 금융 데이터를 분석하고 핵심 내용을 간결하게 요약합니다.
"""


@financial_summarizer.user_prompt
async def user_prompt(deps: FinancialSummarizerDeps) -> str:
    return f"""
다음 금융 데이터를 분석하고 사용자 질문에 답변할 수 있도록 요약하세요.

## 필요한 정보
쿼리: {deps.action.query}
설명: {deps.action.description}

## 관련 뉴스
{deps.news}

## 현재 가격
{deps.price}

## 최근
{deps.short_term_price}

## 장기 가격
{deps.long_term_price}

위 쿼리에 대해 수집된 데이터를 바탕으로 응답에 필요한 핵심 정보를 요약해주세요.
"""
