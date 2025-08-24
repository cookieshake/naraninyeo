import asyncio
import logging
from typing import List, override

from pydantic import BaseModel
from naraninyeo.domain.gateway.retrieval import (
    PlanExecutorStrategy,
    RetrievalPlanExecutor,
    RetrievalResultCollector,
)
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan


class LocalPlanExecutor(RetrievalPlanExecutor):
    _strategies: List[PlanExecutorStrategy] = []

    @property
    def strategies(self) -> list[PlanExecutorStrategy]:
        return self._strategies

    def register_strategy(self, strategy: PlanExecutorStrategy) -> None:
        self._strategies.append(strategy)

    @override
    async def execute(
        self, plans: list[RetrievalPlan], context: ReplyContext, collector: RetrievalResultCollector
    ) -> None:
        tasks = []
        try:
            for plan in plans:
                matched = False
                for strategy in self.strategies:
                    if strategy.supports(plan):
                        matched = True
                        tasks.append(asyncio.create_task(strategy.execute(plan, context, collector)))
                        break
                if not matched:
                    logging.warning(
                        f"No executor found for plan: {plan.model_dump() if isinstance(plan, BaseModel) else str(plan)}"
                    )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logging.info("A retrieval strategy failed", exc_info=result)
        except asyncio.CancelledError:
            logging.info("Retrieval tasks were cancelled, so some results may be missing.")

    @override
    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        timeout_seconds: float,
        collector: RetrievalResultCollector,
    ) -> None:
        """Execute plans with a timeout; return partial results if time runs out."""
        try:
            await asyncio.wait_for(self.execute(plans, context, collector), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logging.info("Retrieval execution timed out; returning partial results")
