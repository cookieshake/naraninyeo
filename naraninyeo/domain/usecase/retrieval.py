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
        results = await asyncio.wait_for(task, timeout=Variables.RETRIEVAL_EXECUTION_TIMEOUT)
        if task.cancelled():
            logfire.warning(
                "Retrieval execution was cancelled after {timeout} seconds",
                timeout=Variables.RETRIEVAL_EXECUTION_TIMEOUT
            )
        logfire.debug(
            "Retrieval execution completed with {retrieval_count} results",
            retrieval_count=len(results),
            results=[result.model_dump() for result in results]
        )
        return results
