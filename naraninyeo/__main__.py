import asyncio
import logging
import os

from naraninyeo.api import create_app


async def main() -> None:
    entrypoint = os.environ.get("NRIY_ENTRYPOINT", "api")
    if entrypoint == "api":
        app = create_app()
        import uvicorn
        uvicorn_config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
            log_level=os.environ.get("LOG_LEVEL", "info"),
            access_log=True
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()

if __name__ == "__main__":
    asyncio.run(main())
