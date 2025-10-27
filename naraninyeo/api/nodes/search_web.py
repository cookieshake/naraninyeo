"""Task that performs external web searches."""

from __future__ import annotations

from naraninyeo.api.infrastructure.interfaces import WebSearchClient
from naraninyeo.api.models import MessageProcessingState
from naraninyeo.core import FlowContext, RetrievalPlan
from naraninyeo.core.task import TaskBase, TaskResult


class SearchWebTask(TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]):
    def __init__(self, client: WebSearchClient, *, default_max_results: int = 5) -> None:
        super().__init__(client=client, default_max_results=default_max_results)
        self._client = client
        self._default_max_results = default_max_results

    async def run(self, context: FlowContext, payload: MessageProcessingState) -> TaskResult[MessageProcessingState]:
        plan = payload.retrieval_plan or RetrievalPlan(
            search_type="web",
            query=payload.inbound.content.text,
            max_results=self._default_max_results,
        )
        knowledge = await self._client.search(plan)
        payload.knowledge = list(knowledge)
        context.set_state("web_results", len(knowledge))
        return TaskResult(output=payload, diagnostics={"web_results": len(knowledge)})
