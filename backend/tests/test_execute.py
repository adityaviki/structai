from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from structai.pipeline.execute import execute_script

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT_OK = """
import sys, json, pathlib
doc = pathlib.Path(sys.argv[1])
pg = sys.argv[2]
sys.stderr.write(f"received doc={doc} pg={pg}\\n")
print(json.dumps({"rows_imported": 5, "tables": ["customers"]}))
"""

SCRIPT_FAIL = """
import sys
sys.stderr.write("boom\\n")
sys.exit(2)
"""

SCRIPT_SLOW = """
import time
time.sleep(5)
"""


@pytest.mark.asyncio
async def test_execute_success(tmp_path: Path) -> None:
    doc = tmp_path / "data.csv"
    doc.write_text("a,b\n1,2\n")
    res = await execute_script(
        script=SCRIPT_OK,
        doc_path=doc,
        pg_url="postgresql://dummy/none",
        workdir=tmp_path / "run",
    )
    assert res.exit_code == 0, res.stderr
    assert res.rows_imported == 5
    assert res.tables_reported == ["customers"]
    assert not res.timed_out


@pytest.mark.asyncio
async def test_execute_failure(tmp_path: Path) -> None:
    res = await execute_script(
        script=SCRIPT_FAIL,
        doc_path=tmp_path / "x.csv",
        pg_url="postgresql://dummy/none",
        workdir=tmp_path / "run",
    )
    assert res.exit_code == 2
    assert res.rows_imported is None
    assert "boom" in res.stderr


@pytest.mark.asyncio
async def test_execute_timeout(tmp_path: Path) -> None:
    res = await execute_script(
        script=SCRIPT_SLOW,
        doc_path=tmp_path / "x.csv",
        pg_url="postgresql://dummy/none",
        workdir=tmp_path / "run",
        timeout_seconds=1,
    )
    assert res.timed_out
    assert res.exit_code != 0


@pytest.mark.asyncio
async def test_execute_cancel(tmp_path: Path) -> None:
    import asyncio

    cancel = asyncio.Event()

    async def cancel_soon() -> None:
        await asyncio.sleep(0.2)
        cancel.set()

    asyncio.create_task(cancel_soon())
    res = await execute_script(
        script=SCRIPT_SLOW,
        doc_path=tmp_path / "x.csv",
        pg_url="postgresql://dummy/none",
        workdir=tmp_path / "run",
        timeout_seconds=10,
        cancel_event=cancel,
    )
    assert res.cancelled
    assert not res.timed_out
