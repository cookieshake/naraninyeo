from __future__ import annotations

from typing import Any, AsyncIterator, Generic, TypeVar

# We only wrap pydantic-ai's Agent to avoid leaking its type externally
from pydantic_ai import Agent as _PydanticAgent

T = TypeVar("T")


class RunResult(Generic[T]):
    """Lightweight wrapper over pydantic-ai's run result.

    Exposes only the parts we use (`output`), while delegating other
    attributes to the underlying object for flexibility.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def output(self) -> T:  # pyright: ignore[reportGeneralTypeIssues]
        return self._inner.output

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _AgentStream:
    """Async context manager wrapper for streaming calls.

    Provides `.stream_text(delta=True|False)` as used by the codebase.
    """

    def __init__(self, inner_cm: Any) -> None:
        self._inner_cm = inner_cm
        self._entered: Any | None = None

    async def __aenter__(self) -> "_AgentStream":
        self._entered = await self._inner_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> Any:
        return await self._inner_cm.__aexit__(exc_type, exc, tb)

    def stream_text(self, *, delta: bool = False) -> AsyncIterator[str]:
        if self._entered is None:
            raise RuntimeError("Stream not entered; use 'async with agent.run_stream(...) as stream:'")
        return self._entered.stream_text(delta=delta)


class Agent(Generic[T]):
    """App-level Agent wrapper.

    - Keeps our public surface independent from pydantic-ai's concrete types
    - Provides `run` and `run_stream` used throughout the app
    """

    def __init__(self, inner: _PydanticAgent[Any, T]) -> None:
        self._inner = inner

    async def run(self, *args: Any, **kwargs: Any) -> RunResult[T]:
        result = await self._inner.run(*args, **kwargs)
        return RunResult(result)

    def run_stream(self, *args: Any, **kwargs: Any) -> _AgentStream:
        """Return an async context manager for streaming responses."""
        cm = self._inner.run_stream(*args, **kwargs)
        return _AgentStream(cm)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
