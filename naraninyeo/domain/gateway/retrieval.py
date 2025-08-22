from abc import abstractmethod, ABC
from typing import AsyncIterator, List

from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalPlan, RetrievalResult


class RetrievalPlanner(ABC):
    @abstractmethod
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        ...

class RetrievalPlanExecutor(ABC):
    @abstractmethod
    async def execute(self, plans: list[RetrievalPlan], context: ReplyContext) -> List[RetrievalResult]:
        ...
