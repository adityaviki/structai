from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import events as agent_events
from .api.dev import router as dev_router
from .api.documents import router as documents_router
from .api.errors import ApiError, api_error_handler
from .api.healthz import router as healthz_router
from .api.projects import router as projects_router
from .api.runs import router as runs_router
from .api.schema import router as schema_router
from .api.settings import project_router as project_settings_router
from .api.settings import router as settings_router
from .api.snapshots import router as snapshots_router
from .api.tables import router as tables_router
from .db.health import StartupCheckError
from .db.health import run_all as run_startup_checks
from .db.pools import get_pools, init_pools
from .logging import configure_logging, log
from .settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        await run_startup_checks(settings)
    except StartupCheckError as exc:
        log.error("startup.failed", error=str(exc))
        # Fail loud and exit non-zero so the user sees the problem.
        print(f"\nstructai: startup check failed.\n\n{exc}\n", file=sys.stderr)
        raise SystemExit(1) from exc
    if settings.anthropic_api_key is None:
        log.warning("startup.anthropic_key_missing")

    init_pools(settings)
    try:
        yield
    finally:
        await get_pools().close()
        await agent_events.close()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="StructAI",
        version="0.0.1",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]

    app.include_router(healthz_router, prefix="/api")
    app.include_router(dev_router, prefix="/api")
    app.include_router(projects_router)
    app.include_router(documents_router)
    app.include_router(runs_router)
    app.include_router(tables_router)
    app.include_router(schema_router)
    app.include_router(settings_router)
    app.include_router(project_settings_router)
    app.include_router(snapshots_router)
    return app


app = create_app()
