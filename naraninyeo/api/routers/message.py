
from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from naraninyeo.api.infrastructure.interfaces import MessageRepository
from naraninyeo.core.models import Message, TenancyContext
from naraninyeo.api.graphs.new_message import new_message_graph, NewMessageGraphState, NewMessageGraphContext

message_router = APIRouter()

class NewMessageRequest(BaseModel):
    message: Message
    reply_needed: bool = False

@message_router.post("/new_message")
async def new_message(
    new_message_request: NewMessageRequest,
    tctx: FromDishka[TenancyContext],
    message_repo: FromDishka[MessageRepository]
):
    await message_repo.upsert(tctx, new_message_request.message)
    if not new_message_request.reply_needed:
        return {"status": "message stored"}

    latest_message = message_repo.get_channel_messages_before(
        tctx,
        channel_id=new_message_request.message.channel.channel_id,
        before_message_id=new_message_request.message.message_id,
        limit=1
    )

    
