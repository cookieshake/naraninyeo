from contextlib import AbstractAsyncContextManager
from typing import Awaitable, Callable, TypeAlias, TypeVar

from pydantic_ai import Agent
from pydantic_ai.result import StreamedRunResult
from pydantic_ai.run import AgentRunResult

Tdeps = TypeVar("Tdeps")
Tout = TypeVar("Tout")

PromptGenerator: TypeAlias = Callable[[Tdeps], Awaitable[str]]

class StructuredAgent(Agent[Tdeps, Tout]):
    user_prompt_generator: PromptGenerator

    def user_prompt(self, callable: PromptGenerator) -> PromptGenerator:
        self.user_prompt_generator = callable
        return callable

    async def run_with_generator(
        self,
        deps: Tdeps,
        **kwargs
    ) -> AgentRunResult[Tout]:
        prompt = await self.user_prompt_generator(deps)
        return await self.run(prompt, deps=deps, **kwargs)

    async def run_stream_with_generator(
        self,
        deps: Tdeps,
        **kwargs
    ) -> AbstractAsyncContextManager[StreamedRunResult[Tdeps, Tout]]:
        prompt = await self.user_prompt_generator(deps)
        return self.run_stream(prompt, deps=deps, **kwargs)
