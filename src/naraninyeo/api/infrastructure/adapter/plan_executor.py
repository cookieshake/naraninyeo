import asyncio
import logging
from copy import deepcopy
from typing import Dict, List, Literal

from opentelemetry.trace import get_current_span, get_tracer

from naraninyeo.api.agents.financial_summarizer import FinancialSummarizerDeps, financial_summarizer
from naraninyeo.api.agents.summary_extractor import SummaryExtractorDeps, summary_extractor
from naraninyeo.api.infrastructure.adapter.finance_search import FinanceSearchClient
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
        self.finance_search_client = FinanceSearchClient()

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
            case ActionType.SEARCH_FINANCIAL_DATA:
                if action.query is None:
                    raise ValueError("Query is required for financial data search")
                ticker = await self.finance_search_client.search_symbol(action.query)
                if ticker is None:
                    raise ValueError("Ticker not found for query: {}".format(action.query))
                price = asyncio.create_task(self.finance_search_client.search_current_price(ticker))
                short_term_price = asyncio.create_task(self.finance_search_client.get_short_term_price(ticker))
                long_term_price = asyncio.create_task(self.finance_search_client.get_long_term_price(ticker))
                news = asyncio.create_task(self.finance_search_client.search_news(ticker))
                await asyncio.gather(price, short_term_price, long_term_price, news, return_exceptions=True)

                if isinstance(price, Exception):
                    price = ""
                else:
                    price = price.result() or ""

                if isinstance(short_term_price, Exception):
                    short_term_price = ""
                else:
                    short_term_price = short_term_price.result()
                    short_term_price = "\n".join(f"{item.local_date}: {item.close_price}" for item in short_term_price)

                if isinstance(long_term_price, Exception):
                    long_term_price = ""
                else:
                    long_term_price = long_term_price.result()
                    long_term_price = "\n".join(f"{item.local_date}: {item.close_price}" for item in long_term_price)

                if isinstance(news, Exception):
                    news = ""
                else:
                    news = news.result()
                    news = "\n".join(f"[{item.source}, {item.timestamp}] {item.title}\n{item.body}" for item in news)
                financial_summarizer_deps = FinancialSummarizerDeps(
                    action=action,
                    price=price,
                    short_term_price=short_term_price,
                    long_term_price=long_term_price,
                    news=news,
                )
                financial_summarizer_result = await financial_summarizer.run_with_generator(financial_summarizer_deps)
                collector.add_result(
                    action=action,
                    result=PlanActionResult(
                        action_result_id=self.id_generator.generate_id(),
                        action=action,
                        status="COMPLETED",
                        content=financial_summarizer_result.output,
                        priority=5,
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
        tasks: list[asyncio.Task] = []
        try:
            for action in actions:
                task = asyncio.create_task(
                    self._execute_action(
                        tctx=tctx,
                        action=action,
                        channel_id=incoming_message.channel.channel_id,
                        collector=collector,
                    ),
                    name=f"{action.action_type.value}-{action.query}",
                )
                tasks.append(task)
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=20)
        except TimeoutError:
            logging.warning(f"Plan execution timeout after 20 seconds. {len(tasks)} tasks were running.")
        finally:
            for task in tasks:
                if task.done():
                    if task.cancelled():
                        logging.warning(f"Task cancelled: ({task.get_name()})")
                    elif (exc := task.exception()) is not None:
                        logging.warning(f"Task failed: ({task.get_name()}) {exc}")
        results = collector.get_results()
        return results
