"""API tests for `/files` upload + listing + profile fetch
(CHECKLIST.md line 141). Uses `httpx.AsyncClient` + `ASGITransport` so
the FastAPI app runs in the test's own event loop (otherwise the
asyncpg engine sees cross-loop futures)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from structai_api.deps import get_session, get_settings
from structai_api.main import app
from structai_core.config import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("STRUCTAI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STRUCTAI_MAX_UPLOAD_BYTES", "1048576")  # 1 MB for tests
    return Settings()


@pytest.fixture
async def client(
    settings: Settings,
    db_session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    def override_settings() -> Settings:
        return settings

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _csv_payload(content: bytes = b"id,name\n1,alice\n2,bob\n") -> dict:
    return {"file": ("simple.csv", content, "text/csv")}


# --- POST /files ----------------------------------------------------------


async def test_upload_lands_in_live_no_quarantine_leftover(
    client: AsyncClient, settings: Settings
) -> None:
    resp = await client.post("/files", files=_csv_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["original_name"] == "simple.csv"
    assert body["bytes"] > 0

    quarantine = settings.data_dir / "uploads" / "quarantine"
    live = settings.data_dir / "uploads" / "live"
    assert list(quarantine.iterdir()) == []
    live_files = list(live.iterdir())
    assert len(live_files) == 1
    assert live_files[0].name == f"{body['source_sha256']}.csv"


async def test_upload_rejects_oversized_with_413(
    client: AsyncClient, settings: Settings
) -> None:
    big = b"a" * (settings.max_upload_bytes + 1)
    resp = await client.post(
        "/files", files={"file": ("big.csv", big, "text/csv")}
    )
    assert resp.status_code == 413


async def test_upload_rejects_unsupported_extension_with_415(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/files",
        files={"file": ("data.xlsx", b"\x50\x4b\x03\x04", "application/octet-stream")},
    )
    assert resp.status_code == 415


async def test_upload_dedup_returns_existing_id_with_200(
    client: AsyncClient,
) -> None:
    r1 = await client.post("/files", files=_csv_payload())
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = await client.post("/files", files=_csv_payload())
    assert r2.status_code == 200
    assert r2.json()["id"] == id1


async def test_upload_enqueues_profile_file_job(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    resp = await client.post("/files", files=_csv_payload())
    assert resp.status_code == 201
    file_id = resp.json()["id"]

    rows = (
        await db_session.execute(
            text(
                "SELECT kind, payload_jsonb FROM jobs "
                "WHERE (payload_jsonb->>'file_id')::bigint = :fid"
            ),
            {"fid": file_id},
        )
    ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["kind"] == "profile_file"


async def test_upload_dedup_does_not_double_enqueue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post("/files", files=_csv_payload())
    await client.post("/files", files=_csv_payload())

    n = (
        await db_session.execute(
            text("SELECT count(*) AS n FROM jobs WHERE kind = 'profile_file'")
        )
    ).scalar()
    assert n == 1


async def test_unsniffable_upload_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/files", files={"file": ("empty.csv", b"", "text/csv")}
    )
    assert resp.status_code == 422


# --- GET /files -----------------------------------------------------------


async def test_list_files_orders_desc(client: AsyncClient) -> None:
    await client.post("/files", files={"file": ("a.csv", b"id\n1\n", "text/csv")})
    await client.post("/files", files={"file": ("b.csv", b"id\n2\n", "text/csv")})
    await client.post("/files", files={"file": ("c.csv", b"id\n3\n", "text/csv")})

    resp = await client.get("/files")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [it["original_name"] for it in items]
    assert names == ["c.csv", "b.csv", "a.csv"]


async def test_list_files_status_profiled_when_profile_row_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    upload = (await client.post("/files", files=_csv_payload())).json()
    file_id = upload["id"]
    await db_session.execute(
        text(
            "INSERT INTO profiles (file_id, profile_sha256, profile_jsonb) "
            "VALUES (:fid, :sha, CAST(:jsonb AS jsonb))"
        ),
        {"fid": file_id, "sha": "x" * 64, "jsonb": "{}"},
    )
    await db_session.commit()

    resp = await client.get("/files")
    rows = resp.json()["items"]
    assert rows[0]["status"] == "profiled"
    assert rows[0]["profile_id"] is not None


async def test_list_files_status_failed_when_job_failed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    upload = (await client.post("/files", files=_csv_payload())).json()
    file_id = upload["id"]
    await db_session.execute(
        text(
            "UPDATE jobs SET status='failed', error_class='terminal', last_error='boom' "
            "WHERE (payload_jsonb->>'file_id')::bigint = :fid"
        ),
        {"fid": file_id},
    )
    await db_session.commit()

    resp = await client.get("/files")
    assert resp.json()["items"][0]["status"] == "failed"


# --- GET /files/:id/profile ----------------------------------------------


async def test_get_profile_404_when_no_row(client: AsyncClient) -> None:
    upload = (await client.post("/files", files=_csv_payload())).json()
    resp = await client.get(f"/files/{upload['id']}/profile")
    assert resp.status_code == 404


async def test_get_profile_returns_jsonb_when_present(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    upload = (await client.post("/files", files=_csv_payload())).json()
    profile_jsonb = {
        "row_count": 2,
        "duplicate_row_count": 0,
        "encoding": "utf-8",
        "delimiter": ",",
        "has_header": True,
        "source_sha256": upload["source_sha256"],
        "profile_sha256": "b" * 64,
        "profile_version": "v1",
        "raw_to_safe": {"id": "id", "name": "name"},
        "columns": [],
        "omitted_columns": [],
    }
    await db_session.execute(
        text(
            "INSERT INTO profiles (file_id, profile_sha256, profile_jsonb) "
            "VALUES (:fid, :sha, CAST(:jsonb AS jsonb))"
        ),
        {"fid": upload["id"], "sha": "b" * 64, "jsonb": json.dumps(profile_jsonb)},
    )
    await db_session.commit()

    resp = await client.get(f"/files/{upload['id']}/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2
    assert body["profile_version"] == "v1"
