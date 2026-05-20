"""Loaded-table browse routes. Implemented in Phase 5 (plan §10)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/tables", tags=["tables"])
