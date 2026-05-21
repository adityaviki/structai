"""Sniffer tests — encoding, delimiter, header detection across the 9
Phase-1 CSV/TSV fixtures (CHECKLIST.md lines 122-130, 133)."""

from __future__ import annotations

from pathlib import Path

import pytest

from structai_core.io.sniff import SniffError, sniff

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "csv"


# (filename, expected_encoding, expected_delimiter, expected_has_header, expected_bom)
CASES = [
    ("bom.csv", "utf-8-sig", ",", True, True),
    ("semicolon.csv", "utf-8", ";", True, False),
    ("mixed_types.csv", "utf-8", ",", True, False),
    ("all_null.csv", "utf-8", ",", True, False),
    ("single_row.csv", "utf-8", ",", True, False),
    ("german_decimals.csv", "utf-8", ";", True, False),
    ("leading_zero_ids.csv", "utf-8", ",", True, False),
    ("quoted_newlines.csv", "utf-8", ",", True, False),
    ("ragged.csv", "utf-8", ",", True, False),
]


@pytest.mark.parametrize(
    "filename,expected_encoding,expected_delimiter,expected_has_header,expected_bom",
    CASES,
)
def test_sniff_fixture(
    filename: str,
    expected_encoding: str,
    expected_delimiter: str,
    expected_has_header: bool,
    expected_bom: bool,
) -> None:
    result = sniff(FIXTURE_DIR / filename)
    assert result.encoding == expected_encoding, f"{filename}: encoding"
    assert result.delimiter == expected_delimiter, f"{filename}: delimiter"
    assert result.has_header is expected_has_header, f"{filename}: has_header"
    assert result.bom is expected_bom, f"{filename}: bom"
    assert result.confidence > 0.0
    assert result.line_terminator in {"\n", "\r\n"}


def test_sniff_bom_byte_present(tmp_path: Path) -> None:
    """BOM detection must look at the raw byte prefix, not just the decoded text."""
    path = tmp_path / "boom.csv"
    path.write_bytes(b"\xef\xbb\xbfid,name\n1,a\n2,b\n")
    result = sniff(path)
    assert result.bom is True
    assert result.encoding == "utf-8-sig"


def test_sniff_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(SniffError):
        sniff(path)


def test_sniff_whitespace_only_raises(tmp_path: Path) -> None:
    path = tmp_path / "blank.csv"
    path.write_text("\n\n\n")
    with pytest.raises(SniffError):
        sniff(path)


def test_sniff_numeric_header_treated_as_no_header(tmp_path: Path) -> None:
    """Fixture with numeric 'headers' (e.g. year columns 2020/2021/2022) and
    numeric data should be reported as has_header=False so the profiler can
    surface the row 0 values as data."""
    path = tmp_path / "numeric_header.csv"
    path.write_text(
        "2020,2021,2022\n100,110,121\n95,108,118\n88,99,105\n80,92,99\n"
    )
    result = sniff(path)
    assert result.delimiter == ","
    assert result.has_header is False


def test_sniff_single_column_falls_back_to_default_delimiter(tmp_path: Path) -> None:
    """A file with no candidate-delimiter occurrences (single-column) returns
    the default delimiter with low confidence, not a SniffError."""
    path = tmp_path / "single_col.csv"
    path.write_text("name\nalice\nbob\ncarol\n")
    result = sniff(path)
    assert result.delimiter == ","
    assert result.confidence <= 0.5


def test_sniff_crlf_line_terminator(tmp_path: Path) -> None:
    path = tmp_path / "crlf.csv"
    path.write_bytes(b"id,name\r\n1,alice\r\n2,bob\r\n")
    result = sniff(path)
    assert result.line_terminator == "\r\n"
    assert result.delimiter == ","
    assert result.has_header is True


def test_sniff_tab_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "data.tsv"
    path.write_text("id\tname\tscore\n1\talice\t87\n2\tbob\t91\n")
    result = sniff(path)
    assert result.delimiter == "\t"
    assert result.has_header is True
