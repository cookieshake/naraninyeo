"""Command line entrypoint for the NaraninYeo assistant."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
from typing import Any

from naraninyeo.api import RouterDependencies, create_app
from naraninyeo.router.router import KafkaMessageRouter

logger = logging.getLogger(__name__)


def _load_module(path: str):
    try:
        return importlib.import_module(path)
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(f"failed to import module '{path}'") from exc


def _load_router_dependencies(module: Any) -> RouterDependencies:
    if not hasattr(module, "build_router_dependencies"):
        raise RuntimeError("dependencies module must expose 'build_router_dependencies'")
    deps = module.build_router_dependencies()
    if not isinstance(deps, RouterDependencies):
        raise RuntimeError("build_router_dependencies must return RouterDependencies")
    return deps


def _load_kafka_router(module: Any) -> KafkaMessageRouter:
    if not hasattr(module, "create_kafka_router"):
        raise RuntimeError("dependencies module must expose 'create_kafka_router'")
    router = module.create_kafka_router()
    if not isinstance(router, KafkaMessageRouter):
        raise RuntimeError("create_kafka_router must return KafkaMessageRouter")
    return router


def run_api(deps_module: str, *, host: str, port: int, reload: bool) -> None:
    router_module = _load_module(deps_module)
    deps = _load_router_dependencies(router_module)
    app = create_app(deps)
    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is required to run the API") from exc
    uvicorn.run(app, host=host, port=port, reload=reload)


async def run_router(deps_module: str) -> None:
    router_module = _load_module(deps_module)
    kafka_router = _load_kafka_router(router_module)
    await kafka_router.start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="naraninyeo")
    sub = parser.add_subparsers(dest="command", required=True)

    api_parser = sub.add_parser("api", help="Run the FastAPI application")
    api_parser.add_argument("--deps", dest="deps", required=True, help="Module path providing router dependencies")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8080)
    api_parser.add_argument("--reload", action="store_true")

    router_parser = sub.add_parser("router", help="Run the Kafka message router")
    router_parser.add_argument("--deps", dest="deps", required=True, help="Module path providing router dependencies")

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    if args.command == "api":
        run_api(args.deps, host=args.host, port=args.port, reload=args.reload)
    elif args.command == "router":
        asyncio.run(run_router(args.deps))
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    main()
