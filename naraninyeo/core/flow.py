"""Flow abstractions used to compose async tasks."""

from __future__ import annotations

import asyncio
from typing import Any, Generic, Iterable, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.generics import GenericModel

from naraninyeo.core.task import TaskBase, TaskError, TaskResult

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class FlowError(RuntimeError):
    """Raised when a flow cannot produce a result."""

    def __init__(self, flow_name: str, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(f"{flow_name}: {message}")
        self.flow_name = flow_name
        self.cause = cause


class FlowRetryPolicy(BaseModel):
    """Configures retry behaviour for individual tasks within a flow."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    max_attempts: int = 1
    base_delay: float = 0.0
    multiplier: float = 2.0
    max_delay: float = 10.0

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts

    def delay_for(self, attempt: int) -> float:
        if self.base_delay <= 0:
            return 0.0
        delay = self.base_delay * (self.multiplier ** max(attempt - 1, 0))
        return min(delay, self.max_delay)


class FlowContext(BaseModel):
    """Mutable execution context shared across tasks within a flow."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)

    def set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str, default: Any | None = None) -> Any:
        return self.state.get(key, default)

    def append_diagnostic(self, line: str) -> None:
        self.diagnostics.append(line)


class FlowExecutionResult(GenericModel, Generic[OutputT]):
    """Represents the outcome of a flow execution."""

    flow_name: str
    succeeded: bool
    output: OutputT | None = None
    context: FlowContext | None = None
    diagnostics: Iterable[str] = Field(default_factory=tuple)


class FlowBase(Generic[InputT, OutputT]):
    """Base class for flows that compose multiple tasks."""

    def __init__(
        self,
        *,
        name: str | None = None,
        tasks: Sequence[TaskBase[FlowContext, Any, Any]] | None = None,
        retry_policy: FlowRetryPolicy | None = None,
        task_timeout: float | None = None,
    ) -> None:
        self._name = name or self.__class__.__name__
        self._tasks = list(tasks or [])
        self._retry_policy = retry_policy or FlowRetryPolicy()
        self._task_timeout = task_timeout

    @property
    def name(self) -> str:
        return self._name

    def register_task(self, task: TaskBase[FlowContext, Any, Any]) -> None:
        self._tasks.append(task)

    def build_context(
        self, *, metadata: dict[str, Any] | None = None, state: dict[str, Any] | None = None
    ) -> FlowContext:
        return FlowContext(state=state or {}, metadata=metadata or {})

    async def execute(self, context: FlowContext, payload: InputT) -> FlowExecutionResult[OutputT]:
        current_payload: Any = payload
        for task in self._tasks:
            attempt = 0
            while True:
                try:
                    context.append_diagnostic(f"task:{task.name}:start")
                    result = await self._run_task(task, context, current_payload)
                    current_payload = result.output
                    if result.diagnostics:
                        context.diagnostics.extend(
                            f"task:{task.name}:{key}={value}" for key, value in result.diagnostics.items()
                        )
                    context.append_diagnostic(f"task:{task.name}:success")
                    break
                except TaskError as exc:
                    context.append_diagnostic(f"task:{task.name}:error:{exc}")
                    attempt += 1
                    if not self._retry_policy.should_retry(attempt):
                        raise FlowError(self.name, f"task {task.name} failed", cause=exc) from exc
                    delay = self._retry_policy.delay_for(attempt)
                    if delay > 0:
                        await asyncio.sleep(delay)
        return FlowExecutionResult(
            flow_name=self.name,
            succeeded=True,
            output=current_payload,
            context=context,
            diagnostics=context.diagnostics,
        )

    async def _run_task(
        self, task: TaskBase[FlowContext, Any, Any], context: FlowContext, payload: Any
    ) -> TaskResult[Any]:  # pragma: no cover - exercised via execute
        if self._task_timeout is None:
            return await task(context, payload)
        return await asyncio.wait_for(task(context, payload), timeout=self._task_timeout)
