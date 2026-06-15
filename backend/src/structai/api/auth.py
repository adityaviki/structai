"""Authentication endpoints: login / logout / session probe.

There is no registration endpoint by design — accounts cannot be created
through the API. Credentials come from configuration (see ``structai.auth``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..auth import COOKIE_NAME, issue_token, verify_password, verify_token
from ..settings import get_settings
from .errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class SessionOut(BaseModel):
    authenticated: bool
    # False when no password is configured: the client should skip the login
    # gate entirely rather than show a form it can never satisfy.
    auth_required: bool
    username: str | None = None


def _is_secure(request: Request) -> bool:
    """Whether the original request reached us over HTTPS (incl. via a proxy)."""

    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


@router.post("/login", response_model=SessionOut)
async def login(body: LoginIn, request: Request, response: Response) -> SessionOut:
    settings = get_settings()
    if not settings.auth_enabled:
        raise ApiError(
            status=400,
            title="Auth disabled",
            detail="Authentication is not configured on this server.",
        )
    if not verify_password(settings, body.username, body.password):
        raise ApiError(
            status=401,
            title="Invalid credentials",
            detail="The username or password is incorrect.",
        )
    token = issue_token(settings, body.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.auth_session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
        path="/",
    )
    return SessionOut(authenticated=True, auth_required=True, username=body.username)


@router.post("/logout", response_model=SessionOut)
async def logout(response: Response) -> SessionOut:
    settings = get_settings()
    response.delete_cookie(COOKIE_NAME, path="/")
    return SessionOut(authenticated=False, auth_required=settings.auth_enabled, username=None)


@router.get("/me", response_model=SessionOut)
async def me(request: Request) -> SessionOut:
    settings = get_settings()
    if not settings.auth_enabled:
        return SessionOut(authenticated=True, auth_required=False, username=None)
    token = request.cookies.get(COOKIE_NAME)
    username = verify_token(settings, token) if token else None
    if username is None:
        return SessionOut(authenticated=False, auth_required=True, username=None)
    return SessionOut(authenticated=True, auth_required=True, username=username)
