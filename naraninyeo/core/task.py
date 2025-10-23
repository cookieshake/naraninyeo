"""Asynchronous task primitives used by flows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ContextT = TypeVar("ContextT")


class TaskError(RuntimeError):
    """Raised when a task cannot complete successfully."""

    def __init__(self, task_name: str, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(f"{task_name}: {message}")
        self.task_name = task_name
        self.cause = cause


@dataclass(slots=True)
class TaskResult(Generic[OutputT]):
    """Wrapper for task outputs to include optional diagnostics."""

    output: OutputT
    diagnostics: dict[str, Any] | None = None


class TaskBase(ABC, Generic[ContextT, InputT, OutputT]):
    """Base class for every asynchronous task used in flows."""

    def __init__(self, *, name: str | None = None, **dependencies: Any) -> None:
        self._name = name or self.__class__.__name__
        self._dependencies = dependencies

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> dict[str, Any]:
        return self._dependencies

    async def __call__(self, context: ContextT, payload: InputT) -> TaskResult[OutputT]:
        try:
            result = await self.run(context, payload)
            if isinstance(result, TaskResult):
                return result
            return TaskResult(output=result)
        except TaskError:
            raise
        except BaseException as exc:  # pragma: no cover - defensive guard
            raise TaskError(self.name, "unhandled exception") from exc

    @abstractmethod
    async def run(self, context: ContextT, payload: InputT) -> TaskResult[OutputT] | OutputT:
        """Override to implement task behaviour."""
