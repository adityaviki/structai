from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentExt = Literal["csv", "tsv", "xlsx", "json"]
DocumentStatus = Literal["uploaded", "importing", "imported", "failed", "needs_attention"]


class DocumentOut(BaseModel):
    id: str
    project_id: str
    name: str
    ext: DocumentExt
    size_bytes: int
    status: DocumentStatus
    last_import_id: str | None
    uploaded_at: datetime
