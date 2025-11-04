import httpx


class PhoneClient:
    def __init__(self, api_url: str):
        self.client = httpx.AsyncClient(
            base_url=api_url,
        )

    async def reply(
        self,
        channel_id: str,
        message: str,
    ):
        response = await self.client.post(
            "/reply",
            json={
                "type": "text",
                "room": channel_id,
                "data": message,
            },
        )
        response.raise_for_status()
