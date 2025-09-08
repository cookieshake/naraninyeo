import asyncio
import logging
from typing import List

from pydantic import BaseModel

from naraninyeo.core.contracts.retrieval import PlanExecutorStrategy, RetrievalResultCollector
from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import RetrievalPlan


class LocalPlanExecutor:
    def __init__(self, max_concurrency: int | None = None) -> None:
        # Use instance-level strategy registry to avoid cross-instance leakage
        self._strategies: List[PlanExecutorStrategy] = []
        self._semaphore = asyncio.Semaphore(max_concurrency or 999999)

    @property
    def strategies(self) -> list[PlanExecutorStrategy]:
        return self._strategies

    def register_strategy(self, strategy: PlanExecutorStrategy) -> None:
        self._strategies.append(strategy)

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

                        async def run_with_sem(s=strategy, p=plan):
                            async with self._semaphore:
                                await s.execute(p, context, collector)

                        tasks.append(asyncio.create_task(run_with_sem()))
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
