import asyncio
import logging

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from naraninyeo.core.interfaces import (
    BotRepository,
    Clock,
    FinanceSearch,
    IdGenerator,
    MemoryRepository,
    MessageRepository,
    NaverSearch,
    TextEmbedder,
    WebDocumentFetch,
)
from naraninyeo.core.models import (
    BotMessage,
    MessageContent,
    NewMessageRequest,
    NewMessageResponseChunk,
    TenancyContext,
)
from naraninyeo.core.settings import Settings
from naraninyeo.graphs.manage_memory import (
    ManageMemoryGraphContext,
    ManageMemoryGraphState,
    manage_memory_graph,
)
from naraninyeo.graphs.new_message import NewMessageGraphContext, NewMessageGraphState, new_message_graph

message_router = APIRouter()


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
    naver_search: FromDishka[NaverSearch],
    finance_search: FromDishka[FinanceSearch],
    web_document_fetch: FromDishka[WebDocumentFetch],
    text_embedder: FromDishka[TextEmbedder],
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
        mem_state = ManageMemoryGraphState(
            current_tctx=tctx,
            current_bot=bot,
            status="processing",
            incoming_message=new_message_request.message,
            latest_history=list(latest_messages),
        )
        mem_context = ManageMemoryGraphContext(
            clock=clock,
            id_generator=id_generator,
            memory_repository=memory_repo,
        )

        async def _run_manage_memory(s: ManageMemoryGraphState, c: ManageMemoryGraphContext) -> None:
            try:
                await manage_memory_graph.ainvoke(s, context=c)
            except Exception:
                logging.exception("manage_memory_graph failed")

        asyncio.create_task(_run_manage_memory(mem_state, mem_context))
    else:
        logging.info(
            "No need to update memory. Latest memory update ts: %s, Oldest message ts in history: %s",
            latest_update_ts,
            oldest_message_ts_in_history,
        )

    if new_message_request.reply_needed:
        query_emb = await text_embedder.embed_queries([new_message_request.message.content.text])
        channel_memory = await memory_repo.search_memories(
            tctx,
            bot_id=new_message_request.bot_id,
            channel_id=new_message_request.message.channel.channel_id,
            query_embedding=query_emb[0],
            limit=20,
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
            naver_search_client=naver_search,
            finance_search_client=finance_search,
            web_document_fetcher=web_document_fetch,
        )

        async def message_stream_generator():
            current_state: dict = init_state.model_dump()
            async for tpl in new_message_graph.astream(  # pyright: ignore[reportAssignmentType]
                init_state, context=graph_context, stream_mode=["values", "custom"]
            ):
                tpl: tuple[str, dict] = tpl
                mode, state = tpl
                if mode == "values":
                    current_state = state  # pyright: ignore[reportAssignmentType]
                elif mode == "custom":
                    if state.get("type") == "response":
                        text: str = state.get("text", "")
                        yield (
                            NewMessageResponseChunk(
                                is_final=False,
                                generated_message=BotMessage(
                                    bot=bot,
                                    channel=new_message_request.message.channel,
                                    content=MessageContent(text=text),
                                ),
                                last_state=current_state,
                            ).model_dump_json()
                            + "\n"
                        )
            yield NewMessageResponseChunk(is_final=True).model_dump_json()

        return StreamingResponse(content=message_stream_generator(), media_type="application/ld+json")
    else:
        return NewMessageResponseChunk(is_final=True)
