from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from structai.main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from _pytest.monkeypatch import MonkeyPatch

USERNAME = "admin"
PASSWORD = "s3cret-pw"


@pytest.fixture
async def auth_client(monkeypatch: MonkeyPatch) -> AsyncIterator[AsyncClient]:
    """A client against an app with auth turned on (password configured)."""

    monkeypatch.setenv("STRUCTAI_AUTH_USERNAME", USERNAME)
    monkeypatch.setenv("STRUCTAI_AUTH_PASSWORD", PASSWORD)
    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),  # type: ignore[attr-defined]
        AsyncClient(transport=transport, base_url="http://test") as c,
    ):
        yield c


@pytest.mark.asyncio
async def test_protected_route_requires_login(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/projects")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_healthz_stays_open(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/healthz")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_me_reports_required_when_logged_out(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body == {"authenticated": False, "auth_required": True, "username": None}


@pytest.mark.asyncio
async def test_login_bad_password_rejected(auth_client: AsyncClient) -> None:
    r = await auth_client.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrong"}
    )
    assert r.status_code == 401
    # No session cookie handed out on failure.
    assert "structai_session" not in auth_client.cookies


@pytest.mark.asyncio
async def test_login_grants_access_then_logout_revokes(auth_client: AsyncClient) -> None:
    # Logged out: blocked.
    assert (await auth_client.get("/api/projects")).status_code == 401

    # Log in.
    ok = await auth_client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["username"] == USERNAME
    assert "structai_session" in auth_client.cookies

    # Cookie now unlocks protected routes and identifies the user.
    assert (await auth_client.get("/api/projects")).status_code == 200
    me = await auth_client.get("/api/auth/me")
    assert me.json() == {"authenticated": True, "auth_required": True, "username": USERNAME}

    # Logout clears the cookie and re-locks the API.
    out = await auth_client.post("/api/auth/logout")
    assert out.status_code == 200
    assert (await auth_client.get("/api/projects")).status_code == 401


@pytest.mark.asyncio
async def test_disabled_auth_leaves_api_open(client: AsyncClient) -> None:
    """With no password configured (the default fixture), nothing is gated."""

    assert (await client.get("/api/projects")).status_code == 200
    me = await client.get("/api/auth/me")
    assert me.json() == {"authenticated": True, "auth_required": False, "username": None}
