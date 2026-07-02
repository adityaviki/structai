-- Chat agent for data operations.
--
-- A persisted conversation per project plus the data/schema changes it
-- proposes. Mirrors the import-undo model (D15): each *applied* change clones
-- the project DB first (data_changes.snapshot_db) so it is one-click
-- reversible. Only the most-recently-applied change keeps its snapshot, so at
-- most one row per project carries a non-null snapshot_db at a time.

CREATE TABLE data_changes (
    id              text        PRIMARY KEY,
    project_id      text        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_table    text,
    summary         text,
    sql             text        NOT NULL,
    affected_rows   integer,
    total_rows      integer,
    preview         jsonb,
    status          text        NOT NULL DEFAULT 'proposing',
    snapshot_db     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    applied_at      timestamptz,
    reverted_at     timestamptz
);

CREATE INDEX data_changes_project_idx ON data_changes (project_id, created_at);

CREATE TABLE chat_messages (
    id          text        PRIMARY KEY,
    project_id  text        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role        text        NOT NULL,
    content     text        NOT NULL DEFAULT '',
    change_id   text        REFERENCES data_changes(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chat_messages_project_idx ON chat_messages (project_id, created_at);
