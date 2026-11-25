"""SQLite 存储（PRD 第 8 章）。

单机黑客松选型：SQLite + WAL。所有查询必须带 openid 做数据隔离。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["SCHEMA", "connect", "init_db"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id              TEXT PRIMARY KEY,
    openid          TEXT NOT NULL,
    short_no        INTEGER NOT NULL,
    title           TEXT NOT NULL,
    start_at        TEXT,
    end_at          TEXT,
    all_day         INTEGER NOT NULL DEFAULT 0,
    location        TEXT,
    deadline_at     TEXT,
    organizer       TEXT,
    notes           TEXT,
    source_type     TEXT NOT NULL,
    source_url      TEXT,
    source_raw      TEXT,
    confidence      TEXT NOT NULL DEFAULT '{}',
    lifecycle       TEXT NOT NULL DEFAULT 'active',
    sync_status     TEXT NOT NULL DEFAULT 'pending',
    calendar_uid    TEXT,
    calendar_href   TEXT,
    calendar_etag   TEXT,
    sequence        INTEGER NOT NULL DEFAULT 0,
    duplicate_of    INTEGER,
    remind_offsets  TEXT,
    remind_at       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_activities_openid_short
    ON activities(openid, short_no);
CREATE INDEX IF NOT EXISTS idx_activities_openid_start
    ON activities(openid, lifecycle, start_at);
CREATE INDEX IF NOT EXISTS idx_activities_sync
    ON activities(openid, sync_status);

CREATE TABLE IF NOT EXISTS user_prefs (
    openid                  TEXT PRIMARY KEY,
    default_remind_offsets  TEXT NOT NULL DEFAULT '[-30,0]',
    all_day_remind_time     TEXT NOT NULL DEFAULT '09:00',
    auto_sync_enabled       INTEGER NOT NULL DEFAULT 1,
    sync_interval_min       INTEGER NOT NULL DEFAULT 10,
    list_offset             INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    msg_id       TEXT PRIMARY KEY,
    openid       TEXT NOT NULL,
    msg_type     TEXT NOT NULL,
    raw_xml      TEXT,
    status       TEXT NOT NULL DEFAULT 'queued',
    task_no      TEXT,
    result_text  TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_openid_created
    ON messages(openid, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_status
    ON messages(status);

CREATE TABLE IF NOT EXISTS pending_actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    openid       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL DEFAULT '{}',
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    consumed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_openid
    ON pending_actions(openid, consumed_at, expires_at);

CREATE TABLE IF NOT EXISTS sync_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    openid       TEXT NOT NULL,
    activity_id  TEXT,
    action       TEXT NOT NULL,
    result       TEXT NOT NULL,
    error        TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_logs_openid
    ON sync_logs(openid, created_at);

CREATE TABLE IF NOT EXISTS user_counters (
    openid          TEXT PRIMARY KEY,
    next_short_no   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kf_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """轻量迁移：给已有数据库补列，不影响新库。"""
    message_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    }
    if "result_text" not in message_columns:
        conn.execute("ALTER TABLE messages ADD COLUMN result_text TEXT")

    pref_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(user_prefs)").fetchall()
    }
    if "list_offset" not in pref_columns:
        conn.execute(
            "ALTER TABLE user_prefs ADD COLUMN list_offset INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn
