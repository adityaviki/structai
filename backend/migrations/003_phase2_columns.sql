-- Phase 2: add cancellation, snapshot, and undo tracking to import_runs.

ALTER TABLE import_runs
    ADD COLUMN cancel_requested  boolean      NOT NULL DEFAULT false,
    ADD COLUMN snapshot_db       text,
    ADD COLUMN snapshot_pinned   boolean      NOT NULL DEFAULT false,
    ADD COLUMN reverted_at       timestamptz,
    ADD COLUMN reverted_by_run_id text REFERENCES import_runs(id) ON DELETE SET NULL;

CREATE INDEX import_runs_snapshot_db_idx ON import_runs (snapshot_db)
    WHERE snapshot_db IS NOT NULL;
