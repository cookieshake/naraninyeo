"""Factories and utilities for the assistant's LLM integrations."""

from dataclasses import dataclass
from textwrap import dedent
from typing import Any, AsyncIterator, Callable, Generic, TypeVar

from pydantic_ai import Agent as _PydanticAgent
from pydantic_ai import NativeOutput, PromptedOutput, TextOutput, ToolOutput
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.output import OutputSpec
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.assistant.models import RetrievalPlan
from naraninyeo.assistant.prompts import (
    EXTRACTOR_PROMPT,
    MEMORY_PROMPT,
    PLANNER_PROMPT,
    REPLY_PROMPT,
    PromptTemplate,
)
from naraninyeo.settings import Settings

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TOverride = TypeVar("TOverride")


class LLMProvider:
    """Simple interface so plugins can supply custom providers."""

    def create_model(self, model_name: str) -> OpenAIModel:  # pragma: no cover
        raise NotImplementedError


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._provider = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)

    def create_model(self, model_name: str) -> OpenAIModel:
        return OpenAIModel(model_name=model_name, provider=self._provider)


ProviderFactory = Callable[[Settings], LLMProvider]


class LLMProviderRegistry:
    """Keeps track of available LLM providers by name."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderFactory] = {}
        self.register("openrouter", lambda settings: OpenRouterLLMProvider(settings))

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._providers[name] = factory

    def build(self, name: str, settings: Settings) -> LLMProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown LLM provider: {name}")
        return self._providers[name](settings)


@dataclass(frozen=True)
class LLMTask(Generic[TIn, TOut]):
    name: str
    model_setting: str
    timeout_setting: str
    prompt: PromptTemplate[TIn]
    output: OutputSpec[TOut] | None = None


class LLMTool(Generic[TIn, TOut]):
    """Wraps a pydantic-ai agent and a prompt template."""

    def __init__(self, agent: _PydanticAgent[Any, TOut], prompt: PromptTemplate[TIn]):
        self._agent = agent
        self._prompt = prompt

    async def run(self, payload: TIn) -> TOut:
        prompt = self._prompt.user_prompt(payload)
        result = await self._agent.run(prompt)
        return result.output

    async def stream_text(self, payload: TIn, *, delta: bool = True) -> AsyncIterator[str]:
        prompt = self._prompt.user_prompt(payload)
        async with self._agent.run_stream(prompt) as stream:
            async for chunk in stream.stream_text(delta=delta):
                yield chunk


class LLMToolFactory:
    """Builds ready-to-use tools for reply generation, planning, and extraction."""

    def __init__(self, settings: Settings, provider_registry: LLMProviderRegistry | None = None):
        provider_name = getattr(settings, "LLM_PROVIDER", "openrouter")
        registry = provider_registry or LLMProviderRegistry()
        try:
            self._provider = registry.build(provider_name, settings)
        except KeyError:
            self._provider = OpenRouterLLMProvider(settings)
        self.settings = settings

    def _select_output_spec(self, output_spec: OutputSpec[TOut], model: OpenAIModel) -> OutputSpec[TOut]:
        if output_spec is str:
            return output_spec  # type: ignore[return-value]
        if isinstance(output_spec, (NativeOutput, PromptedOutput, TextOutput, ToolOutput)):
            return output_spec
        profile = getattr(model, "profile", None)
        if getattr(profile, "supports_json_schema_output", False):
            return NativeOutput(output_spec)  # type: ignore[arg-type]
        return output_spec

    def _build_agent(
        self,
        task: LLMTask[TIn, TOut],
        output_override: OutputSpec[Any] | None = None,
    ) -> _PydanticAgent[Any, Any]:
        model_name = getattr(self.settings, task.model_setting)
        timeout = getattr(self.settings, task.timeout_setting)
        model = self._provider.create_model(model_name)
        desired_output = output_override if output_override is not None else task.output
        agent_kwargs: dict[str, Any] = {
            "model": model,
            "instrument": InstrumentationSettings(event_mode="logs"),
            "model_settings": OpenAIModelSettings(
                timeout=int(timeout),
                extra_body={"reasoning": {"effort": "minimal"}},
            ),
            "system_prompt": dedent(task.prompt.system_prompt(self.settings)).strip(),
        }
        if desired_output is not None:
            output_spec = self._select_output_spec(desired_output, model)
            agent_kwargs["output_type"] = output_spec
        return _PydanticAgent(**agent_kwargs)

    def tool(
        self,
        task: LLMTask[TIn, TOut],
        *,
        output_override: OutputSpec[Any] | None = None,
    ) -> LLMTool[TIn, Any]:
        agent = self._build_agent(task, output_override)
        return LLMTool(agent, task.prompt)

    def reply_tool(self) -> LLMTool[Any, str]:
        return self.tool(REPLY_TASK)

    def planner_tool(self) -> LLMTool[Any, list[RetrievalPlan]]:
        return self.tool(PLANNER_TASK)

    def memory_tool(self, *, output_type: OutputSpec[TOverride]) -> LLMTool[Any, TOverride]:
        return self.tool(MEMORY_TASK, output_override=output_type)

    def extractor_tool(self, *, output_type: OutputSpec[TOverride]) -> LLMTool[Any, TOverride]:
        return self.tool(EXTRACTOR_TASK, output_override=output_type)


REPLY_TASK = LLMTask[Any, str](
    name="reply",
    model_setting="REPLY_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_REPLY",
    prompt=REPLY_PROMPT,
)

PLANNER_TASK = LLMTask[Any, list[RetrievalPlan]](
    name="planner",
    model_setting="PLANNER_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_PLANNER",
    prompt=PLANNER_PROMPT,
    output=NativeOutput(list[RetrievalPlan]),
)

MEMORY_TASK = LLMTask[Any, Any](
    name="memory",
    model_setting="MEMORY_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_MEMORY",
    prompt=MEMORY_PROMPT,
)

EXTRACTOR_TASK = LLMTask[Any, Any](
    name="extractor",
    model_setting="EXTRACTOR_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_EXTRACTOR",
    prompt=EXTRACTOR_PROMPT,
)
