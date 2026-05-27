from datetime import datetime

from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    emoji: str | None = None
    color: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    emoji: str | None
    color: str | None
    db_name: str
    created_at: datetime
    updated_at: datetime


class ProjectStats(BaseModel):
    tables: int
    documents: int
    imports_completed: int


class ProjectWithStatsOut(ProjectOut):
    stats: ProjectStats
