from abc import ABC, abstractmethod

from naraninyeo.domain.model.retrieval import RetrievalResult


class RetrievalRanker(ABC):
    @abstractmethod
    def score(self, item: RetrievalResult) -> float: ...

