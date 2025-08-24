from naraninyeo.domain.gateway.retrieval import (
    RetrievalPlanExecutor,
    RetrievalPlanner,
    RetrievalResultCollectorFactory,
)
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult
from naraninyeo.domain.variable import Variables


class RetrievalUseCase:
    def __init__(
        self,
        planner: RetrievalPlanner,
        executor: RetrievalPlanExecutor,
        collector_factory: RetrievalResultCollectorFactory,
    ):
        self.planner = planner
        self.executor = executor
        self.collector_factory = collector_factory

    async def plan_retrieval(self, context: ReplyContext) -> list[RetrievalPlan]:
        plans = await self.planner.plan(context)
        return plans

    async def execute_retrieval(self, plans: list[RetrievalPlan], context: ReplyContext) -> list[RetrievalResult]:
        collector = self.collector_factory.create()
        await self.executor.execute_with_timeout(
            plans,
            context,
            Variables.RETRIEVAL_EXECUTION_TIMEOUT,
            collector=collector,
        )
        return await collector.snapshot()
