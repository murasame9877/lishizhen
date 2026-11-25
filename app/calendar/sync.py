"""同步状态机：pending / update_pending / delete_pending → synced / failed。"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime

from app.calendar.caldav import CalDAVClient
from app.calendar.ics import build_event_ics
from app.config import Settings, is_calendar_enabled
from app.parsing.time_norm import TZ, ensure_aware
from app.storage.db import init_db
from app.storage.repo_activities import get_pending_sync

logger = logging.getLogger(__name__)

__all__ = ["sync_openid", "sync_all_users", "build_activity_ics"]


def _retry(fn, attempts: int = 3):
    last: Exception | None = None
    for index in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if index < attempts - 1:
                time.sleep(0.2 * (2**index))
    assert last is not None
    raise last


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def build_activity_ics(activity: dict, settings: Settings) -> str:
    start = _dt(activity.get("start_at"))
    if start is None:
        raise ValueError("activity has no start_at")

    end = _dt(activity.get("end_at"))
    offsets = json.loads(activity.get("remind_offsets") or "[-30, 0]")
    description_parts = []
    if activity.get("organizer"):
        description_parts.append(f"主办：{activity['organizer']}")
    if activity.get("notes"):
        description_parts.append(str(activity["notes"]))

    return build_event_ics(
        uid=activity["calendar_uid"],
        title=activity.get("title") or "未命名活动",
        start=start,
        end=end,
        all_day=bool(activity.get("all_day")),
        location=activity.get("location"),
        description="\n".join(description_parts) or None,
        url=activity.get("source_url"),
        sequence=int(activity.get("sequence") or 0),
        created_at=_dt(activity.get("created_at")),
        updated_at=_dt(activity.get("updated_at")),
        remind_offsets=offsets,
        all_day_remind_at=activity.get("remind_at") or "09:00",
    )


def sync_openid(
    conn: sqlite3.Connection,
    openid: str,
    settings: Settings,
    *,
    client: CalDAVClient | None = None,
    now: datetime | None = None,
) -> dict:
    now = ensure_aware(now or datetime.now(TZ))
    if not is_calendar_enabled(settings, openid):
        return {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "failed": 0,
            "failed_ids": [],
            "skipped": True,
        }

    client = client or CalDAVClient(settings)
    counts = {
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "failed": 0,
        "failed_ids": [],
    }

    for activity in get_pending_sync(conn, openid):
        short_no = int(activity["short_no"])
        try:
            if activity["sync_status"] == "delete_pending":
                uid = activity["calendar_uid"]
                _retry(lambda: client.delete_event(uid))
                conn.execute(
                    """
                    UPDATE activities
                    SET sync_status = 'deleted', calendar_etag = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), activity["id"]),
                )
                counts["deleted"] += 1
            else:
                ics = build_activity_ics(activity, settings)
                uid = activity["calendar_uid"]
                etag = activity.get("calendar_etag")
                new_etag = _retry(
                    lambda: client.put_event(uid, ics, etag=etag)
                )
                conn.execute(
                    """
                    UPDATE activities
                    SET sync_status = 'synced', calendar_etag = ?,
                        calendar_href = ?, sequence = sequence + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_etag,
                        client.event_href(uid),
                        now.isoformat(),
                        activity["id"],
                    ),
                )
                if activity["sync_status"] == "update_pending":
                    counts["updated"] += 1
                else:
                    counts["created"] += 1
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("同步失败 #%s", short_no)
            counts["failed"] += 1
            counts["failed_ids"].append(short_no)
            conn.execute(
                "UPDATE activities SET sync_status = 'failed', updated_at = ? WHERE id = ?",
                (now.isoformat(), activity["id"]),
            )
            conn.execute(
                """
                INSERT INTO sync_logs
                    (openid, activity_id, action, result, error, created_at)
                VALUES (?, ?, ?, 'failed', ?, ?)
                """,
                (
                    openid,
                    activity["id"],
                    activity["sync_status"],
                    str(exc)[:500],
                    now.isoformat(),
                ),
            )
            conn.commit()

    return counts


def sync_all_users(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    try:
        openids = [
            row[0]
            for row in conn.execute(
                """
                SELECT DISTINCT openid FROM activities
                WHERE sync_status IN ('pending', 'update_pending', 'delete_pending')
                """
            ).fetchall()
        ]
        if settings.demo_mode:
            allowed = settings.caldav_sync_openid_set
            openids = [openid for openid in openids if openid in allowed]
        for openid in openids:
            prefs = conn.execute(
                "SELECT auto_sync_enabled FROM user_prefs WHERE openid = ?",
                (openid,),
            ).fetchone()
            if prefs is not None and not prefs[0]:
                continue
            try:
                sync_openid(conn, openid, settings)
            except Exception:  # noqa: BLE001
                logger.exception("定时同步用户失败 openid=%s", openid)
    finally:
        conn.close()
