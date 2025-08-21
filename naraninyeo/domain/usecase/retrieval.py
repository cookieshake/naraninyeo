import asyncio

import logfire

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.variable import Variables
from naraninyeo.domain.gateway.retrieval import RetrievalPlanExecutor, RetrievalPlanner
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult, RetrievalStatus

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
        task = asyncio.create_task(self.executor.execute(plans, context))
        timed_out = False
        try:
            await asyncio.wait_for(task, timeout=Variables.RETRIEVAL_EXECUTION_TIMEOUT)
        except asyncio.TimeoutError:
            timed_out = True
        results = await task
        if timed_out:
            logfire.warning(
                "Retrieval execution timed out. Executed {executed_plans} plans out of {all_plans}",
                executed_plans=len([r for r in results if r.status == RetrievalStatus.SUCCESS]),
                all_plans=len(results)
            )

        return results
