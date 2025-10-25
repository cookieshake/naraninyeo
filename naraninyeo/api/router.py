"""API router wiring handlers to HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from naraninyeo.api.handlers.frontend_handler import FrontendHandler
from naraninyeo.api.handlers.message_handler import BotResolver as MessageBotResolver
from naraninyeo.api.handlers.message_handler import MessageHandler, MessageProcessingFlow
from naraninyeo.api.handlers.reply_handler import BotResolver as ReplyBotResolver
from naraninyeo.api.handlers.reply_handler import ReplyGenerationFlow, ReplyHandler
from naraninyeo.api.interfaces import (
    MemoryRepository,
    MemoryStrategy,
    MessageRepository,
    OutboundDispatcher,
    ReplyGenerator,
    WebSearchClient,
)
from naraninyeo.api.models import FlowResponse, IncomingMessageRequest, ReplyRequest
from naraninyeo.api.tasks.generate_reply import GenerateReplyTask
from naraninyeo.api.tasks.get_history import GetHistoryTask
from naraninyeo.api.tasks.manage_memory import ManageMemoryTask
from naraninyeo.api.tasks.messages_to_memory import MessagesToMemoryTask
from naraninyeo.api.tasks.retrieve_memory import RetrieveMemoryTask
from naraninyeo.api.tasks.save_memory import SaveMemoryTask
from naraninyeo.api.tasks.search_history import SearchHistoryTask
from naraninyeo.api.tasks.search_web import SearchWebTask
from naraninyeo.api.tasks.store_message import StoreMessageTask


@dataclass(slots=True)
class RouterDependencies:
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    memory_strategy: MemoryStrategy
    web_client: WebSearchClient
    reply_generator: ReplyGenerator
    dispatcher: OutboundDispatcher | None = None
    message_bot_resolver: MessageBotResolver | None = None
    reply_bot_resolver: ReplyBotResolver | None = None


def build_message_flow(deps: RouterDependencies) -> MessageProcessingFlow:
    store_message = StoreMessageTask(deps.message_repository)
    get_history = GetHistoryTask(deps.message_repository)
    search_history = SearchHistoryTask(deps.message_repository)
    to_memory = MessagesToMemoryTask()
    save_memory = SaveMemoryTask(deps.memory_repository)
    manage_memory = ManageMemoryTask(deps.memory_repository, deps.memory_strategy)
    retrieve_memory = RetrieveMemoryTask(deps.memory_repository)
    web_search = SearchWebTask(deps.web_client)
    generate_reply = GenerateReplyTask(deps.reply_generator, deps.dispatcher)

    tasks = (
        store_message,
        get_history,
        search_history,
        to_memory,
        save_memory,
        manage_memory,
        retrieve_memory,
        web_search,
        generate_reply,
    )
    return MessageProcessingFlow(tasks)


def build_reply_flow(deps: RouterDependencies) -> ReplyGenerationFlow:
    get_history = GetHistoryTask(deps.message_repository)
    search_history = SearchHistoryTask(deps.message_repository)
    retrieve_memory = RetrieveMemoryTask(deps.memory_repository)
    web_search = SearchWebTask(deps.web_client)
    generate_reply = GenerateReplyTask(deps.reply_generator, deps.dispatcher)

    tasks = (
        get_history,
        search_history,
        retrieve_memory,
        web_search,
        generate_reply,
    )
    return ReplyGenerationFlow(tasks)


def build_router(deps: RouterDependencies) -> APIRouter:
    message_flow = build_message_flow(deps)
    reply_flow = build_reply_flow(deps)

    message_handler = MessageHandler(message_flow, resolve_bot=deps.message_bot_resolver)
    reply_handler = ReplyHandler(reply_flow, deps.message_repository, resolve_bot=deps.reply_bot_resolver)
    frontend_handler = FrontendHandler()

    router = APIRouter(prefix="/api")

    @router.post("/messages", response_model=FlowResponse)
    async def post_message(payload: IncomingMessageRequest) -> FlowResponse:
        try:
            return await message_handler.handle(payload)
        except Exception as exc:  # pragma: no cover - surfaced as HTTP error
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/replies", response_model=FlowResponse)
    async def post_reply(payload: ReplyRequest) -> FlowResponse:
        try:
            return await reply_handler.handle(payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/", response_class=HTMLResponse)
    async def frontend() -> HTMLResponse:
        return await frontend_handler.handle()

    return router
