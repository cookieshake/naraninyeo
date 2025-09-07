from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable, Iterable

from naraninyeo.core.llm.providers import LLMProviderRegistry
from naraninyeo.core.middleware import ChatMiddleware
from naraninyeo.core.pipeline.steps import PipelineStep
from naraninyeo.domain.gateway.retrieval import PlanExecutorStrategy
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory  # type: ignore circular import
from naraninyeo.infrastructure.pipeline.steps import PipelineDeps
from naraninyeo.infrastructure.settings import Settings

# Builder type aliases
RetrievalStrategyBuilder = Callable[[Settings, LLMAgentFactory], PlanExecutorStrategy]
ChatMiddlewareBuilder = Callable[[Settings], ChatMiddleware]
PipelineStepBuilder = Callable[[PipelineDeps], PipelineStep]


@dataclass
class AppRegistry:
    """Central registry of extension points for the app.

    - llm_provider_registry: register new LLM providers
    - retrieval_strategy_builders: register strategy builders discoverable by DI
    """

    llm_provider_registry: LLMProviderRegistry = field(default_factory=LLMProviderRegistry)
    retrieval_strategy_builders: list[RetrievalStrategyBuilder] = field(default_factory=list)
    chat_middleware_builders: list[ChatMiddlewareBuilder] = field(default_factory=list)
    pipeline_step_builders: dict[str, PipelineStepBuilder] = field(default_factory=dict)

    # Registration helpers
    def register_retrieval_strategy(self, builder: RetrievalStrategyBuilder) -> None:
        self.retrieval_strategy_builders.append(builder)

    def register_chat_middleware(self, builder: ChatMiddlewareBuilder) -> None:
        self.chat_middleware_builders.append(builder)

    def register_pipeline_step(self, name: str, builder: PipelineStepBuilder) -> None:
        self.pipeline_step_builders[name] = builder


class PluginManager:
    """Loads plugin modules and allows them to register to the AppRegistry.

    A plugin module may expose either:
      - a `register(registry: AppRegistry)` function, or
      - top-level `RETRIEVAL_STRATEGY_BUILDERS: Iterable[RetrievalStrategyBuilder]`.
      - top-level `CHAT_MIDDLEWARE_BUILDERS: Iterable[ChatMiddlewareBuilder]`.
      - top-level `PIPELINE_STEPS: dict[str, PipelineStepBuilder]`.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load_plugins(self, registry: AppRegistry) -> None:
        plugin_modules: Iterable[str] = getattr(self.settings, "PLUGINS", []) or []
        for mod_name in plugin_modules:
            module = importlib.import_module(mod_name)
            # Preferred: unified register(registry) function
            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(registry)
                continue

            # Fallback: well-known lists
            strategy_builders = getattr(module, "RETRIEVAL_STRATEGY_BUILDERS", None)
            if strategy_builders:
                for builder in strategy_builders:
                    registry.register_retrieval_strategy(builder)
            middleware_builders = getattr(module, "CHAT_MIDDLEWARE_BUILDERS", None)
            if middleware_builders:
                for builder in middleware_builders:
                    registry.register_chat_middleware(builder)
            pipeline_steps = getattr(module, "PIPELINE_STEPS", None)
            if pipeline_steps:
                for name, builder in dict(pipeline_steps).items():
                    registry.register_pipeline_step(name, builder)
