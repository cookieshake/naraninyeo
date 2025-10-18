"""Execution helpers shared across retrieval strategies."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

from naraninyeo.assistant.models import (
    ReplyContext,
    RetrievalPlan,
    RetrievalResult,
)
from naraninyeo.settings import Settings

if TYPE_CHECKING:
    from naraninyeo.assistant.retrieval.planner import RetrievalPlanLog


class RetrievalResultCollector:
    """Collects retrieval results in memory for later post-processing."""

    def __init__(self) -> None:
        self._results: dict[str, RetrievalResult] = {}

    async def add(self, item: RetrievalResult) -> None:
        self._results[item.result_id] = item

    async def snapshot(self) -> list[RetrievalResult]:
        return list(self._results.values())


class RetrievalResultCollectorFactory:
    def create(self) -> RetrievalResultCollector:
        return RetrievalResultCollector()


@runtime_checkable
class RetrievalStrategy(Protocol):
    def supports(self, plan: RetrievalPlan) -> bool: ...

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None: ...


class RetrievalExecutor:
    """Coordinates concurrent execution of retrieval strategies."""

    def __init__(self, max_concurrency: int | None = None) -> None:
        self._strategies: list[RetrievalStrategy] = []
        self._semaphore = asyncio.Semaphore(max_concurrency or 999999)

    def register(self, strategy: RetrievalStrategy) -> None:
        if not isinstance(strategy, RetrievalStrategy):
            raise TypeError("Strategy must define 'supports' and 'execute' methods")
        self._strategies.append(strategy)

    @property
    def strategies(self) -> list[RetrievalStrategy]:
        return list(self._strategies)

    async def execute(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        from naraninyeo.assistant.retrieval.planner import RetrievalPlanLog

        tasks: list[asyncio.Task[None]] = []
        logs: list[RetrievalPlanLog] = []
        try:
            for plan in plans:
                matched = False
                for strategy in self._strategies:
                    if strategy.supports(plan):
                        matched = True

                        async def run_with_sem(s=strategy, p=plan) -> None:
                            # 동시에 너무 많은 전략이 실행되지 않도록 세마포어로 조절한다.
                            async with self._semaphore:
                                await s.execute(p, context, collector)

                        tasks.append(asyncio.create_task(run_with_sem()))
                        break
                logs.append(RetrievalPlanLog(plan=plan, matched=matched))
                if not matched:
                    logging.warning("No executor found for plan: %s", plan.model_dump())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logging.info("A retrieval strategy failed", exc_info=result)
        except asyncio.CancelledError:
            logging.info("Retrieval tasks were cancelled, so some results may be missing.")
        return logs

    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        timeout_seconds: float,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        try:
            return await asyncio.wait_for(
                self.execute(plans, context, collector),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logging.info("Retrieval execution timed out; returning partial results")
            return []


class HeuristicRetrievalRanker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, item: RetrievalResult) -> float:
        score = 1.0
        search_type = getattr(item.plan, "search_type", None)
        score += float(self.settings.RANK_WEIGHTS.get(search_type or "", 0.0))
        ts = item.source_timestamp
        if isinstance(ts, datetime):
            try:
                now = datetime.now(ts.tzinfo or timezone.utc)
                window = timedelta(hours=int(self.settings.RECENCY_WINDOW_HOURS))
                age = now - ts
                if age <= window:
                    # 최신 결과일수록 가산점을 부여해 답변의 신선도를 높인다.
                    fraction = max(0.0, 1.0 - age.total_seconds() / window.total_seconds())
                    score += float(self.settings.RECENCY_BONUS_MAX) * fraction
            except Exception:
                pass
        return score


class RetrievalPostProcessor:
    """Deduplicate and rank retrieval results before they reach the LLM."""

    def __init__(self, settings: Settings, ranker: HeuristicRetrievalRanker):
        self.settings = settings
        self.ranker = ranker

    def process(self, results: list[RetrievalResult], context: ReplyContext) -> list[RetrievalResult]:
        filtered = [r for r in results if r.content and r.content.strip()]
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievalResult] = []
        for item in filtered:
            try:
                ref_attr = getattr(item.ref, "as_text", None)
                if isinstance(ref_attr, str):
                    ref_text = ref_attr
                elif callable(ref_attr):
                    ref_text = str(ref_attr())
                else:
                    ref_text = str(item.ref)
            except Exception:
                ref_text = str(item.ref)
            key = (ref_text, item.content.strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        try:
            deduped.sort(key=lambda r: self.ranker.score(r), reverse=True)
        except Exception:
            deduped.sort(key=lambda r: r.result_id)
        # 상위 N개만 남겨 LLM 입력이 너무 길어지지 않게 제어한다.
        return deduped[: max(1, self.settings.MAX_KNOWLEDGE_REFERENCES)]


class RetrievalLogger:
    """Simple observer that records which plans were matched."""

    def __init__(self) -> None:
        self.entries: list[RetrievalPlanLog] = []

    def record(self, entries: Iterable[RetrievalPlanLog]) -> None:
        self.entries.extend(entries)
