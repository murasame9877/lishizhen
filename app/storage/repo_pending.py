"""多轮确认态：删除确认、低置信时间确认。

只在存在未过期确认态时消费 1/0/2，避免吞掉普通消息。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from app.parsing.time_norm import TZ, ensure_aware

__all__ = ["create_pending", "get_pending", "consume_pending"]


def create_pending(
    conn: sqlite3.Connection,
    openid: str,
    kind: str,
    payload: dict,
    *,
    now: datetime | None = None,
    ttl_minutes: int = 10,
) -> int:
    now = ensure_aware(now or datetime.now(TZ))
    expires_at = now + timedelta(minutes=ttl_minutes)
    cursor = conn.execute(
        """
        INSERT INTO pending_actions
            (openid, kind, payload, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            openid,
            kind,
            json.dumps(payload, ensure_ascii=False),
            expires_at.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_pending(
    conn: sqlite3.Connection,
    openid: str,
    *,
    now: datetime | None = None,
) -> dict | None:
    now = ensure_aware(now or datetime.now(TZ))
    row = conn.execute(
        """
        SELECT * FROM pending_actions
        WHERE openid = ? AND consumed_at IS NULL AND expires_at > ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (openid, now.isoformat()),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        result["payload"] = json.loads(result.get("payload") or "{}")
    except ValueError:
        result["payload"] = {}
    return result


def consume_pending(
    conn: sqlite3.Connection,
    pending_id: int,
    *,
    now: datetime | None = None,
) -> None:
    now = ensure_aware(now or datetime.now(TZ))
    conn.execute(
        "UPDATE pending_actions SET consumed_at = ? WHERE id = ?",
        (now.isoformat(), pending_id),
    )
    conn.commit()
