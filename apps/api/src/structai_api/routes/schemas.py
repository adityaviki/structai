"""Profile / inferred-schema routes. Implemented in Phase 1 (plan §10)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/schemas", tags=["schemas"])
