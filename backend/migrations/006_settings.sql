-- Phase 6: app-level settings (key-value) + per-project model override.

CREATE TABLE app_settings (
    key         text         PRIMARY KEY,
    value       text         NOT NULL,
    updated_at  timestamptz  NOT NULL DEFAULT now()
);

ALTER TABLE projects ADD COLUMN model_override text;
