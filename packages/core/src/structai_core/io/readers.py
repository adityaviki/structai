"""CSV/TSV Reader interface backed by Polars.

`open_reader(path, sniff)` returns a `Reader` whose `scan()` builds a
lazy frame with every column read as `Utf8` so that leading zeros and
European decimals survive into the profiler's type inference (plan §5).
`head(n)` materializes the first n rows for sample extraction;
`read_all()` eagerly reads the whole file. `raw_columns` gives the
header names without scanning the data.

Ragged rows raise `RaggedRowError`. Non-UTF-8 source files fall back to
`utf8-lossy` decoding — full non-UTF-8 support is a v1.1 follow-on
alongside Excel.
"""

from __future__ import annotations

import abc
from pathlib import Path

import polars as pl
from polars.exceptions import ComputeError

from structai_core.io.sniff import SniffResult


class RaggedRowError(ValueError):
    """A row had a different column count from the header."""


class Reader(abc.ABC):
    @abc.abstractmethod
    def scan(self) -> pl.LazyFrame: ...

    @abc.abstractmethod
    def head(self, n: int = 5) -> pl.DataFrame: ...

    @abc.abstractmethod
    def read_all(self) -> pl.DataFrame: ...

    @property
    @abc.abstractmethod
    def raw_columns(self) -> list[str]: ...


class CSVReader(Reader):
    def __init__(self, path: Path, sniff: SniffResult) -> None:
        self._path = path
        self._sniff = sniff
        self._columns_cache: list[str] | None = None

    def scan(self) -> pl.LazyFrame:
        return self._scan_csv()

    def head(self, n: int = 5) -> pl.DataFrame:
        try:
            return self._scan_csv().head(n).collect()
        except ComputeError as exc:
            raise RaggedRowError(_ragged_message(exc)) from exc

    def read_all(self) -> pl.DataFrame:
        try:
            return self._scan_csv().collect()
        except ComputeError as exc:
            raise RaggedRowError(_ragged_message(exc)) from exc

    @property
    def raw_columns(self) -> list[str]:
        if self._columns_cache is None:
            schema = self._scan_csv().collect_schema()
            self._columns_cache = list(schema.names())
        return list(self._columns_cache)

    def _scan_csv(self) -> pl.LazyFrame:
        return pl.scan_csv(
            self._path,
            separator=self._sniff.delimiter,
            quote_char=self._sniff.quotechar,
            has_header=self._sniff.has_header,
            encoding=_polars_encoding(self._sniff.encoding),
            infer_schema_length=0,
            truncate_ragged_lines=False,
            try_parse_dates=False,
        )


class TSVReader(CSVReader):
    def __init__(self, path: Path, sniff: SniffResult) -> None:
        if sniff.delimiter != "\t":
            raise ValueError(
                f"TSVReader requires tab delimiter, got {sniff.delimiter!r}"
            )
        super().__init__(path, sniff)


def open_reader(path: Path, sniff: SniffResult) -> Reader:
    if sniff.delimiter == "\t":
        return TSVReader(path, sniff)
    return CSVReader(path, sniff)


def _polars_encoding(encoding: str) -> str:
    e = encoding.lower()
    if e in {"utf-8", "utf_8", "utf-8-sig"}:
        return "utf8"
    return "utf8-lossy"


def _ragged_message(exc: ComputeError) -> str:
    return f"ragged row in CSV input: {exc}"
