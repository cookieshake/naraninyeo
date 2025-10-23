"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from naraninyeo.api.router import RouterDependencies, build_router


def create_app(deps: RouterDependencies) -> FastAPI:
    """Create a FastAPI application wired with the provided dependencies."""
    app = FastAPI(title="NaraninYeo Assistant API")
    app.include_router(build_router(deps))
    return app


__all__ = ["create_app", "RouterDependencies"]
