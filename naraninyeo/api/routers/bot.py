
from fastapi import APIRouter


bot_router = APIRouter()

@bot_router.get("/bots")
async def list_bots():
    return [{"bot_id": "bot1"}, {"bot_id": "bot2"}]

@bot_router.post("/bots")
async def create_bot(bot_data: dict):
    return {"bot_id": "new_bot_id", "data": bot_data}