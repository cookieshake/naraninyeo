"""쿼리를 기반으로 마크다운 텍스트에서 관련 정보를 추출하는 에이전트"""

from typing import List

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.core.config import Settings

class Extractor:
    """쿼리를 기반으로 마크다운 텍스트에서 관련 정보를 추출하는 클래스"""

    def __init__(self, settings: Settings):
        """Extractor 초기화"""
        self.settings = settings
        # 추출 에이전트 생성
        self.agent = Agent(
            model=OpenAIModel(
                model_name="x-ai/grok-3-mini",
                provider=OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY,
                )
            ),
            instrument=True,
            model_settings=OpenAIModelSettings(
                timeout=20
            )
        )
        
        # 시스템 프롬프트 설정
        self.agent.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        """추출 에이전트의 시스템 프롬프트를 생성합니다."""
        return """당신은 주어진 마크다운 텍스트에서 사용자의 질문과 관련된 핵심 정보를 정확하게 추출하는 AI입니다.

- 반드시 마크다운 텍스트에 있는 내용만을 기반으로 추출해야 합니다.
- 관련된 내용을 1~2문장으로 짧고 간결하게 요약하세요.
- 텍스트는 독립적이고 완전한 의미를 담고 있어야 합니다.
- 불필요한 설명이나 서론을 추가하지 말고, 추출된 텍스트만 제공하세요.
- 추출된 내용만 간결하게 반환하고, 어떤 부가적인 설명도 덧붙이지 마세요."""

    def _create_prompt(self, markdown_text: str, query: str) -> str:
        """추출 에이전트용 프롬프트를 생성합니다."""
        return f"""[마크다운 텍스트]
---
{markdown_text}
---

[사용자 질문]
{query}

위 마크다운 텍스트에서 위 사용자 질문과 관련된 내용만 아주 짧게 추출해주세요."""

    async def run(self, markdown_text: str, query: str) -> str:
        """
        마크다운 텍스트와 쿼리를 받아 관련 정보를 추출합니다.

        Args:
            markdown_text: 정보 추출의 대상이 되는 마크다운 텍스트입니다.
            query: 추출할 정보에 대한 사용자 질문입니다.

        Returns:
            추출된 텍스트 목록을 담은 텍스트를 반환합니다.
        """
        prompt = self._create_prompt(markdown_text, query)
        output = (await self.agent.run(prompt)).output
        return output
