"""Single-user authentication: password check + signed session cookies.

There is no account creation by design. A single login (username + password)
is configured via env (``STRUCTAI_AUTH_USERNAME`` / ``STRUCTAI_AUTH_PASSWORD``).
While no password is set, :attr:`Settings.auth_enabled` is ``False`` and the
API is unprotected — that keeps local dev and the test suite open.

Sessions are stateless: a successful login mints an HMAC-signed token carrying
the username and an expiry. Nothing is stored server-side, so logins survive
process restarts as long as the signing key is stable. The signing key is
derived from ``STRUCTAI_AUTH_SECRET`` when set, otherwise from the password —
so rotating the password invalidates every outstanding session.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import Settings

COOKIE_NAME = "structai_session"
_APP_SALT = b"structai.session.v1"
_PBKDF2_ROUNDS = 100_000


def _signing_key(settings: Settings) -> bytes:
    secret = settings.auth_secret or settings.auth_password or ""
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), _APP_SALT, _PBKDF2_ROUNDS)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def verify_password(settings: Settings, username: str, password: str) -> bool:
    """Constant-time check of submitted credentials against the configured pair."""

    if not settings.auth_password:
        return False
    user_ok = hmac.compare_digest(username, settings.auth_username)
    pass_ok = hmac.compare_digest(password, settings.auth_password)
    return user_ok and pass_ok


def issue_token(settings: Settings, username: str, *, now: float | None = None) -> str:
    """Mint a signed session token for ``username``."""

    issued = time.time() if now is None else now
    expiry = int(issued) + settings.auth_session_ttl_hours * 3600
    payload = f"{username}|{expiry}".encode()
    sig = hmac.new(_signing_key(settings), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(sig)}"


def verify_token(settings: Settings, token: str, *, now: float | None = None) -> str | None:
    """Return the username if ``token`` is well-formed, unexpired and signed by us."""

    checked_at = time.time() if now is None else now
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64decode(payload_b64)
        sig = _b64decode(sig_b64)
    except (ValueError, binascii.Error):
        return None
    expected = hmac.new(_signing_key(settings), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        username, expiry_str = payload.decode().rsplit("|", 1)
        expiry = int(expiry_str)
    except (ValueError, UnicodeDecodeError):
        return None
    if checked_at >= expiry:
        return None
    return username
