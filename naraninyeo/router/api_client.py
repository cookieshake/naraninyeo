from typing import AsyncGenerator

import httpx

from naraninyeo.api.routers.message import NewMessageRequest, NewMessageResponseChunk
from naraninyeo.core.models import BotMessage, Message


class APIClient:
    def __init__(
        self,
        api_url: str,
        bot_id: str,
    ) -> None:
        self.api_url = api_url
        self.bot_id = bot_id
        self.client = httpx.AsyncClient(
            base_url=api_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=180.0,
                write=180.0,
                pool=10.0,
            ),
        )

    async def new_message(
        self,
        message: Message,
        reply_needed: bool = False,
    ) -> AsyncGenerator[BotMessage]:
        req = NewMessageRequest(
            bot_id=self.bot_id,
            message=message,
            reply_needed=reply_needed,
        )
        async with self.client.stream(
            "POST",
            "/new_message",
            json=req.model_dump(),
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_lines():
                chunk = NewMessageResponseChunk.model_validate_json(chunk)
                if chunk.generated_message:
                    yield chunk.generated_message
