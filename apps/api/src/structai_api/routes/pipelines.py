"""Pipeline revision routes. Implemented in Phase 3 (plan §10, §6.4)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
