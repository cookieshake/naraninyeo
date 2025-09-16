from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.infrastructure.settings import Settings


class LLMProvider(ABC):
    """Abstract LLM provider that produces pydantic-ai models."""

    @abstractmethod
    def create_model(self, model_name: str) -> OpenAIModel: ...


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._provider = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)

    def create_model(self, model_name: str) -> OpenAIModel:
        return OpenAIModel(model_name=model_name, provider=self._provider)


ProviderFactory = Callable[[Settings], LLMProvider]


class LLMProviderRegistry:
    """Registry for LLM providers by name.

    Keeps factories to allow provider instances to be configured from Settings when needed.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderFactory] = {}
        # Register built-in providers
        self.register("openrouter", lambda s: OpenRouterLLMProvider(s))

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._providers[name] = factory

    def has(self, name: str) -> bool:
        return name in self._providers

    def build(self, name: str, settings: Settings) -> LLMProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown LLM provider: {name}")
        return self._providers[name](settings)
