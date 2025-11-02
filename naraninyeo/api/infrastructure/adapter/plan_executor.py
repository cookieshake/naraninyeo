import asyncio
from copy import deepcopy
from typing import Dict, List, Literal

from naraninyeo.api.agents.summary_extractor import SummaryExtractorDeps, summary_extractor
from naraninyeo.api.infrastructure.adapter.naver_search import NaverSearchClient
from naraninyeo.api.infrastructure.interfaces import MessageRepository, PlanActionExecutor
from naraninyeo.core.models import ActionType, MemoryItem, Message, PlanAction, PlanActionResult, TenancyContext
from naraninyeo.core.settings import Settings


class ActionResultCollector:
    def __init__(self) -> None:
        self.results: Dict[PlanAction, PlanActionResult] = {}

    def add_result(self, action: PlanAction, result: PlanActionResult) -> None:
        self.results[action] = result

    def get_results(self) -> Dict[PlanAction, PlanActionResult]:
        return deepcopy(self.results)


class DefaultPlanActionExecutor(PlanActionExecutor):
    def __init__(
        self,
        settings: Settings,
        message_repository: MessageRepository,
    ) -> None:
        self.settings = settings
        self.search_client = NaverSearchClient(settings=settings)
        self.message_repository = message_repository

    async def _execute_action(
        self,
        tctx: TenancyContext,
        action: PlanAction,
        channel_id: str,
        collector: ActionResultCollector,
    ) -> None:
        match action.action_type:
            case (
                ActionType.SEARCH_WEB_GENERAL |
                ActionType.SEARCH_WEB_NEWS |
                ActionType.SEARCH_WEB_BLOG |
                ActionType.SEARCH_WEB_SCHOLAR |
                ActionType.SEARCH_WEB_ENCYCLOPEDIA
            ):
                action_kv: dict[
                    ActionType,
                    Literal["general", "news", "blog", "document", "encyclopedia"]
                ] = {
                        ActionType.SEARCH_WEB_GENERAL: "general",
                        ActionType.SEARCH_WEB_NEWS: "news",
                        ActionType.SEARCH_WEB_BLOG: "blog",
                        ActionType.SEARCH_WEB_SCHOLAR: "document",
                        ActionType.SEARCH_WEB_ENCYCLOPEDIA: "encyclopedia",
                    }
                results = await self.search_client.search(
                    search_type=action_kv[action.action_type],
                    query=action.query or "",
                    limit=5
                )
                result_str = "\n".join([
                    (
                        f"{result.link}\n"
                        f"{result.published_at}\n"
                        f"{result.title}\n"
                        f"{result.description}\n"
                    )
                    for result in results
                ])
                collector.add_result(
                    action=action,
                    result=PlanActionResult(
                        action=action,
                        status="COMPLETED",
                        content=result_str,
                    )
                )
                deps = SummaryExtractorDeps(
                    plan=action,
                    result=result_str,
                )
                result = await summary_extractor.run_with_generator(deps)
                collector.add_result(
                    action=action,
                    result=PlanActionResult(
                        action=action,
                        status="COMPLETED",
                        content=result.output.summary,
                    )
                )
            case ActionType.SEARCH_CHAT_HISTORY:
                messages = await self.message_repository.text_search_messages(
                    tctx=tctx,
                    channel_id=channel_id,
                    query=action.query or "",
                    limit=5
                )
                async with asyncio.TaskGroup() as tg:
                    before = []
                    after = []
                    for message in messages:
                        before.append(
                            tg.create_task(
                                self.message_repository.get_channel_messages_before(
                                    tctx=tctx,
                                    channel_id=channel_id,
                                    before_message_id=message.message_id,
                                    limit=5
                                )
                            )
                        )
                        after.append(
                            tg.create_task(
                                self.message_repository.get_channel_messages_after(
                                    tctx=tctx,
                                    channel_id=channel_id,
                                    after_message_id=message.message_id,
                                    limit=5
                                )
                            )
                        )
                before = await asyncio.gather(*before)
                after = await asyncio.gather(*after)

                result = [
                    f"{'\n'.join(m.preview for m in before)}\n"
                    f"{message.preview}\n"
                    f"{'\n'.join(m.preview for m in after)}"
                    for message in messages
                ]
                collector.add_result(
                    action=action,
                    result=PlanActionResult(
                        action=action,
                        status="COMPLETED",
                        content="\n".join(result),
                    )
                )

    async def execute_actions(
        self,
        tctx: TenancyContext,
        incoming_message: Message,
        latest_history: list[Message],
        memories: list[MemoryItem],
        actions: list[PlanAction]
    ) -> List[PlanActionResult]:
        collector = ActionResultCollector()
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for action in actions:
                    task = tg.create_task(
                        self._execute_action(
                            tctx=tctx,
                            action=action,
                            channel_id=incoming_message.channel.channel_id,
                            collector=collector
                        )
                    )
                    tasks.append(task)
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        except asyncio.TimeoutError:
            pass
        return list(collector.get_results().values())
