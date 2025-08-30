from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI

from naraninyeo.di import container
from naraninyeo.domain.application.new_message_handler import NewMessageHandler
from naraninyeo.domain.model.message import Message
from naraninyeo.entrypoints.kafka import APIClient
from naraninyeo.infrastructure.settings import Settings

app = FastAPI()


async def get_message_handler() -> NewMessageHandler:
    return await container.get(NewMessageHandler)


async def get_api_client() -> APIClient:
    settings = await container.get(Settings)
    return APIClient(settings)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/handle_new_message")
async def handle_new_message(
    new_message: Message,
    message_handler: Annotated[NewMessageHandler, Depends(get_message_handler)],
    api_client: Annotated[APIClient, Depends(get_api_client)],
):
    async for reply in message_handler.handle(new_message):
        await api_client.send_response(reply)


async def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)
