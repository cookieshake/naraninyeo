import asyncio
import logging
from copy import deepcopy
from typing import Dict, List, Literal

from opentelemetry.trace import get_tracer, get_current_span

from naraninyeo.api.agents.summary_extractor import SummaryExtractorDeps, summary_extractor
from naraninyeo.api.infrastructure.adapter.naver_search import NaverSearchClient
from naraninyeo.api.infrastructure.adapter.web_document import WebDocumentFetcher
from naraninyeo.api.infrastructure.interfaces import IdGenerator, MessageRepository, PlanActionExecutor
from naraninyeo.core.models import ActionType, MemoryItem, Message, PlanAction, PlanActionResult, TenancyContext
from naraninyeo.core.settings import Settings


class ActionResultCollector:
    def __init__(self) -> None:
        self.results: Dict[str, PlanActionResult] = {}

    def add_result(self, action: PlanAction, result: PlanActionResult) -> None:
        self.results[result.action_result_id] = result

    def remove_result(self, action_result_id: str) -> None:
        if action_result_id in self.results:
            del self.results[action_result_id]

    def get_results(self) -> List[PlanActionResult]:
        result = list(self.results.values())
        result.sort(key=lambda r: r.priority, reverse=True)
        return result


class DefaultPlanActionExecutor(PlanActionExecutor):
    def __init__(
        self,
        settings: Settings,
        message_repository: MessageRepository,
        id_generator: IdGenerator,
    ) -> None:
        self.settings = settings
        self.search_client = NaverSearchClient(settings=settings)
        self.message_repository = message_repository
        self.id_generator = id_generator
        self.web_document_fetcher = WebDocumentFetcher()

    async def _enhance_result_with_fetch(
        self,
        collector: ActionResultCollector,
        plan: PlanAction,
        plan_action_result: PlanActionResult,
    ) -> None:
        try:
            if not plan_action_result.link:
                return

            fetched_content = await self.web_document_fetcher.fetch_document(plan_action_result.link)
            extract_summary_deps = SummaryExtractorDeps(plan=plan, result=fetched_content.markdown_content)
            summary = await summary_extractor.run_with_generator(extract_summary_deps)
            if summary.output.relevance == 0:
                collector.remove_result(plan_action_result.action_result_id)
                return
            enhanced_result = deepcopy(plan_action_result)
            enhanced_result.content = summary.output.summary
            enhanced_result.priority = summary.output.relevance
            enhanced_result.timestamp = (
                fetched_content.meta_tags.get("article:published_time") or enhanced_result.timestamp
            )
            collector.add_result(action=plan_action_result.action, result=enhanced_result)
        except Exception as e:
            logging.warning(f"Failed to enhance result for action {plan.action_type}: {e}")

    @get_tracer(__name__).start_as_current_span("execute_action")
    async def _execute_action(
        self,
        tctx: TenancyContext,
        action: PlanAction,
        channel_id: str,
        collector: ActionResultCollector,
    ) -> None:
        span = get_current_span()
        span.set_attribute("plan.action_type", action.action_type.value)
        span.set_attribute("plan.action_query", action.query or "")
        match action.action_type:
            case (
                ActionType.SEARCH_WEB_GENERAL
                | ActionType.SEARCH_WEB_NEWS
                | ActionType.SEARCH_WEB_BLOG
                | ActionType.SEARCH_WEB_SCHOLAR
                | ActionType.SEARCH_WEB_ENCYCLOPEDIA
            ):
                action_kv: dict[ActionType, Literal["general", "news", "blog", "document", "encyclopedia"]] = {
                    ActionType.SEARCH_WEB_GENERAL: "general",
                    ActionType.SEARCH_WEB_NEWS: "news",
                    ActionType.SEARCH_WEB_BLOG: "blog",
                    ActionType.SEARCH_WEB_SCHOLAR: "document",
                    ActionType.SEARCH_WEB_ENCYCLOPEDIA: "encyclopedia",
                }
                results = await self.search_client.search(
                    search_type=action_kv[action.action_type], query=action.query or "", limit=12
                )
                tasks = []
                for result in results:
                    arid = self.id_generator.generate_id()
                    aresult = PlanActionResult(
                        action_result_id=arid,
                        action=action,
                        status="COMPLETED",
                        link=result.link,
                        source=result.link,
                        content=f"[{result.title}]\n{result.description}",
                        timestamp=result.published_at,
                    )
                    collector.add_result(action=action, result=aresult)
                    tasks.append(
                        asyncio.create_task(
                            self._enhance_result_with_fetch(
                                collector=collector, plan=action, plan_action_result=aresult
                            )
                        )
                    )
                await asyncio.gather(*tasks, return_exceptions=True)

            case ActionType.SEARCH_CHAT_HISTORY:
                messages = await self.message_repository.text_search_messages(
                    tctx=tctx, channel_id=channel_id, query=action.query or "", limit=5
                )
                async with asyncio.TaskGroup() as tg:
                    before = []
                    after = []
                    for message in messages:
                        before.append(
                            tg.create_task(
                                self.message_repository.get_channel_messages_before(
                                    tctx=tctx, channel_id=channel_id, before_message_id=message.message_id, limit=5
                                )
                            )
                        )
                        after.append(
                            tg.create_task(
                                self.message_repository.get_channel_messages_after(
                                    tctx=tctx, channel_id=channel_id, after_message_id=message.message_id, limit=5
                                )
                            )
                        )
                before = await asyncio.gather(*before)
                after = await asyncio.gather(*after)

                result = []
                for b, c, a in zip(before, messages, after, strict=False):
                    result.append(f"{'\n'.join(m.preview for m in b)}\n{c.preview}\n{'\n'.join(m.preview for m in a)}")
                collector.add_result(
                    action=action,
                    result=PlanActionResult(
                        action_result_id=self.id_generator.generate_id(),
                        action=action,
                        status="COMPLETED",
                        content="\n".join(result),
                    ),
                )

    async def execute_actions(
        self,
        tctx: TenancyContext,
        incoming_message: Message,
        latest_history: list[Message],
        memories: list[MemoryItem],
        actions: list[PlanAction],
    ) -> List[PlanActionResult]:
        collector = ActionResultCollector()
        try:
            tasks = []
            for action in actions:
                task = asyncio.create_task(
                    self._execute_action(
                        tctx=tctx,
                        action=action,
                        channel_id=incoming_message.channel.channel_id,
                        collector=collector,
                    )
                )
                tasks.append(task)
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=20)
        except TimeoutError:
            pass
        return collector.get_results()
