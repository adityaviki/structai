"""FastAPI app entrypoint.

Wires routes and exposes `/healthz`. All heavy work runs in `apps/worker`;
this process only orchestrates (plan §3).
"""

from __future__ import annotations

from fastapi import FastAPI

from structai_api.routes import files, jobs, pipelines, runs, schemas, sessions, tables

app = FastAPI(title="StructAI API", version="0.0.0")

app.include_router(files.router)
app.include_router(sessions.router)
app.include_router(jobs.router)
app.include_router(schemas.router)
app.include_router(pipelines.router)
app.include_router(runs.router)
app.include_router(tables.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
