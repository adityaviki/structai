from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from structai.api.healthz import router as healthz_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(healthz_router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
