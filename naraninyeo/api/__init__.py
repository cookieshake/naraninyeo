"""FastAPI application factory."""

from __future__ import annotations

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from naraninyeo.api.routers.bot import bot_router
from naraninyeo.api.routers.message import message_router
from naraninyeo.core.container import container


def create_app() -> FastAPI:
    app = FastAPI(title="Naraninyeo API")

    app.include_router(bot_router, tags=["bots"])
    app.include_router(message_router, tags=["messages"])
    setup_dishka(container, app)

    return app

