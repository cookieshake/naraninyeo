import asyncio
from datetime import datetime
from typing import Literal
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from naraninyeo.api.infrastructure.interfaces import BotRepository, Clock, IdGenerator, MemoryRepository, MessageRepository
from naraninyeo.core.models import Bot, Message, TenancyContext, BotMessage
from naraninyeo.api.graphs.manage_memory import manage_memory_graph, ManageMemoryGraphState, ManageMemoryGraphContext
from naraninyeo.api.graphs.new_message import new_message_graph, NewMessageGraphState, NewMessageGraphContext

message_router = APIRouter()

class NewMessageRequest(BaseModel):
    bot_id: str
    message: Message
    reply_needed: bool = False

class NewMessageResponseChunk(BaseModel):
    is_final: bool
    error: str | None = None
    generated_message: BotMessage | None = None

@message_router.post("/new_message")
@inject
async def new_message(
    new_message_request: NewMessageRequest,
    message_repo: FromDishka[MessageRepository],
    memory_repo: FromDishka[MemoryRepository],
    bot_repo: FromDishka[BotRepository],
    clock: FromDishka[Clock],
    id_generator: FromDishka[IdGenerator],
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
                asyncio.create_task(
                    manage_memory_graph.ainvoke(init_state, context=graph_context)
                )

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
                limit=1
            )
        )
        channel_memory_task = tg.create_task(
            memory_repo.get_channel_memory_items(
                tctx,
                bot_id=new_message_request.bot_id,
                channel_id=new_message_request.message.channel.channel_id,
                limit=100
            )
        )
        bot_task = tg.create_task(
            bot_repo.get(tctx, new_message_request.bot_id)
        )
    latest_message = await latest_message_task
    channel_memory = await channel_memory_task
    bot = await bot_task
    if not bot:
        return Response(
            status_code=400,
            content=NewMessageResponseChunk(
                is_final=True,
                error=f"Bot with ID {new_message_request.bot_id} not found."
            ).model_dump_json(),
            media_type="application/ld+json",
        )

    init_state = NewMessageGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=new_message_request.message,
        latest_history=list(latest_message),
        memories=list(channel_memory)
    )
            
    async def message_stream_generator():
        async for chunk in new_message_graph.astream(init_state):
            updates = chunk.values()
            for state_update in updates:
                if "outgoing_messages" in state_update:
                    generated_message = state_update.outgoing_messages[-1]
                    yield NewMessageResponseChunk(
                        is_final=False,
                        generated_message=generated_message
                    ).model_dump_json() + "\n"
        yield NewMessageResponseChunk(is_final=True).model_dump_json() + "\n"

    return StreamingResponse(
        content=message_stream_generator(),
        media_type="application/ld+json"
    )
