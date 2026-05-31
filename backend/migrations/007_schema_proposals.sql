-- Phase 7: schema-approval gate. After profiling, the agent proposes a
-- DDL. The user accepts it or asks for changes; each revision creates a
-- new row with an incremented iteration. The latest non-superseded row
-- per run is the active proposal.

CREATE TABLE schema_proposals (
    id          text        PRIMARY KEY,
    run_id      text        NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
    iteration   integer     NOT NULL,
    schema_ddl  text        NOT NULL,
    tables      text[]      NOT NULL,
    rationale   text        NOT NULL,
    status      text        NOT NULL DEFAULT 'pending',
        -- pending | accepted | superseded
    feedback    text,
        -- user-supplied revision request that produced the NEXT iteration
    auto_accepted boolean   NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    decided_at  timestamptz,
    UNIQUE (run_id, iteration)
);

CREATE INDEX schema_proposals_run_idx
    ON schema_proposals (run_id, iteration);
