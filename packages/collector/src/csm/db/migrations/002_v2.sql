-- 002_v2.sql — v2 schema additions.
--
-- Single migration carrying all v2 schema additions so the version table
-- stays compact. Per docs/spec.md v2 plan §4 cross-cutting concerns.
--
-- Adds:
--   sessions: title / title_source / agent_kind / agent_kind_confidence /
--             nickname / activity_summary / activity_updated_at
--   transcript_messages: subagent_virtual_id (for token attribution)
--   subagent_sessions: virtual rows for in-session Agent tool calls
--   permission_requests: pending Allow/Deny/Ask decisions
--   settings: api_secret + approval_enabled / approval_tools /
--             approval_timeout_ms + dashboard_url
--
-- All ADD COLUMN statements are individually safe under SQLite's
-- "ALTER TABLE ADD COLUMN" semantics — they run inside the migration
-- runner's BEGIN IMMEDIATE / COMMIT (per db/runner.py) so partial
-- application rolls back atomically. CREATE TABLE / CREATE INDEX use
-- IF NOT EXISTS so an interrupted retry is idempotent. INSERTs use
-- OR IGNORE so seed rows don't duplicate on re-run.

-- ── A: sessions identity columns ──
ALTER TABLE sessions ADD COLUMN title                   TEXT;
ALTER TABLE sessions ADD COLUMN title_source            TEXT;
ALTER TABLE sessions ADD COLUMN agent_kind              TEXT;
ALTER TABLE sessions ADD COLUMN agent_kind_confidence   REAL;
ALTER TABLE sessions ADD COLUMN nickname                TEXT;
ALTER TABLE sessions ADD COLUMN activity_summary        TEXT;
ALTER TABLE sessions ADD COLUMN activity_updated_at     TEXT;

-- ── C: in-session subagent virtual rows ──
ALTER TABLE transcript_messages ADD COLUMN subagent_virtual_id TEXT;

CREATE INDEX IF NOT EXISTS idx_transcript_subagent
    ON transcript_messages(subagent_virtual_id);

CREATE TABLE IF NOT EXISTS subagent_sessions (
    virtual_id          TEXT PRIMARY KEY,
    parent_session_id   TEXT NOT NULL,
    tool_use_id         TEXT NOT NULL,
    title               TEXT,
    description         TEXT,
    prompt              TEXT,
    agent_kind          TEXT,
    subagent_type       TEXT,
    state               TEXT NOT NULL DEFAULT 'running',
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE (parent_session_id, tool_use_id)
);

CREATE INDEX IF NOT EXISTS idx_subagent_parent
    ON subagent_sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_state
    ON subagent_sessions(state);

-- ── D: pending permission requests ──
CREATE TABLE IF NOT EXISTS permission_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    tool_use_id     TEXT,
    tool_name       TEXT NOT NULL,
    tool_input_json TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    decision_reason TEXT,
    requested_at    TEXT NOT NULL,
    decided_at      TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_perm_status
    ON permission_requests(status, requested_at);
CREATE INDEX IF NOT EXISTS idx_perm_session
    ON permission_requests(session_id);

-- ── settings seeds for v2 ──
-- api_secret is generated on csm install (csm/cli/install.py). Empty
-- means "approval feature unconfigured"; csm doctor warns when
-- approval_enabled=1 but api_secret is empty.
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('api_secret',             ''),
    ('approval_enabled',       '0'),
    ('approval_tools',         ''),
    ('approval_timeout_ms',    '60000'),
    ('dashboard_url',          '');
