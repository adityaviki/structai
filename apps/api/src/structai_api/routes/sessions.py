"""Agent session routes. Implemented in Phase 2 (plan §10)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/sessions", tags=["sessions"])
