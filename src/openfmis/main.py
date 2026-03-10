"""FastAPI application factory with lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from openfmis.api.router import api_router
from openfmis.core.plugin_registry import register_builtin_plugins
from openfmis.database import engine
from openfmis.middleware.cors import add_cors_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    await register_builtin_plugins()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory — called by uvicorn and tests."""
    app = FastAPI(
        title="OpenFMIS",
        version="0.1.0",
        lifespan=lifespan,
    )

    add_cors_middleware(app)
    app.include_router(api_router)

    return app
