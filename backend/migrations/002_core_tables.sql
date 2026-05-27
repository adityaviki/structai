-- Phase 1: the core tables in structai_meta.
-- See PLAN.md D3 for the layout rationale (one structai_meta DB plus one
-- DB per project; this migration only touches structai_meta).

CREATE TABLE projects (
    id          text        PRIMARY KEY,
    name        text        NOT NULL,
    description text,
    emoji       text,
    color       text,
    db_name     text        NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX projects_updated_at_idx ON projects (updated_at DESC);

CREATE TABLE documents (
    id            text        PRIMARY KEY,
    project_id    text        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name          text        NOT NULL,
    ext           text        NOT NULL,
    size_bytes    bigint      NOT NULL,
    storage_path  text        NOT NULL,
    status        text        NOT NULL DEFAULT 'uploaded',
    last_import_id text,
    uploaded_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_project_uploaded_idx
    ON documents (project_id, uploaded_at DESC);

CREATE TABLE import_runs (
    id              text        PRIMARY KEY,
    project_id      text        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id     text        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title           text        NOT NULL,
    status          text        NOT NULL DEFAULT 'queued',
    progress        integer     NOT NULL DEFAULT 0,
    instructions    text,
    auto_mode       boolean     NOT NULL DEFAULT false,
    rows_imported   bigint,
    total_rows      bigint,
    created_tables  text[],
    error_message   text,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz
);

CREATE INDEX import_runs_project_started_idx
    ON import_runs (project_id, started_at DESC);
CREATE INDEX import_runs_status_idx
    ON import_runs (status);

CREATE TABLE pipeline_steps (
    id          bigserial   PRIMARY KEY,
    run_id      text        NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
    step_key    text        NOT NULL,
    status      text        NOT NULL,
    title       text        NOT NULL,
    summary     text,
    code        text,
    language    text,
    attempts    integer     NOT NULL DEFAULT 1,
    errors      text[],
    started_at  timestamptz,
    duration_ms integer,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, step_key, attempts)
);

CREATE INDEX pipeline_steps_run_idx
    ON pipeline_steps (run_id, created_at);
