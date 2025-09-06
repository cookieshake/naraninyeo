from naraninyeo.domain.gateway.retrieval import (
    RetrievalPlanExecutor,
    RetrievalPlanner,
    RetrievalResultCollectorFactory,
)
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult
from naraninyeo.domain.variable import Variables
from naraninyeo.infrastructure.settings import Settings
from naraninyeo.domain.gateway.retrieval_post import RetrievalPostProcessor


class RetrievalUseCase:
    def __init__(
        self,
        planner: RetrievalPlanner,
        executor: RetrievalPlanExecutor,
        collector_factory: RetrievalResultCollectorFactory,
        settings: Settings,
        post_processor: RetrievalPostProcessor,
    ):
        self.planner = planner
        self.executor = executor
        self.collector_factory = collector_factory
        self.settings = settings
        self.post_processor = post_processor

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
        results = await collector.snapshot()
        return self.post_processor.process(results, context)
