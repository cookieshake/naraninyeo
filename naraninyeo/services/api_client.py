import httpx

from naraninyeo.core.config import settings
from naraninyeo.models.message import Message

async def send_response(response: Message):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.NARANINYEO_API_URL}/reply",
            json={
                "type": "text",
                "room": response.channel.channel_id,
                "data": response.content.text
            }
        )
        response.raise_for_status()