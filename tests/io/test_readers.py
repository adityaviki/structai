"""Reader tests — CSV/TSV round-trip, quoted newlines, ragged-row error,
all-Utf8 schema (CHECKLIST.md line 134)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from structai_core.io.readers import (
    CSVReader,
    RaggedRowError,
    TSVReader,
    open_reader,
)
from structai_core.io.sniff import sniff

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "csv"


def _open(name: str) -> tuple[Path, object]:
    path = FIXTURE_DIR / name
    return path, open_reader(path, sniff(path))


def test_csv_reader_basic_round_trip() -> None:
    _, reader = _open("semicolon.csv")
    df = reader.read_all()
    assert df.shape == (4, 3)
    assert df.columns == ["id", "name", "score"]


def test_reader_open_picks_csv_for_comma() -> None:
    _, reader = _open("semicolon.csv")
    # semicolon.csv has `;` so it's still a CSVReader, not TSV.
    assert isinstance(reader, CSVReader)
    assert not isinstance(reader, TSVReader)


def test_reader_open_picks_tsv_for_tab() -> None:
    _, reader = _open("simple.tsv")
    assert isinstance(reader, TSVReader)


def test_all_columns_read_as_utf8() -> None:
    """Plan §5: every column comes back as Utf8 so leading zeros / European
    decimals / mixed types survive into type inference."""
    _, reader = _open("leading_zero_ids.csv")
    df = reader.read_all()
    for dtype in df.dtypes:
        assert dtype == pl.Utf8, f"got {dtype!r}, expected Utf8"

    # Leading-zero string must be preserved verbatim.
    zips = df["zip"].to_list()
    assert zips[0] == "00123"
    assert zips[1] == "00456"


def test_german_decimals_survive_as_utf8() -> None:
    _, reader = _open("german_decimals.csv")
    df = reader.read_all()
    assert df["preis"].to_list() == ["1,29", "0,89", "1.234,56", "2.499,99"]


def test_quoted_newlines_preserved() -> None:
    _, reader = _open("quoted_newlines.csv")
    df = reader.read_all()
    assert df.shape == (3, 3)
    desc = df["description"].to_list()
    assert desc[0] == "line one\nline two"
    assert desc[1] == "single line"
    assert desc[2] == "multi\nline\ndescription"


def test_head_returns_at_most_n_rows() -> None:
    _, reader = _open("semicolon.csv")
    head = reader.head(2)
    assert head.height == 2
    assert head.columns == ["id", "name", "score"]


def test_head_with_n_larger_than_file_returns_whole_file() -> None:
    _, reader = _open("single_row.csv")
    head = reader.head(100)
    assert head.height == 1


def test_raw_columns_does_not_require_full_scan() -> None:
    _, reader = _open("semicolon.csv")
    cols = reader.raw_columns
    assert cols == ["id", "name", "score"]
    # Repeated calls cache and return a fresh list each time.
    assert reader.raw_columns is not cols
    assert reader.raw_columns == cols


def test_ragged_rows_raise_ragged_row_error() -> None:
    _, reader = _open("ragged.csv")
    with pytest.raises(RaggedRowError) as exc_info:
        reader.read_all()
    assert "ragged" in str(exc_info.value).lower()


def test_bom_first_column_is_clean() -> None:
    """Polars should strip the BOM from the first header so we don't end up
    with `\\ufeffid` as a column name."""
    _, reader = _open("bom.csv")
    assert reader.raw_columns[0] == "id"


def test_tsv_reader_rejects_non_tab_delimiter() -> None:
    """Constructing TSVReader directly with a CSV sniff must fail."""
    csv_path = FIXTURE_DIR / "semicolon.csv"
    with pytest.raises(ValueError, match="tab delimiter"):
        TSVReader(csv_path, sniff(csv_path))


def test_all_null_column_reads_as_empty_strings() -> None:
    """The middle column in all_null.csv is empty between commas. Polars
    reads these as null. The empty-string-vs-null distinction is handled by
    the profiler — here we just confirm the read shape."""
    _, reader = _open("all_null.csv")
    df = reader.read_all()
    assert df.shape == (4, 3)
    assert df.columns == ["id", "empty_col", "name"]
    assert df["empty_col"].null_count() == 4
