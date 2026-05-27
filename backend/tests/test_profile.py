from __future__ import annotations

from typing import TYPE_CHECKING

from structai.pipeline.profile import profile_csv

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
    prof = profile_csv(csv)
    assert prof.total_rows == 3
    assert [c.name for c in prof.columns] == ["id", "name", "age", "email"]

    types = {c.name: c.inferred_type for c in prof.columns}
    assert types["id"] == "int"
    assert types["name"] == "string"
    # age has a null and one row may parse as int or float depending on infer
    assert types["age"] in ("int", "float")
    assert types["email"] == "string"

    age_col = next(c for c in prof.columns if c.name == "age")
    assert age_col.null_rate > 0
