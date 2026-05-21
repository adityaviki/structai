"""CSV/TSV file sniffer.

Determines encoding (via `charset-normalizer`), delimiter (per-line vote
cross-checked against `csv.Sniffer`), header presence (per-column numeric
vs string comparison), and line terminator from the first ~64 KB of a
file. Plan §5; CHECKLIST.md line 76.

The sniffer never reads more than `sample_bytes`; downstream consumers
(`io.readers`) re-read the file with the chosen dialect.
"""

from __future__ import annotations

import csv
import io
import statistics
from pathlib import Path

from charset_normalizer import from_bytes
from pydantic import BaseModel

BOM_UTF8 = b"\xef\xbb\xbf"
BOM_UTF16_LE = b"\xff\xfe"
BOM_UTF16_BE = b"\xfe\xff"

CANDIDATE_DELIMITERS: tuple[str, ...] = (",", ";", "\t", "|")
DEFAULT_DELIMITER = ","


class SniffResult(BaseModel):
    """Output of `sniff()` — enough to open the file with `csv.reader` /
    `polars.scan_csv` correctly.
    """

    encoding: str
    bom: bool
    delimiter: str
    quotechar: str = '"'
    has_header: bool
    line_terminator: str
    confidence: float


class SniffError(ValueError):
    """Raised when the file is unreadable for sniffing (empty, undecodable)."""


def sniff(path: Path, *, sample_bytes: int = 65_536) -> SniffResult:
    raw = path.read_bytes()[:sample_bytes]
    if not raw:
        raise SniffError(f"file is empty: {path}")

    bom, encoding_hint, body = _strip_bom(raw)
    encoding = encoding_hint if encoding_hint is not None else _detect_encoding(body)
    try:
        text = body.decode(encoding)
    except UnicodeDecodeError as exc:
        raise SniffError(f"failed to decode {path} as {encoding}: {exc}") from exc

    if not text.strip():
        raise SniffError(f"file is whitespace-only: {path}")

    line_terminator = "\r\n" if b"\r\n" in raw else "\n"
    delimiter, delim_confidence = _detect_delimiter(text)
    has_header, header_confidence = _detect_has_header(text, delimiter)

    reported_encoding = (
        "utf-8-sig" if bom and encoding.lower() in {"utf-8", "utf_8"} else encoding
    )

    return SniffResult(
        encoding=reported_encoding,
        bom=bom,
        delimiter=delimiter,
        has_header=has_header,
        line_terminator=line_terminator,
        confidence=min(delim_confidence, header_confidence),
    )


def _strip_bom(raw: bytes) -> tuple[bool, str | None, bytes]:
    """Returns (has_bom, encoding_hint, body_without_bom)."""
    if raw.startswith(BOM_UTF8):
        return True, "utf-8", raw[len(BOM_UTF8) :]
    if raw.startswith(BOM_UTF16_LE):
        return True, "utf-16-le", raw[len(BOM_UTF16_LE) :]
    if raw.startswith(BOM_UTF16_BE):
        return True, "utf-16-be", raw[len(BOM_UTF16_BE) :]
    return False, None, raw


def _detect_encoding(body: bytes) -> str:
    best = from_bytes(body).best()
    if best is None:
        return "latin-1"
    raw = str(best.encoding).replace("_", "-").lower()
    # ASCII is a strict subset of UTF-8; report UTF-8 so downstream consumers
    # (Polars `scan_csv`) handle later non-ASCII content correctly without a
    # re-sniff. Same idea for charset-normalizer's "ascii" alias.
    if raw == "ascii":
        return "utf-8"
    return raw


def _detect_delimiter(text: str) -> tuple[str, float]:
    lines = [line for line in text.splitlines() if line.strip()][:20]
    if not lines:
        return DEFAULT_DELIMITER, 0.0

    counts: dict[str, list[int]] = {
        d: [line.count(d) for line in lines] for d in CANDIDATE_DELIMITERS
    }

    majority_threshold = (len(lines) + 1) // 2
    viable = {
        d: cs
        for d, cs in counts.items()
        if sum(1 for c in cs if c > 0) >= majority_threshold and max(cs) > 0
    }

    if not viable:
        return DEFAULT_DELIMITER, 0.2

    def score(cs: list[int]) -> tuple[float, float]:
        var = statistics.pvariance(cs) if len(cs) > 1 else 0.0
        return (var, -statistics.fmean(cs))

    voted = min(viable, key=lambda d: score(viable[d]))

    sniffer_confirmed = False
    try:
        dialect = csv.Sniffer().sniff(text, delimiters="".join(CANDIDATE_DELIMITERS))
        sniffer_confirmed = dialect.delimiter == voted
    except csv.Error:
        pass

    return voted, (0.95 if sniffer_confirmed else 0.7)


def _detect_has_header(text: str, delimiter: str) -> tuple[bool, float]:
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    if not rows:
        return False, 0.0
    if len(rows) == 1:
        return True, 0.5

    header = rows[0]
    data_rows = rows[1:11]

    numeric_columns = 0
    header_strings_in_numeric_columns = 0
    for i, h in enumerate(header):
        col_values = [r[i] for r in data_rows if i < len(r)]
        if not col_values:
            continue
        data_numeric_rate = sum(1 for v in col_values if _looks_numeric(v)) / len(col_values)
        if data_numeric_rate >= 0.5:
            numeric_columns += 1
            if not _looks_numeric(h):
                header_strings_in_numeric_columns += 1

    if numeric_columns == 0:
        # All-string file — assume header (common case for CSVs in the wild).
        return True, 0.5

    if header_strings_in_numeric_columns >= 1:
        return True, 0.9
    return False, 0.8


def _looks_numeric(value: str) -> bool:
    v = value.strip().replace(" ", "")
    if not v:
        return False
    try:
        float(v)
        return True
    except ValueError:
        return False
