"""Job inspection routes. Implemented across Phases 1–4 (plan §10)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/jobs", tags=["jobs"])
