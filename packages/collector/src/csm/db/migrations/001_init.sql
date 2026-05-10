-- 001_init.sql — claude-sidecar-monitor schema v1.
--
-- Per docs/spec.md §4.2. PRAGMAs (foreign_keys, journal_mode) are set
-- on the connection in csm.db.connect() — NOT here.
--
-- Statements use IF NOT EXISTS / OR IGNORE so the migration is safe to
-- re-run if it failed partway through (the runner will then re-record
-- the version in _migrations on the retry).

CREATE TABLE IF NOT EXISTS sessions (
    session_id           TEXT PRIMARY KEY,
    parent_session_id    TEXT,
    worktree_root        TEXT NOT NULL,
    project_label        TEXT,
    cwd                  TEXT NOT NULL,
    transcript_path      TEXT,
    agent_type           TEXT,
    state                TEXT NOT NULL DEFAULT 'running',
    last_event_at        TEXT NOT NULL,
    last_event_name      TEXT,
    last_tool_name       TEXT,
    started_at           TEXT NOT NULL,
    completed_at         TEXT,
    primary_model        TEXT,
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens   INTEGER NOT NULL DEFAULT 0,
    notification         TEXT,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_worktree     ON sessions(worktree_root);
CREATE INDEX IF NOT EXISTS idx_sessions_parent       ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_state        ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_last_event   ON sessions(last_event_at);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at   ON sessions(started_at);

CREATE TABLE IF NOT EXISTS events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    event_name    TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    tool_name     TEXT,
    tool_use_id   TEXT,
    duration_ms   INTEGER,
    payload_json  TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_session  ON events(session_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_name     ON events(event_name, received_at DESC);

CREATE TABLE IF NOT EXISTS transcript_messages (
    message_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                    TEXT NOT NULL,
    role                          TEXT NOT NULL,
    timestamp                     TEXT NOT NULL,
    content_json                  TEXT NOT NULL,
    model                         TEXT,
    input_tokens                  INTEGER,
    output_tokens                 INTEGER,
    cache_creation_input_tokens   INTEGER,
    cache_read_input_tokens       INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transcript_session  ON transcript_messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_transcript_model    ON transcript_messages(model, timestamp);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS _offsets (
    file_path    TEXT PRIMARY KEY,
    byte_offset  INTEGER NOT NULL,
    last_inode   INTEGER,
    last_seen    TEXT NOT NULL
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('hang_yellow_ms', '60000'),
    ('hang_red_ms',    '180000'),
    ('ntfy_topic',     '');
