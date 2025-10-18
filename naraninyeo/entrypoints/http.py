import os
from typing import Annotated

import httpx
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from naraninyeo.app.reply import NewMessageHandler
from naraninyeo.assistant.models import Message
from naraninyeo.container import container
from naraninyeo.settings import Settings

app = FastAPI()


class APIClient:
    def __init__(self, settings: Settings):
        self.api_url = settings.NARANINYEO_API_URL

    async def send_response(self, message: Message):
        # 내부에서 생성한 봇 응답을 본 서비스 API로 전달한다.
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


async def get_settings() -> Settings:
    return await container.get(Settings)


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
            # 파이프라인이 내놓는 응답을 JSON 문자열로 스트리밍한다.
            yield reply.model_dump_json()

    return StreamingResponse(make_reply(), media_type="application/ld+json")


def main():
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    return {
        "status": "ok",
        "models": {
            "reply": settings.REPLY_MODEL_NAME,
            "planner": settings.PLANNER_MODEL_NAME,
            "memory": settings.MEMORY_MODEL_NAME,
            "extractor": settings.EXTRACTOR_MODEL_NAME,
        },
        "retrieval": {
            "max_concurrency": settings.RETRIEVAL_MAX_CONCURRENCY,
            "max_references": settings.MAX_KNOWLEDGE_REFERENCES,
        },
    }
