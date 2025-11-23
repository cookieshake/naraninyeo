"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from naraninyeo.api.routers.bot import bot_router
from naraninyeo.api.routers.core import core_router
from naraninyeo.api.routers.message import message_router


def create_app() -> FastAPI:
    app = FastAPI(title="Naraninyeo API")

    app.include_router(bot_router, tags=["bots"])
    app.include_router(core_router, tags=["core"])
    app.include_router(message_router, tags=["messages"])
    FastAPIInstrumentor.instrument_app(app)

    return app
