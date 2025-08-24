from abc import abstractmethod, ABC

from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult


class RetrievalResultCollector(ABC):
    """Abstract interface to collect RetrievalResult items incrementally."""

    @abstractmethod
    async def add(self, item: RetrievalResult) -> None: ...

    @abstractmethod
    async def snapshot(self) -> list[RetrievalResult]: ...


class RetrievalResultCollectorFactory(ABC):
    """Factory for creating a new RetrievalResultCollector per execution."""

    @abstractmethod
    def create(self) -> RetrievalResultCollector: ...


class PlanExecutorStrategy(ABC):
    """Strategy interface that can execute one plan type. Used by composite executors."""

    @abstractmethod
    def supports(self, plan: RetrievalPlan) -> bool: ...

    @abstractmethod
    async def execute(self, plan: RetrievalPlan, context: ReplyContext, collector: RetrievalResultCollector):
        """
        Execute the plan and push ImplRetrievalResult-like items into result_queue.
        We keep the queue and stop_event untyped here to avoid a hard dependency on infrastructure types.
        Optionally, add items into the provided collector for partial-progress consumption.
        """
        ...


class RetrievalPlanner(ABC):
    @abstractmethod
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]: ...


class RetrievalPlanExecutor(ABC):
    @property
    @abstractmethod
    def strategies(self) -> list[PlanExecutorStrategy]:
        """The strategies used to execute concrete plan types."""
        ...

    @abstractmethod
    def register_strategy(self, strategy: PlanExecutorStrategy) -> None:
        """Register an additional plan executor strategy."""
        ...

    @abstractmethod
    async def execute(
        self, plans: list[RetrievalPlan], context: ReplyContext, collector: RetrievalResultCollector
    ) -> None: ...

    @abstractmethod
    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        timeout_seconds: float,
        collector: RetrievalResultCollector,
    ) -> None:
        """Execute plans but return partial results if a timeout occurs."""
        ...
