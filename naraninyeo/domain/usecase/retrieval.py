import asyncio

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.variable import Variables
from naraninyeo.domain.gateway.retrieval import RetrievalPlanExecutor, RetrievalPlanner
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult

class RetrievalUseCase:
    def __init__(
        self,
        planner: RetrievalPlanner,
        executor: RetrievalPlanExecutor
    ):
        self.planner = planner
        self.executor = executor

    async def plan_retrieval(self, context: ReplyContext) -> list[RetrievalPlan]:
        plans = await self.planner.plan(context)
        return plans

    async def execute_retrieval(self, plans: list[RetrievalPlan], context: ReplyContext) -> list[RetrievalResult]:
        results = []

        async with asyncio.timeout(Variables.RETRIEVAL_EXECUTION_TIMEOUT):
            async for plan in self.executor.execute(plans, context): # type: ignore
                results.append(plan)

        return results
