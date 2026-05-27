from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    anthropic_key_present: bool
    anthropic_key_source: str  # env | config | unset
    default_model: str
    default_model_source: str  # env | config | default
    snapshot_keep_last_n: int
    snapshot_max_age_days: int


class SettingsPatch(BaseModel):
    anthropic_api_key: str | None = None
    default_model: str | None = None
    snapshot_keep_last_n: int | None = Field(default=None, ge=0, le=1000)
    snapshot_max_age_days: int | None = Field(default=None, ge=0, le=3650)
    clear_anthropic_api_key: bool = False


class ProjectModelIn(BaseModel):
    model_override: str | None
