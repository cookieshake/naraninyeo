
from fastapi import APIRouter


bot_router = APIRouter()

@bot_router.get("/bots/{bot_id}")
async def get_bot(bot_id: str)