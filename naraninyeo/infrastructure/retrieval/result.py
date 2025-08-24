from naraninyeo.domain.gateway.retrieval import (
    RetrievalResultCollector,
    RetrievalResultCollectorFactory,
)
from naraninyeo.domain.model.retrieval import RetrievalResult


class InMemoryRetrievalResultCollector(RetrievalResultCollector):
    def __init__(self):
        self._results = {}

    async def add(self, item: RetrievalResult) -> None:
        self._results[item.result_id] = item

    async def snapshot(self) -> list[RetrievalResult]:
        return list(self._results.values())


class InMemoryRetrievalResultCollectorFactory(RetrievalResultCollectorFactory):
    def create(self) -> RetrievalResultCollector:
        return InMemoryRetrievalResultCollector()
