from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from naraninyeo.core.pipeline.types import EmitFn, PipelineState


class PipelineStep(ABC):
    """A composable unit in the chat pipeline."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def run(self, state: PipelineState, emit: EmitFn) -> None: ...


StepBuilder = Callable[[], PipelineStep]


class StepRegistry:
    def __init__(self) -> None:
        self._steps: dict[str, PipelineStep] = {}

    def register(self, step: PipelineStep) -> None:
        if step.name in self._steps:
            raise ValueError(f"Duplicate pipeline step name: {step.name}")
        self._steps[step.name] = step

    def get(self, name: str) -> PipelineStep:
        if name not in self._steps:
            raise KeyError(f"Unknown pipeline step: {name}")
        return self._steps[name]

    def has(self, name: str) -> bool:
        return name in self._steps
