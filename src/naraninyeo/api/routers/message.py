import asyncio
import logging
from typing import Optional

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from naraninyeo.api.graphs.manage_memory import ManageMemoryGraphContext, ManageMemoryGraphState, manage_memory_graph
from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState, new_message_graph
from naraninyeo.api.infrastructure.adapter.naver_search import NaverSearchClient
from naraninyeo.api.infrastructure.interfaces import (
    BotRepository,
    Clock,
    IdGenerator,
    MemoryRepository,
    MessageRepository,
    PlanActionExecutor,
)
from naraninyeo.core.models import BotMessage, Message, TenancyContext
from naraninyeo.core.settings import Settings

message_router = APIRouter()


class NewMessageRequest(BaseModel):
    bot_id: str
    message: Message
    reply_needed: bool = False


class NewMessageResponseChunk(BaseModel):
    is_final: bool
    error: str | None = None
    generated_message: BotMessage | None = None
    last_state: Optional[dict] = None


@message_router.post("/new_message")
@inject
async def new_message(
    new_message_request: NewMessageRequest,
    settings: FromDishka[Settings],
    message_repo: FromDishka[MessageRepository],
    memory_repo: FromDishka[MemoryRepository],
    bot_repo: FromDishka[BotRepository],
    clock: FromDishka[Clock],
    id_generator: FromDishka[IdGenerator],
    plan_executor: FromDishka[PlanActionExecutor],
):
    tctx = TenancyContext(tenant_id="default")
    bot = await bot_repo.get(tctx, new_message_request.bot_id)
    if not bot:
        return Response(
            status_code=400,
            content=NewMessageResponseChunk(
                is_final=True, error=f"Bot with ID {new_message_request.bot_id} not found."
            ).model_dump_json(),
            media_type="application/ld+json",
        )
    await message_repo.upsert(tctx, new_message_request.message)
    async with asyncio.TaskGroup() as tg:
        latest_update_ts = tg.create_task(
            memory_repo.get_latest_memory_update_ts(
                tctx,
                bot_id=new_message_request.bot_id,
                channel_id=new_message_request.message.channel.channel_id,
            )
        )
        latest_messages = tg.create_task(
            message_repo.get_channel_messages_before(
                tctx,
                channel_id=new_message_request.message.channel.channel_id,
                before_message_id=new_message_request.message.message_id,
                limit=30,
            )
        )
    latest_update_ts = await latest_update_ts
    latest_messages = await latest_messages
    oldest_message_ts_in_history = latest_messages[0].timestamp if latest_messages else None

    if (not latest_update_ts) or (oldest_message_ts_in_history and oldest_message_ts_in_history > latest_update_ts):
        logging.info(
            "Oldest message in history (%s) is newer than latest update (%s)",
            oldest_message_ts_in_history,
            latest_update_ts,
        )
        init_state = ManageMemoryGraphState(
            current_tctx=tctx,
            current_bot=bot,
            status="processing",
            incoming_message=new_message_request.message,
            latest_history=list(latest_messages),
        )
        graph_context = ManageMemoryGraphContext(
            clock=clock,
            id_generator=id_generator,
            memory_repository=memory_repo,
        )
        asyncio.create_task(manage_memory_graph.ainvoke(init_state, context=graph_context))
    else:
        logging.info(
            "No need to update memory. Latest memory update ts: %s, Oldest message ts in history: %s",
            latest_update_ts,
            oldest_message_ts_in_history,
        )

    if new_message_request.reply_needed:
        channel_memory = await memory_repo.get_channel_memory_items(
            tctx,
            bot_id=new_message_request.bot_id,
            channel_id=new_message_request.message.channel.channel_id,
            limit=100,
        )

        init_state = NewMessageGraphState(
            current_tctx=tctx,
            current_bot=bot,
            status="processing",
            incoming_message=new_message_request.message,
            latest_history=list(latest_messages),
            memories=list(channel_memory),
        )
        graph_context = NewMessageGraphContext(
            clock=clock,
            message_repository=message_repo,
            memory_repository=memory_repo,
            plan_action_executor=plan_executor,
            naver_search_client=NaverSearchClient(settings),
        )

        async def message_stream_generator():
            current_state = init_state.model_copy()
            async for state in new_message_graph.astream(init_state, context=graph_context, stream_mode="updates"):
                state = state.popitem()[1]
                if not state:
                    continue
                for key, value in state.items():
                    current_state.__setattr__(key, value)
                if "outgoing_messages" in state and state["outgoing_messages"] is not None:
                    generated_message = state["outgoing_messages"]
                    for msg in generated_message:
                        yield (
                            NewMessageResponseChunk(
                                is_final=False, generated_message=msg, last_state=current_state.model_dump()
                            ).model_dump_json()
                            + "\n"
                        )
            yield NewMessageResponseChunk(is_final=True).model_dump_json()

        return StreamingResponse(content=message_stream_generator(), media_type="application/ld+json")
    else:
        return NewMessageResponseChunk(is_final=True)
