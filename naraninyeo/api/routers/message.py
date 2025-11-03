import asyncio
from typing import Optional

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from naraninyeo.api.graphs.manage_memory import ManageMemoryGraphContext, ManageMemoryGraphState, manage_memory_graph
from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState, new_message_graph
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
    await message_repo.upsert(tctx, new_message_request.message)

    if not new_message_request.reply_needed:
        if new_message_request.message.author.author_id == new_message_request.bot_id:
            bot = await bot_repo.get(tctx, new_message_request.bot_id)
            if bot:
                init_state = ManageMemoryGraphState(
                    current_tctx=tctx,
                    current_bot=bot,
                    status="processing",
                    incoming_message=new_message_request.message,
                )
                graph_context = ManageMemoryGraphContext(
                    clock=clock,
                    id_generator=id_generator,
                    memory_repository=memory_repo,
                )
                asyncio.create_task(manage_memory_graph.ainvoke(init_state, context=graph_context))

        return Response(
            status_code=200,
            content=NewMessageResponseChunk(is_final=True).model_dump_json(),
            media_type="application/ld+json",
        )

    async with asyncio.TaskGroup() as tg:
        latest_message_task = tg.create_task(
            message_repo.get_channel_messages_before(
                tctx,
                channel_id=new_message_request.message.channel.channel_id,
                before_message_id=new_message_request.message.message_id,
                limit=20,
            )
        )
        channel_memory_task = tg.create_task(
            memory_repo.get_channel_memory_items(
                tctx,
                bot_id=new_message_request.bot_id,
                channel_id=new_message_request.message.channel.channel_id,
                limit=100,
            )
        )
        bot_task = tg.create_task(bot_repo.get(tctx, new_message_request.bot_id))
    latest_message = await latest_message_task
    channel_memory = await channel_memory_task
    bot = await bot_task
    if not bot:
        return Response(
            status_code=400,
            content=NewMessageResponseChunk(
                is_final=True, error=f"Bot with ID {new_message_request.bot_id} not found."
            ).model_dump_json(),
            media_type="application/ld+json",
        )

    init_state = NewMessageGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=new_message_request.message,
        latest_history=list(latest_message),
        memories=list(channel_memory),
    )
    graph_context = NewMessageGraphContext(
        clock=clock,
        message_repository=message_repo,
        memory_repository=memory_repo,
        plan_action_executor=plan_executor,
    )

    async def message_stream_generator():
        message_sent = 0
        async for chunk in new_message_graph.astream(init_state, context=graph_context):
            states = chunk.values()
            for state in states:
                if "outgoing_messages" in state:
                    generated_message = state["outgoing_messages"][message_sent:]
                    message_sent += len(generated_message)
                    for msg in generated_message:
                        yield (
                            NewMessageResponseChunk(
                                is_final=False, generated_message=msg, last_state=state
                            ).model_dump_json()
                            + "\n"
                        )
        yield NewMessageResponseChunk(is_final=True).model_dump_json()

    return StreamingResponse(content=message_stream_generator(), media_type="application/ld+json")
