import json
from datetime import datetime

import pytest

from app.calendar.sync import sync_openid
from app.config import Settings
from app.parsing.time_norm import TZ
from app.storage.db import init_db

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=TZ)


class FakeCalDAV:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.puts: list[tuple[str, str, str | None]] = []
        self.deletes: list[str] = []

    def put_event(self, uid, ics, etag=None):
        if self.fail:
            raise RuntimeError("boom")
        self.puts.append((uid, ics, etag))
        return f'"etag-{len(self.puts)}"'

    def delete_event(self, uid):
        if self.fail:
            raise RuntimeError("boom")
        self.deletes.append(uid)
        return True

    def event_href(self, uid):
        return f"/radicale/sdg/calendar/{uid}.ics"


@pytest.fixture
def env(tmp_path):
    conn = init_db(tmp_path / "sync.sqlite3")
    settings = Settings(
        db_path=str(tmp_path / "sync.sqlite3"),
        caldav_internal_url="http://127.0.0.1:8000/radicale/",
        caldav_username="sdg",
        caldav_password="secret",
        worker_enabled=False,
        sync_scheduler_enabled=False,
        demo_mode=False,
    )
    yield conn, settings
    conn.close()


def add_activity(conn, short_no, sync_status="pending", all_day=0, start="2026-11-27T19:00:00+08:00", end="2026-11-27T21:00:00+08:00"):
    conn.execute(
        """
        INSERT INTO activities (
            id, openid, short_no, title, start_at, end_at, all_day, location,
            source_type, confidence, lifecycle, sync_status, calendar_uid,
            sequence, remind_offsets, remind_at, created_at, updated_at
        ) VALUES (?, 'o1', ?, ?, ?, ?, ?, '大礼堂', 'text', ?, 'active', ?, ?,
                  0, '[-30, 0]', '09:00', ?, ?)
        """,
        (
            f"id-{short_no}",
            short_no,
            f"活动{short_no}",
            start,
            end,
            all_day,
            json.dumps({"start_at": 0.95}),
            sync_status,
            f"uid-{short_no}@test",
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    conn.commit()


def test_sync_creates_and_is_idempotent(env):
    conn, settings = env
    add_activity(conn, 1)
    fake = FakeCalDAV()

    counts = sync_openid(conn, "o1", settings, client=fake, now=NOW)
    assert counts["created"] == 1
    assert len(fake.puts) == 1
    uid, ics, _ = fake.puts[0]
    assert uid == "uid-1@test"
    assert "BEGIN:VALARM" in ics
    assert "TZID:Asia/Shanghai" in ics

    row = conn.execute("SELECT * FROM activities WHERE short_no=1").fetchone()
    assert row["sync_status"] == "synced"
    assert row["calendar_etag"] == '"etag-1"'
    assert row["sequence"] == 1

    again = sync_openid(conn, "o1", settings, client=fake, now=NOW)
    assert again == {"created": 0, "updated": 0, "deleted": 0, "failed": 0, "failed_ids": []}
    assert len(fake.puts) == 1


def test_sync_update_uses_stable_uid_and_etag(env):
    conn, settings = env
    add_activity(conn, 1)
    fake = FakeCalDAV()
    sync_openid(conn, "o1", settings, client=fake, now=NOW)

    conn.execute("UPDATE activities SET sync_status='update_pending' WHERE short_no=1")
    conn.commit()

    counts = sync_openid(conn, "o1", settings, client=fake, now=NOW)
    assert counts["updated"] == 1
    assert len(fake.puts) == 2
    assert fake.puts[1][0] == "uid-1@test"
    assert fake.puts[1][2] == '"etag-1"'


def test_sync_delete_and_404_is_success(env):
    conn, settings = env
    add_activity(conn, 1)
    fake = FakeCalDAV()
    sync_openid(conn, "o1", settings, client=fake, now=NOW)

    conn.execute("UPDATE activities SET sync_status='delete_pending' WHERE short_no=1")
    conn.commit()
    counts = sync_openid(conn, "o1", settings, client=fake, now=NOW)
    assert counts["deleted"] == 1
    assert fake.deletes == ["uid-1@test"]

    row = conn.execute("SELECT sync_status FROM activities WHERE short_no=1").fetchone()
    assert row["sync_status"] == "deleted"


def test_sync_failure_marks_failed_and_logs(env):
    conn, settings = env
    add_activity(conn, 1)
    fake = FakeCalDAV(fail=True)

    counts = sync_openid(conn, "o1", settings, client=fake, now=NOW)
    assert counts["failed"] == 1
    assert counts["failed_ids"] == [1]

    row = conn.execute("SELECT sync_status FROM activities WHERE short_no=1").fetchone()
    assert row["sync_status"] == "failed"

    log = conn.execute("SELECT * FROM sync_logs").fetchone()
    assert log["result"] == "failed"
    assert "boom" in log["error"]


def test_all_day_ics_has_single_alarm(env):
    conn, settings = env
    add_activity(
        conn,
        1,
        all_day=1,
        start="2026-11-28T00:00:00+08:00",
        end="2026-11-29T00:00:00+08:00",
    )
    fake = FakeCalDAV()
    sync_openid(conn, "o1", settings, client=fake, now=NOW)

    ics = fake.puts[0][1]
    assert "DTSTART;VALUE=DATE:20261128" in ics
    assert ics.count("BEGIN:VALARM") == 1
    assert "TRIGGER;VALUE=DATE-TIME:20261128T010000Z" in ics
