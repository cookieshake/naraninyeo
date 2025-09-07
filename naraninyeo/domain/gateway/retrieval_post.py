from abc import ABC, abstractmethod

from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalResult


class RetrievalPostProcessor(ABC):
    @abstractmethod
    def process(self, results: list[RetrievalResult], context: ReplyContext) -> list[RetrievalResult]: ...
