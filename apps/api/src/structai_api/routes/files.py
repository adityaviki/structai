"""File upload + profile fetch routes. Implemented in Phase 1 (plan §10)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/files", tags=["files"])
