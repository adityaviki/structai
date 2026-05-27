-- Phase 0: the migration runner itself creates schema_migrations on first
-- contact, so this file is intentionally a no-op marker. Future phases will
-- add real DDL (projects, documents, import_runs, ...).
SELECT 1;
