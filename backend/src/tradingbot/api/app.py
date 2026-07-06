"""FastAPI application factory — the composition root of the API process.

Run locally (from backend/):

    uv run uvicorn tradingbot.api.app:app --reload

The engine only connects on the first query, so importing this module never
touches the database.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingbot.api.deps import (
    get_ohlcv_dir,
    get_paper_symbol,
    get_repositories,
    get_walkforward_dir,
)
from tradingbot.api.features.backtests.routes import router as backtests_router
from tradingbot.api.features.live.routes import router as live_router
from tradingbot.api.features.models.routes import router as models_router
from tradingbot.api.features.strategies.routes import router as strategies_router
from tradingbot.api.features.walkforward.routes import router as walkforward_router
from tradingbot.application.persistence import Repositories, build_postgres_repositories
from tradingbot.config.settings import Settings


def _health() -> dict[str, str]:
    return {"status": "ok"}


def create_app(
    repositories: Repositories | None = None, settings: Settings | None = None
) -> FastAPI:
    """Build the API. Tests pass in-memory fakes for `repositories`."""
    resolved = settings if settings is not None else Settings()
    repos = (
        repositories
        if repositories is not None
        else build_postgres_repositories(resolved.database_url)
    )

    app = FastAPI(title="tradingbot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        # Vite picks the next port when 5173 is busy — any localhost port is
        # as trusted as 5173, so accept them all.
        allow_origin_regex=r"http://localhost:\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.dependency_overrides[get_repositories] = lambda: repos
    app.dependency_overrides[get_walkforward_dir] = lambda: resolved.walkforward_dir
    app.dependency_overrides[get_ohlcv_dir] = lambda: resolved.ohlcv_dir
    app.dependency_overrides[get_paper_symbol] = lambda: resolved.paper_symbol

    app.add_api_route("/health", _health, methods=["GET"], tags=["health"])
    app.include_router(backtests_router)
    app.include_router(models_router)
    app.include_router(strategies_router)
    app.include_router(live_router)
    app.include_router(walkforward_router)
    return app


app = create_app()
