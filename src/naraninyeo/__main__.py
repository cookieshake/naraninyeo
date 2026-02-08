import asyncio
import os

from dishka.integrations.fastapi import setup_dishka
from dotenv import load_dotenv

from naraninyeo.api import create_app
from naraninyeo.api.container import container
from naraninyeo.infrastructure.util.opentelemetry import (
    OpenTelemetryInstrumentation,
    OpenTelemetryLog,
    OpenTelemetryMetrics,
    OpenTelemetryTracer,
)
from naraninyeo.router import get_router


async def main() -> None:
    load_dotenv()
    OpenTelemetryLog().configure()
    OpenTelemetryTracer().configure()
    OpenTelemetryMetrics().configure()
    OpenTelemetryInstrumentation().configure()

    entrypoint = os.environ.get("NRIY_ENTRYPOINT", "api")
    if entrypoint == "api":
        app = create_app()
        setup_dishka(container, app)
        import uvicorn

        uvicorn_config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
            log_level=os.environ.get("LOG_LEVEL", "info"),
            access_log=True,
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()
    elif entrypoint == "router":
        router = await get_router()
        await router.run()
    else:
        raise ValueError(f"Unknown entrypoint: {entrypoint}")


if __name__ == "__main__":
    asyncio.run(main())
