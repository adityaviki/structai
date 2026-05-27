-- Phase 3: clarifications table. The orchestrator inserts a row when the
-- agent's `ask_clarification` tool fires; the API answer endpoint updates
-- the answer columns; the worker watchdog wakes when answered.
--
-- The same table holds auto-mode-recorded decisions, distinguished by
-- `auto_decision = true`. No separate `auto_decisions` table needed.

CREATE TABLE clarifications (
    id              text        PRIMARY KEY,
    run_id          text        NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
    question        text        NOT NULL,
    context         text,
    options         jsonb       NOT NULL,
    answer_choice_id text,
    answer_custom   text,
    auto_decision   boolean     NOT NULL DEFAULT false,
    auto_reasoning  text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    answered_at     timestamptz
);

CREATE INDEX clarifications_run_idx ON clarifications (run_id, created_at);
