"""Plugin system primitives and built-in optional plugins."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable

from naraninyeo.assistant.llm_toolkit import LLMProviderRegistry
from naraninyeo.settings import Settings

if TYPE_CHECKING:
    from naraninyeo.app.pipeline import PipelineStep, PipelineTools
    from naraninyeo.assistant.llm_toolkit import LLMProvider, LLMToolFactory
    from naraninyeo.assistant.models import Message, ReplyContext
    from naraninyeo.assistant.retrieval import RetrievalStrategy


class ChatMiddleware:
    """Hook points around the chat pipeline. Methods default to no-ops."""

    async def before_handle(self, message: "Message") -> None: ...

    async def before_retrieval(self, context: "ReplyContext") -> None: ...

    async def after_retrieval(self, context: "ReplyContext") -> None: ...

    async def before_reply_stream(self, context: "ReplyContext") -> None: ...

    async def on_reply(self, reply: "Message") -> None: ...

    async def after_reply_stream(self) -> None: ...


RetrievalStrategyBuilder = Callable[[Settings, "LLMToolFactory"], "RetrievalStrategy"]
ChatMiddlewareBuilder = Callable[[Settings], ChatMiddleware]
PipelineStepBuilder = Callable[["PipelineTools"], "PipelineStep"]


@dataclass
class AppRegistry:
    llm_provider_registry: LLMProviderRegistry = field(default_factory=LLMProviderRegistry)
    retrieval_strategy_builders: list[RetrievalStrategyBuilder] = field(default_factory=list)
    chat_middleware_builders: list[ChatMiddlewareBuilder] = field(default_factory=list)
    pipeline_step_builders: dict[str, PipelineStepBuilder] = field(default_factory=dict)

    def register_llm_provider(self, name: str, factory: Callable[[Settings], "LLMProvider"]) -> None:
        self.llm_provider_registry.register(name, factory)

    def register_retrieval_strategy(self, builder: RetrievalStrategyBuilder) -> None:
        self.retrieval_strategy_builders.append(builder)

    def register_chat_middleware(self, builder: ChatMiddlewareBuilder) -> None:
        self.chat_middleware_builders.append(builder)

    def register_pipeline_step(self, name: str, builder: PipelineStepBuilder) -> None:
        self.pipeline_step_builders[name] = builder


class PluginManager:
    """Helper that loads plugin modules and lets them register hooks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load_plugins(self, registry: AppRegistry) -> None:
        plugin_modules: Iterable[str] = getattr(self.settings, "PLUGINS", []) or []
        for module_name in plugin_modules:
            # 모듈마다 register() 또는 상수 기반 후크를 찾아 순서대로 적용한다.
            module = importlib.import_module(module_name)
            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(registry)
                continue

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
