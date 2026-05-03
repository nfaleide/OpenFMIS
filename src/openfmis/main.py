"""FastAPI application factory with lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from openfmis.api.router import api_router
from openfmis.config import settings
from openfmis.core.plugin_registry import register_builtin_plugins, register_external_plugins
from openfmis.database import engine, geodata_engine
from openfmis.middleware.compression import add_gzip_middleware
from openfmis.middleware.cors import add_cors_middleware
from openfmis.middleware.logging import RequestLoggingMiddleware
from openfmis.middleware.rate_limit import RateLimitMiddleware

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    await register_builtin_plugins()
    await register_external_plugins()
    yield
    await engine.dispose()
    await geodata_engine.dispose()


def create_app() -> FastAPI:
    """Application factory — called by uvicorn and tests."""
    app = FastAPI(
        title="OpenFMIS",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware stack (order matters — outermost first)
    add_gzip_middleware(app, minimum_size=1000)
    add_cors_middleware(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.RATE_LIMIT_RPM)
    app.include_router(api_router)

    # Serve dashboard at root
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        async def root_dashboard():
            return FileResponse(str(_STATIC_DIR / "index.html"))

    return app
