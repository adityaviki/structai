from typing import Any

from pydantic import BaseModel


class FkRef(BaseModel):
    table: str
    column: str


class ColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool
    is_pk: bool
    fk: FkRef | None = None


class TableSummary(BaseModel):
    name: str
    row_count: int
    column_count: int


class TableDetail(BaseModel):
    name: str
    columns: list[ColumnOut]
    row_count: int
    editable: bool = False


class RowsPage(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    next_cursor: str | None = None
