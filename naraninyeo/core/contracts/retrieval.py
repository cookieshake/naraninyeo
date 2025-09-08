from __future__ import annotations

from abc import ABC, abstractmethod

from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import RetrievalPlan, RetrievalResult


class RetrievalResultCollector(ABC):
    @abstractmethod
    async def add(self, item: RetrievalResult) -> None: ...

    @abstractmethod
    async def snapshot(self) -> list[RetrievalResult]: ...


class RetrievalResultCollectorFactory(ABC):
    @abstractmethod
    def create(self) -> RetrievalResultCollector: ...


class PlanExecutorStrategy(ABC):
    @abstractmethod
    def supports(self, plan: RetrievalPlan) -> bool: ...

    @abstractmethod
    async def execute(self, plan: RetrievalPlan, context: ReplyContext, collector: RetrievalResultCollector): ...
