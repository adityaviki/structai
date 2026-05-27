"""Settings endpoints (Phase 6)."""

from __future__ import annotations

from fastapi import APIRouter

from ..db import settings_repo
from ..db.pools import get_pools
from ..schemas.settings import ProjectModelIn, SettingsOut, SettingsPatch
from .errors import ApiError

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def _read_effective() -> SettingsOut:
    key, key_source = await settings_repo.effective_anthropic_key()
    model, model_source = await settings_repo.effective_default_model()
    keep_n, max_age = await settings_repo.effective_retention()
    return SettingsOut(
        anthropic_key_present=key is not None,
        anthropic_key_source=key_source,
        default_model=model,
        default_model_source=model_source,
        snapshot_keep_last_n=keep_n,
        snapshot_max_age_days=max_age,
    )


@router.get("", response_model=SettingsOut)
async def get_settings_endpoint() -> SettingsOut:
    return await _read_effective()


@router.patch("", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch) -> SettingsOut:
    if body.anthropic_api_key is not None:
        if not body.anthropic_api_key.strip():
            raise ApiError(status=400, title="Bad value", detail="API key cannot be blank.")
        await settings_repo.set_value("anthropic_api_key", body.anthropic_api_key.strip())
    if body.clear_anthropic_api_key:
        await settings_repo.delete_value("anthropic_api_key")
    if body.default_model is not None:
        await settings_repo.set_value("default_model", body.default_model.strip())
    if body.snapshot_keep_last_n is not None:
        await settings_repo.set_value(
            "snapshot_keep_last_n", str(body.snapshot_keep_last_n)
        )
    if body.snapshot_max_age_days is not None:
        await settings_repo.set_value(
            "snapshot_max_age_days", str(body.snapshot_max_age_days)
        )
    return await _read_effective()


# Per-project model override.

project_router = APIRouter(prefix="/api/projects", tags=["projects"])


@project_router.put("/{project_id}/model", response_model=dict[str, str | None])
async def set_project_model(project_id: str, body: ProjectModelIn) -> dict[str, str | None]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM projects WHERE id = $1", project_id
        )
        if existing is None:
            raise ApiError(
                status=404, title="Not found", detail=f"Project {project_id!r} not found."
            )
        await conn.execute(
            "UPDATE projects SET model_override = $2, updated_at = now() WHERE id = $1",
            project_id,
            body.model_override,
        )
    return {"model_override": body.model_override}
