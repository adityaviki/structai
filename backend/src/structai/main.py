from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent import events as agent_events
from .api.auth import router as auth_router
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
from .auth import COOKIE_NAME, verify_token
from .db.health import StartupCheckError
from .db.health import run_all as run_startup_checks
from .db.pools import get_pools, init_pools
from .logging import configure_logging, log
from .settings import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# /api/* paths reachable without a session. Everything else under /api/ is
# gated once a password is configured.
_PUBLIC_API_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/healthz",
        "/api/docs",
        "/api/openapi.json",
    }
)


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


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "type": "about:blank",
            "title": "Not authenticated",
            "status": 401,
            "detail": "Sign in to continue.",
            "instance": "/api",
        },
        media_type="application/problem+json",
    )


def _install_auth_guard(app: FastAPI, settings: Settings) -> None:
    """Gate every /api/* route behind a valid session cookie.

    A no-op while ``auth_enabled`` is False, so unconfigured/dev/test setups
    are unaffected. Auth config is env-only and fixed for the process lifetime,
    so we close over ``settings`` rather than re-reading it per request.
    """

    @app.middleware("http")
    async def auth_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if (
            not settings.auth_enabled
            or request.method == "OPTIONS"  # let CORS answer preflight
            or not path.startswith("/api/")
            or path in _PUBLIC_API_PATHS
        ):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if token and verify_token(settings, token):
            return await call_next(request)
        return _unauthorized()


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

    _install_auth_guard(app, settings)

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
    app.include_router(auth_router)
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
