from __future__ import annotations

from textwrap import dedent
from typing import Any, TypeVar

from pydantic_ai import Agent, NativeOutput, PromptedOutput, TextOutput, ToolOutput
from pydantic_ai.output import OutputSpec
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.openai import OpenAIModelSettings

from naraninyeo.core.llm.providers import LLMProviderRegistry, OpenRouterLLMProvider
from naraninyeo.infrastructure.settings import Settings

# Generic type variable for agent output
T = TypeVar("T")


class LLMAgentFactory:
    def __init__(self, settings: Settings, provider_registry: LLMProviderRegistry | None = None):
        self.settings = settings
        # Build provider from registry if available; default to built-in OpenRouter
        registry = provider_registry or LLMProviderRegistry()
        provider_name = getattr(settings, "LLM_PROVIDER", "openrouter")
        try:
            self._provider = registry.build(provider_name, settings)
        except KeyError:
            # Safe fallback to OpenRouter if misconfigured
            self._provider = OpenRouterLLMProvider(settings)


    def _select_output_spec(self, output_type: OutputSpec[T], model) -> OutputSpec[T]:
        """Choose the best OutputSpec based on model capabilities.

        - If caller provided an OutputSpec (Native/Prompted/Text/Tool), use it as-is.
        - If `str`, keep text mode (for streaming and simplicity).
        - Otherwise: prefer NativeOutput only when the model supports native JSON schema output.
          Fallback to raw type (which will default to tool-based structured output) for broader compatibility.
        """
        if output_type is str:
            return output_type  # type: ignore[return-value]
        if isinstance(output_type, (NativeOutput, PromptedOutput, TextOutput, ToolOutput)):
            return output_type
        try:
            if getattr(getattr(model, "profile", None), "supports_json_schema_output", False):
                return NativeOutput(output_type)  # type: ignore[return-value]
        except Exception:
            pass
        return output_type

    def _agent(self, *, model_name: str, timeout: int, output_type: OutputSpec[T], system_prompt: str) -> Agent[T]:
        model = self._provider.create_model(model_name=model_name)
        output_spec = self._select_output_spec(output_type, model)
        return Agent(
            model=model,
            output_type=output_spec,
            instrument=InstrumentationSettings(event_mode="logs"),
            model_settings=OpenAIModelSettings(timeout=timeout, extra_body={"reasoning": {"effort": "minimal"}}),
            system_prompt=dedent(system_prompt).strip(),
        )

    def reply_agent(self, *, output_type: OutputSpec[T] = str) -> Agent[T]:
        return self._agent(
            model_name=self.settings.REPLY_MODEL_NAME,
            timeout=self.settings.LLM_TIMEOUT_SECONDS_REPLY,
            output_type=output_type,
            system_prompt=f"""
            [정체성]
            - 이름: {self.settings.BOT_AUTHOR_NAME}
            - 역할: 생각을 넓혀주는 대화 파트너
            - 성격: 중립적이고 친근함

            [답변 규칙]
            - 간결하고 핵심만 말함
            - 한쪽에 치우치지 않고 다양한 관점 제시
            - 무조건 한국어 반말 사용
            - "검색 결과에 따르면" 같은 표현 절대 사용 금지
            - "시간 이름: 메시지" 형식 사용 금지
            - 대화 맥락 우선: 직전 대화의 흐름과 톤을 최우선으로 맞출 것
            - 참고 정보는 보조자료: 대화 맥락과 충돌하면 참고 정보를 과감히 무시할 것
            - 주제 일탈 금지: 사용자가 원치 않으면 새로운 화제를 열지 말 것
            """,
        )

    def planner_agent(self, *, output_type: OutputSpec[T]) -> Agent[T]:
        return self._agent(
            model_name=self.settings.PLANNER_MODEL_NAME,
            timeout=self.settings.LLM_TIMEOUT_SECONDS_PLANNER,
            output_type=output_type,
            system_prompt="""
            당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
            사용자의 질문, 대화 기록, 단기 기억을 바탕으로 아래 타입 중 필요한 것을 선택하여 계획하세요.

            사용 가능한 검색 타입:
            - naver_news: 최신 뉴스를 찾을 때
            - naver_blog: 개인 경험/후기를 찾을 때
            - naver_web: 일반 웹 페이지 전반 탐색
            - naver_doc: 학술/문서 기반 정보
            - wikipedia: 일반 상식/개념/사전적 정보
            - chat_history: 과거 대화 내용 탐색

            필요 없으면 빈 배열을 반환하고, 필요한 경우 여러 타입을 조합할 수 있습니다.
            각 계획에는 search_type과 적절한 query를 포함하세요.
            """,
        )

    def memory_agent(self, *, output_type: OutputSpec[T]) -> Agent[T]:
        return self._agent(
            model_name=self.settings.MEMORY_MODEL_NAME,
            timeout=self.settings.LLM_TIMEOUT_SECONDS_MEMORY,
            output_type=output_type,
            system_prompt="""
            다음 대답에 유용할 수 있는 단기 기억 후보를 0~3개 추출하세요.
            - 너무 일반적이거나 길거나 추론이 필요한 내용은 제외
            - 명시적 선호, 일정/약속, 지시/요청 요약 등만 포함
            - 각 항목은 200자 이내, 중요도(1~5)는 보수적으로
            - 필요시 ttl_hours(1~48)를 제안; 없으면 기본 TTL 사용
            - 적절치 않으면 빈 배열 반환
            """,
        )

    def extractor_agent(self, *, output_type: OutputSpec[T]) -> Agent[T]:
        return self._agent(
            model_name=self.settings.EXTRACTOR_MODEL_NAME,
            timeout=self.settings.LLM_TIMEOUT_SECONDS_EXTRACTOR,
            output_type=output_type,
            system_prompt="""
            당신은 웹 페이지의 마크다운 텍스트와 사용자의 검색 쿼리를 보고,
            관련된 핵심 정보가 있는지 판단하고 있다면 1~2문장으로 정확히 요약합니다.
            - 반드시 텍스트에 있는 사실만 사용, 추론 금지
            - 관련 없으면 빈 내용으로 반환
            """,
        )
