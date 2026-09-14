-- Initial database schema for the Task Analyzer server (version 1).
--
-- Covers PCE-19, PCE-20, PCE-24, PCE-25 and PCE-29 (REQ-028, REQ-029,
-- REQ-031).
--
-- Timestamps are integer microseconds since the UTC epoch. Deadlines are
-- calendar dates stored as YYYY-MM-DD text. Title comparison uses the
-- precomputed application title key with SQLite's default BINARY
-- collation; no database collation applies its own normalization.
--
-- This file holds no transaction control. The initializer wraps it in a
-- single transaction, so the schema and its version row are installed
-- together or not at all.

CREATE TABLE schema_version (
    schema_version_id INTEGER NOT NULL PRIMARY KEY
        CHECK (schema_version_id = 1),
    version INTEGER NOT NULL
);

CREATE TABLE product_configuration (
    configuration_id INTEGER NOT NULL PRIMARY KEY
        CHECK (configuration_id = 1),
    product_time_zone TEXT NOT NULL
);

CREATE TABLE tasks (
    task_id TEXT NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL,
    observations TEXT,
    deadline_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
    created_at_us INTEGER NOT NULL,
    latest_completed_at_us INTEGER,
    is_deleted INTEGER NOT NULL CHECK (is_deleted IN (0, 1))
);

-- The operation ledger deliberately has no foreign key to tasks: an
-- original result must survive independently of the task row.
CREATE TABLE operation_results (
    operation_id TEXT NOT NULL PRIMARY KEY,
    canonical_request TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('succeeded', 'rejected')),
    http_status INTEGER NOT NULL,
    serialized_result TEXT NOT NULL,
    resolved_at_us INTEGER NOT NULL
);

-- Dated tasks: one title key per deadline date, irrespective of status.
CREATE UNIQUE INDEX tasks_dated_title_key_unique
    ON tasks (title_key, deadline_date)
    WHERE is_deleted = 0 AND deadline_date IS NOT NULL;

-- Undated tasks: one pending title key. Completing an undated task
-- frees its title.
CREATE UNIQUE INDEX tasks_undated_pending_title_key_unique
    ON tasks (title_key)
    WHERE is_deleted = 0 AND deadline_date IS NULL AND status = 'pending';

INSERT INTO schema_version (schema_version_id, version) VALUES (1, 1);
