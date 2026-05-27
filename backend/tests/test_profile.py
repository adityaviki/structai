from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from structai.pipeline.profile import profile_document

if TYPE_CHECKING:
    from pathlib import Path


def test_profile_csv_basic(tmp_path: Path) -> None:
    csv = tmp_path / "people.csv"
    csv.write_text(
        "id,name,age,email\n"
        "1,Alice,30,alice@example.com\n"
        "2,Bob,25,bob@example.com\n"
        "3,Carol,,carol@example.com\n"
    )
    prof = profile_document(csv, "csv")
    assert prof.format == "csv"
    assert len(prof.regions) == 1
    region = prof.regions[0]
    assert region.name == "default"
    assert region.row_count == 3
    assert [c.name for c in region.columns] == ["id", "name", "age", "email"]

    types = {c.name: c.inferred_type for c in region.columns}
    assert types["id"] == "int"
    assert types["name"] == "string"
    assert types["age"] in ("int", "float")
    assert types["email"] == "string"

    age_col = next(c for c in region.columns if c.name == "age")
    assert age_col.null_rate > 0


def test_profile_tsv_basic(tmp_path: Path) -> None:
    tsv = tmp_path / "people.tsv"
    tsv.write_text("id\tname\n1\tAlice\n2\tBob\n")
    prof = profile_document(tsv, "tsv")
    assert prof.format == "tsv"
    assert len(prof.regions) == 1
    assert prof.regions[0].row_count == 2


def test_profile_json_array_of_objects(tmp_path: Path) -> None:
    j = tmp_path / "people.json"
    j.write_text(json.dumps([
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Carol"},
    ]))
    prof = profile_document(j, "json")
    assert prof.format == "json"
    assert len(prof.regions) == 1
    assert prof.regions[0].name == "default"
    assert prof.regions[0].row_count == 3


def test_profile_json_object_of_arrays(tmp_path: Path) -> None:
    j = tmp_path / "shop.json"
    j.write_text(json.dumps({
        "customers": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        "orders": [
            {"id": 10, "customer_id": 1},
            {"id": 11, "customer_id": 2},
            {"id": 12, "customer_id": 1},
        ],
    }))
    prof = profile_document(j, "json")
    assert prof.format == "json"
    names = {r.name for r in prof.regions}
    assert names == {"customers", "orders"}
    by_name = {r.name: r for r in prof.regions}
    assert by_name["customers"].row_count == 2
    assert by_name["orders"].row_count == 3


def test_profile_json_ndjson(tmp_path: Path) -> None:
    j = tmp_path / "events.json"
    j.write_text(
        '{"id": 1, "kind": "click"}\n'
        '{"id": 2, "kind": "view"}\n'
        '{"id": 3, "kind": "click"}\n'
    )
    prof = profile_document(j, "json")
    assert len(prof.regions) == 1
    assert prof.regions[0].row_count == 3


def test_profile_rejects_unknown_ext(tmp_path: Path) -> None:
    p = tmp_path / "x.parquet"
    p.write_text("")
    with pytest.raises(ValueError):
        profile_document(p, "parquet")


def test_profile_rejects_non_utf8_csv(tmp_path: Path) -> None:
    p = tmp_path / "ansi.csv"
    # Real Windows-1252 export: header in ASCII, value cell contains 0xd6 (Ö).
    p.write_bytes(b"id,name\n1,Bj\xd6rn\n")
    with pytest.raises(ValueError, match="not UTF-8"):
        profile_document(p, "csv")
