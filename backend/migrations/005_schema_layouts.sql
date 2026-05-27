-- Phase 5: persisted ER-diagram positions per project.

CREATE TABLE schema_layouts (
    project_id  text        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    table_name  text        NOT NULL,
    x           double precision NOT NULL,
    y           double precision NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, table_name)
);
