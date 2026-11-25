import json
from datetime import datetime, timedelta

import pytest

from app.calendar.sync import sync_openid
from app.commands.handlers import handle_text
from app.commands.render import render_activity_card
from app.config import Settings
from app.parsing.time_norm import TZ
from app.storage.db import init_db
from app.storage.repo_activities import get_activity

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=TZ)
OWNER = "owner-openid"
AUDIENCE = "audience-openid"


class FakeCalDAV:
    def __init__(self):
        self.puts = []
        self.deletes = []

    def put_event(self, uid, ics, etag=None):
        self.puts.append((uid, ics, etag))
        return '"etag-1"'

    def delete_event(self, uid):
        self.deletes.append(uid)
        return True

    def event_href(self, uid):
        return f"/radicale/sdg/calendar/{uid}.ics"


@pytest.fixture
def env(tmp_path):
    conn = init_db(tmp_path / "demo.sqlite3")
    settings = Settings(
        db_path=str(tmp_path / "demo.sqlite3"),
        caldav_username="sdg",
        caldav_password="secret",
        public_base_url="https://example.com",
        worker_enabled=False,
        sync_scheduler_enabled=False,
        demo_mode=True,
        caldav_sync_openids=OWNER,
    )
    yield conn, settings
    conn.close()


def add_activity(conn, openid, short_no=1, sync_status="pending"):
    conn.execute(
        """
        INSERT INTO activities (
            id, openid, short_no, title, start_at, end_at, all_day,
            source_type, confidence, lifecycle, sync_status, calendar_uid,
            sequence, remind_offsets, remind_at, created_at, updated_at
        ) VALUES (?, ?, ?, '观众活动', '2026-11-27T19:00:00+08:00',
                  '2026-11-27T21:00:00+08:00', 0, 'text', ?, 'active', ?, ?,
                  0, '[-30, 0]', '09:00', ?, ?)
        """,
        (
            f"id-{openid}-{short_no}",
            openid,
            short_no,
            json.dumps({"start_at": 0.95, "title": 0.8}),
            sync_status,
            f"uid-{openid}-{short_no}@test",
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    conn.commit()


def test_audience_sync_is_skipped(env):
    conn, settings = env
    add_activity(conn, AUDIENCE)
    fake = FakeCalDAV()

    counts = sync_openid(conn, AUDIENCE, settings, client=fake, now=NOW)
    assert counts.get("skipped") is True
    assert fake.puts == []
    row = get_activity(conn, AUDIENCE, 1)
    assert row["sync_status"] == "pending"


def test_owner_sync_still_works(env):
    conn, settings = env
    add_activity(conn, OWNER)
    fake = FakeCalDAV()

    counts = sync_openid(conn, OWNER, settings, client=fake, now=NOW)
    assert counts["created"] == 1
    assert len(fake.puts) == 1
    assert get_activity(conn, OWNER, 1)["sync_status"] == "synced"


def test_audience_sync_command_explains_demo_mode(env):
    conn, settings = env
    reply = handle_text(conn, AUDIENCE, "同步", settings, NOW)
    assert "演示模式" in reply
    assert "日历同步仅对演示账号开放" in reply


def test_audience_config_is_demo_not_davx5(env):
    conn, settings = env
    reply = handle_text(conn, AUDIENCE, "配置", settings, NOW)
    assert "现场演示模式" in reply
    assert "DAVx5" not in reply


def test_owner_config_has_davx5_and_done_hint(env):
    conn, settings = env
    reply = handle_text(conn, OWNER, "配置", settings, NOW)
    assert "DAVx5" in reply
    assert "配置完成" in reply


def test_audience_list_has_demo_note(env):
    conn, settings = env
    add_activity(conn, AUDIENCE)
    reply = handle_text(conn, AUDIENCE, "列表", settings, NOW)
    assert "演示模式" in reply
    assert "不写入系统日历" in reply


def test_audience_delete_does_not_touch_calendar(env):
    conn, settings = env
    add_activity(conn, AUDIENCE)
    confirm = handle_text(conn, AUDIENCE, "删 1", settings, NOW)
    assert "演示模式" in confirm

    done = handle_text(conn, AUDIENCE, "1", settings, NOW)
    assert "已删除 #1" in done
    row = get_activity(conn, AUDIENCE, 1)
    assert row["lifecycle"] == "deleted"


def test_audience_card_has_demo_status(env):
    conn, settings = env
    add_activity(conn, AUDIENCE)
    activity = get_activity(conn, AUDIENCE, 1)
    card = render_activity_card(
        activity, [], settings, calendar_enabled=False
    )
    assert "演示模式" in card
    assert "不写入系统日历" in card


def test_owner_config_done_creates_two_minute_test_event(env, monkeypatch):
    conn, settings = env
    monkeypatch.setattr(
        "app.calendar.sync.sync_openid",
        lambda *args, **kwargs: {
            "created": 1,
            "updated": 0,
            "deleted": 0,
            "failed": 0,
            "failed_ids": [],
        },
    )

    reply = handle_text(conn, OWNER, "配置完成", settings, NOW)
    assert "测试事件" in reply
    assert "2 分钟后" in reply

    row = conn.execute(
        "SELECT * FROM activities WHERE openid = ?", (OWNER,)
    ).fetchone()
    assert row["title"] == "系统日历测试"
    assert row["start_at"] == (NOW + timedelta(minutes=2)).isoformat()


def test_audience_config_done_is_demo(env):
    conn, settings = env
    reply = handle_text(conn, AUDIENCE, "配置完成", settings, NOW)
    assert "演示模式" in reply
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
