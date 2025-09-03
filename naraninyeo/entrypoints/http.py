import os
from typing import Annotated

import httpx
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from naraninyeo.di import container
from naraninyeo.domain.application.new_message_handler import NewMessageHandler
from naraninyeo.domain.model.message import Message
from naraninyeo.infrastructure.settings import Settings

app = FastAPI()


class APIClient:
    def __init__(self, settings: Settings):
        self.api_url = settings.NARANINYEO_API_URL

    async def send_response(self, message: Message):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/reply",
                json={
                    "type": "text",
                    "room": message.channel.channel_id,
                    "data": message.content.text,
                },
            )
            response.raise_for_status()


async def get_message_handler() -> NewMessageHandler:
    return await container.get(NewMessageHandler)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.post("/handle_new_message")
async def handle_new_message(
    new_message: Message,
    message_handler: Annotated[NewMessageHandler, Depends(get_message_handler)],
):
    async def make_reply():
        is_first = True
        async for reply in message_handler.handle(new_message):
            if not is_first:
                yield "\n"
            else:
                is_first = False
            yield reply.model_dump_json()
    return StreamingResponse(make_reply(), media_type="application/ld+json")


def main():
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
