from pydantic import BaseModel


class FkRef(BaseModel):
    table: str
    column: str


class SchemaColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    is_pk: bool
    fk: FkRef | None = None


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn]
    row_count: int


class ProjectSchemaOut(BaseModel):
    tables: list[SchemaTable]


class LayoutPosition(BaseModel):
    table_name: str
    x: float
    y: float


class LayoutOut(BaseModel):
    positions: list[LayoutPosition]


class LayoutUpsertIn(BaseModel):
    positions: list[LayoutPosition]
