from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from pydantic import BaseModel

from naraninyeo.api.infrastructure.interfaces import BotRepository, Clock, IdGenerator
from naraninyeo.core.models import Bot, TenancyContext

bot_router = APIRouter()


@bot_router.get("/bots")
@inject
async def list_bots(bot_repo: FromDishka[BotRepository]):
    tctx = TenancyContext(tenant_id="default")
    return await bot_repo.list_all(tctx)


class CreateBotRequest(BaseModel):
    name: str
    author_id: str


@bot_router.post("/bots")
@inject
async def create_bot(
    request: CreateBotRequest,
    bot_repo: FromDishka[BotRepository],
    clock: FromDishka[Clock],
    id_generator: FromDishka[IdGenerator],
) -> Bot:
    tctx = TenancyContext(tenant_id="default")
    bot = Bot(
        bot_id=id_generator.generate_id(), bot_name=request.name, author_id=request.author_id, created_at=clock.now()
    )
    await bot_repo.create(tctx, bot)
    return bot
