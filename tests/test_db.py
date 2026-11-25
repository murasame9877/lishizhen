import sqlite3

import pytest

from app.storage.db import init_db


def test_schema_creates_tables(tmp_path):
    conn = init_db(tmp_path / "test.sqlite3")
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "activities",
        "user_prefs",
        "messages",
        "pending_actions",
        "sync_logs",
        "user_counters",
    } <= names
    conn.close()


def test_short_no_is_unique_per_openid(tmp_path):
    conn = init_db(tmp_path / "test.sqlite3")
    now = "2026-11-22T10:00:00+08:00"
    row = (
        "id-1", "oUser1", 1, "活动", "link", "{}", "pending", now, now,
    )
    conn.execute(
        """
        INSERT INTO activities
            (id, openid, short_no, title, source_type, confidence,
             sync_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO activities
                (id, openid, short_no, title, source_type, confidence,
                 sync_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("id-2", "oUser1", 1, "另一个", "text", "{}", "pending", now, now),
        )
    conn.close()


def test_msg_id_is_idempotent(tmp_path):
    conn = init_db(tmp_path / "test.sqlite3")
    now = "2026-11-22T10:00:00+08:00"
    conn.execute(
        "INSERT INTO messages (msg_id, openid, msg_type, created_at) VALUES (?, ?, ?, ?)",
        ("msg-1", "oUser1", "text", now),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO messages (msg_id, openid, msg_type, created_at) VALUES (?, ?, ?, ?)",
            ("msg-1", "oUser1", "text", now),
        )
    conn.close()
