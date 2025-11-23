from typing import Literal

from pydantic import BaseModel
from pydantic_ai import ModelSettings, RunContext
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import PlanAction


class SummaryExtractorDeps(BaseModel):
    plan: PlanAction
    result: str


class SummaryExtractorOutput(BaseModel):
    summary: str
    relevance: Literal[0, 1, 2, 3]


summary_extractor = StructuredAgent(
    name="Summary Extractor",
    model=FallbackModel(
        OpenAIChatModel("openai/gpt-oss-20b", provider=OpenRouterProvider()),
        OpenAIChatModel("openai/gpt-oss-120b", provider=OpenRouterProvider()),
    ),
    model_settings=ModelSettings(
        extra_body={
            "reasoning": {
                "effort": "minimum",
                "enabled": False,
            },
        }
    ),
    deps_type=SummaryExtractorDeps,
    output_type=SummaryExtractorOutput,
)


@summary_extractor.instructions
async def instructions(_: RunContext[SummaryExtractorDeps]) -> str:
    return """
주어진 문서를 읽고, 검색 쿼리와 가장 잘 맞는 핵심 문장을 아주 짧게 요약하세요.
쿼리와 문서가 관련이 있는 정도를 0에서 3까지의 정수로 반환하세요.
3은 매우 관련이 있고, 0은 전혀 관련이 없습니다.
"""


@summary_extractor.user_prompt
async def user_prompt(deps: SummaryExtractorDeps) -> str:
    return f"""
[쿼리 지침]
{deps.plan.description}

[문서 내용]
{deps.result}
"""
