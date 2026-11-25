"""活动记录读写：编号分配、插入、冲突查询。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime

from app.config import Settings
from app.parsing.conflict import Span, find_conflicts
from app.parsing.extract_rules import ParsedActivity
from app.parsing.time_norm import TZ, ensure_aware

__all__ = [
    "next_short_no",
    "ensure_user_prefs",
    "insert_activity",
    "get_activity",
    "get_conflict_ids",
    "list_future",
    "count_future",
    "list_all_active",
    "update_activity",
    "soft_delete",
    "set_sync_status",
    "get_pending_sync",
    "get_by_short_nos",
]


def _iso(value: datetime | None) -> str | None:
    return ensure_aware(value).isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def next_short_no(conn: sqlite3.Connection, openid: str) -> int:
    """每个用户自增、删除不复用的编号。"""
    row = conn.execute(
        """
        INSERT INTO user_counters(openid, next_short_no) VALUES (?, 2)
        ON CONFLICT(openid) DO UPDATE SET next_short_no = next_short_no + 1
        RETURNING next_short_no - 1
        """,
        (openid,),
    ).fetchone()
    return int(row[0])


def ensure_user_prefs(
    conn: sqlite3.Connection, openid: str, now: datetime
) -> sqlite3.Row:
    conn.execute(
        "INSERT OR IGNORE INTO user_prefs(openid, updated_at) VALUES (?, ?)",
        (openid, now.isoformat()),
    )
    return conn.execute(
        "SELECT * FROM user_prefs WHERE openid = ?", (openid,)
    ).fetchone()


def insert_activity(
    conn: sqlite3.Connection,
    openid: str,
    parsed: ParsedActivity,
    settings: Settings,
    *,
    source_type: str = "text",
    source_url: str | None = None,
    source_raw: str | None = None,
    now: datetime | None = None,
) -> dict:
    now = ensure_aware(now or datetime.now(TZ))
    prefs = ensure_user_prefs(conn, openid, now)

    short_no = next_short_no(conn, openid)
    activity_id = uuid.uuid4().hex
    calendar_uid = f"sdg-{uuid.uuid4().hex}@sdg.local"

    if parsed.start_at is None:
        sync_status = "not_synced"
    elif parsed.confidence.get("start_at", 0.0) >= settings.confidence_threshold:
        sync_status = "pending"
    else:
        sync_status = "not_synced"

    conn.execute(
        """
        INSERT INTO activities (
            id, openid, short_no, title, start_at, end_at, all_day,
            location, deadline_at, organizer, notes,
            source_type, source_url, source_raw, confidence,
            lifecycle, sync_status, calendar_uid,
            sequence, duplicate_of, remind_offsets, remind_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            openid,
            short_no,
            parsed.title,
            _iso(parsed.start_at),
            _iso(parsed.end_at),
            1 if parsed.all_day else 0,
            parsed.location,
            _iso(parsed.deadline_at),
            parsed.organizer,
            parsed.notes,
            source_type,
            source_url,
            source_raw,
            json.dumps(parsed.confidence, ensure_ascii=False),
            "active",
            sync_status,
            calendar_uid,
            0,
            None,
            prefs["default_remind_offsets"],
            prefs["all_day_remind_time"],
            now.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    return get_activity(conn, openid, short_no)


def get_activity(
    conn: sqlite3.Connection, openid: str, short_no: int
) -> dict:
    row = conn.execute(
        "SELECT * FROM activities WHERE openid = ? AND short_no = ?",
        (openid, short_no),
    ).fetchone()
    if row is None:
        raise KeyError(f"activity not found: {openid}#{short_no}")
    return dict(row)


def get_conflict_ids(
    conn: sqlite3.Connection, openid: str, activity: dict
) -> list[int]:
    rows = conn.execute(
        """
        SELECT short_no, start_at, end_at, all_day
        FROM activities
        WHERE openid = ? AND lifecycle = 'active' AND start_at IS NOT NULL
        """,
        (openid,),
    ).fetchall()
    spans: list[Span] = []
    for row in rows:
        start = _parse_dt(row["start_at"])
        if start is None:
            continue
        spans.append(
            Span(
                id=int(row["short_no"]),
                start=start,
                end=_parse_dt(row["end_at"]),
                all_day=bool(row["all_day"]),
            )
        )
    return find_conflicts(spans).get(int(activity["short_no"]), [])


def list_future(
    conn: sqlite3.Connection,
    openid: str,
    start: datetime,
    end: datetime,
    *,
    limit: int = 6,
    offset: int = 0,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM activities
        WHERE openid = ? AND lifecycle = 'active'
          AND (start_at IS NULL OR (start_at >= ? AND start_at < ?))
        ORDER BY (start_at IS NULL), start_at, short_no
        LIMIT ? OFFSET ?
        """,
        (openid, start.isoformat(), end.isoformat(), limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def count_future(
    conn: sqlite3.Connection,
    openid: str,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*) FROM activities
            WHERE openid = ? AND lifecycle = 'active'
              AND (start_at IS NULL OR (start_at >= ? AND start_at < ?))
            """,
            (openid, start.isoformat(), end.isoformat()),
        ).fetchone()[0]
    )


def list_all_active(conn: sqlite3.Connection, openid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM activities
        WHERE openid = ? AND lifecycle = 'active'
        ORDER BY (start_at IS NULL), start_at, short_no
        """,
        (openid,),
    ).fetchall()
    return [dict(row) for row in rows]


_ALLOWED_UPDATE_FIELDS = {
    "title",
    "start_at",
    "end_at",
    "all_day",
    "location",
    "deadline_at",
    "organizer",
    "notes",
    "remind_offsets",
    "remind_at",
}


def update_activity(
    conn: sqlite3.Connection,
    openid: str,
    short_no: int,
    fields: dict,
    *,
    sync_status: str | None = None,
    now: datetime | None = None,
) -> dict:
    now = ensure_aware(now or datetime.now(TZ))
    assignments: list[str] = []
    values: list = []

    for key, value in fields.items():
        if key not in _ALLOWED_UPDATE_FIELDS:
            raise ValueError(f"field not allowed: {key}")
        assignments.append(f"{key} = ?")
        values.append(value)

    if sync_status is not None:
        assignments.append("sync_status = ?")
        values.append(sync_status)

    assignments.append("sequence = sequence + 1")
    assignments.append("updated_at = ?")
    values.append(now.isoformat())
    values.extend([openid, short_no])

    conn.execute(
        f"UPDATE activities SET {', '.join(assignments)} "
        "WHERE openid = ? AND short_no = ?",
        values,
    )
    conn.commit()
    return get_activity(conn, openid, short_no)


def soft_delete(
    conn: sqlite3.Connection,
    openid: str,
    short_no: int,
    *,
    now: datetime | None = None,
) -> dict:
    now = ensure_aware(now or datetime.now(TZ))
    activity = get_activity(conn, openid, short_no)
    was_synced = (
        activity.get("calendar_uid")
        and activity.get("sync_status")
        in {"synced", "update_pending", "failed", "external_removed"}
    )
    next_status = "delete_pending" if was_synced else "deleted"

    conn.execute(
        """
        UPDATE activities
        SET lifecycle = 'deleted', deleted_at = ?, sync_status = ?,
            sequence = sequence + 1, updated_at = ?
        WHERE openid = ? AND short_no = ?
        """,
        (now.isoformat(), next_status, now.isoformat(), openid, short_no),
    )
    conn.commit()
    return get_activity(conn, openid, short_no)


def set_sync_status(
    conn: sqlite3.Connection,
    openid: str,
    short_no: int,
    status: str,
    *,
    etag: str | None = None,
    href: str | None = None,
    now: datetime | None = None,
) -> None:
    now = ensure_aware(now or datetime.now(TZ))
    conn.execute(
        """
        UPDATE activities
        SET sync_status = ?, calendar_etag = ?, calendar_href = ?,
            updated_at = ?
        WHERE openid = ? AND short_no = ?
        """,
        (status, etag, href, now.isoformat(), openid, short_no),
    )
    conn.commit()


def get_pending_sync(conn: sqlite3.Connection, openid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM activities
        WHERE openid = ? AND sync_status IN ('pending', 'update_pending', 'delete_pending')
        ORDER BY short_no
        """,
        (openid,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_by_short_nos(
    conn: sqlite3.Connection, openid: str, short_nos: list[int]
) -> list[dict]:
    if not short_nos:
        return []
    placeholders = ",".join("?" for _ in short_nos)
    rows = conn.execute(
        f"SELECT * FROM activities WHERE openid = ? AND short_no IN ({placeholders})",
        [openid, *short_nos],
    ).fetchall()
    return [dict(row) for row in rows]
