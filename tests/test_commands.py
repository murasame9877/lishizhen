import json
from datetime import datetime, timedelta

import pytest

from app.commands.handlers import handle_text
from app.config import Settings
from app.parsing.time_norm import TZ
from app.storage.db import init_db
from app.storage.repo_pending import create_pending

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=TZ)


@pytest.fixture
def env(tmp_path):
    conn = init_db(tmp_path / "commands.sqlite3")
    settings = Settings(
        db_path=str(tmp_path / "commands.sqlite3"),
        caldav_username="sdg",
        caldav_password="secret",
        public_base_url="https://example.com",
        worker_enabled=False,
        sync_scheduler_enabled=False,
        demo_mode=False,
    )
    yield conn, settings
    conn.close()


def add_activity(
    conn,
    short_no: int,
    title: str,
    start: str | None,
    end: str | None = None,
    *,
    all_day: int = 0,
    location: str | None = None,
    sync_status: str = "pending",
):
    conn.execute(
        """
        INSERT INTO activities (
            id, openid, short_no, title, start_at, end_at, all_day, location,
            source_type, confidence, lifecycle, sync_status, calendar_uid,
            sequence, remind_offsets, remind_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'text', ?, 'active', ?, ?, 0,
                  '[-30, 0]', '09:00', ?, ?)
        """,
        (
            f"id-{short_no}",
            "o1",
            short_no,
            title,
            start,
            end,
            all_day,
            location,
            json.dumps({"start_at": 0.95, "title": 0.8}),
            sync_status,
            f"uid-{short_no}@test",
            "2026-11-22T10:00:00+08:00",
            "2026-11-22T10:00:00+08:00",
        ),
    )
    conn.commit()


def test_list_shows_conflicts(env):
    conn, settings = env
    add_activity(conn, 1, "讲座A", "2026-11-27T19:00:00+08:00", "2026-11-27T21:00:00+08:00", location="大礼堂")
    add_activity(conn, 2, "讲座B", "2026-11-27T20:00:00+08:00", "2026-11-27T22:00:00+08:00", location="六教")

    reply = handle_text(conn, "o1", "列表", settings, NOW)
    assert "未来日程" in reply
    assert "共 2 条" in reply
    assert "#1" in reply and "#2" in reply
    assert "⚠️#2" in reply
    assert "📍大礼堂" in reply


def test_list_pagination(env):
    conn, settings = env
    for index in range(1, 9):
        day = (datetime(2026, 11, 25, tzinfo=TZ) + timedelta(days=index)).date()
        add_activity(
            conn,
            index,
            f"活动{index}",
            f"{day.isoformat()}T19:00:00+08:00",
            f"{day.isoformat()}T21:00:00+08:00",
        )

    first = handle_text(conn, "o1", "列表", settings, NOW)
    assert "共 8 条" in first
    assert "更多 查看剩余 2 条" in first
    assert "#6" in first and "#7" not in first

    second = handle_text(conn, "o1", "更多", settings, NOW)
    assert "#7" in second and "#8" in second

    third = handle_text(conn, "o1", "更多", settings, NOW)
    assert "没有更多日程了" in third


def test_detail_and_not_found(env):
    conn, settings = env
    add_activity(conn, 1, "讲座A", "2026-11-27T19:00:00+08:00", "2026-11-27T21:00:00+08:00")
    add_activity(conn, 2, "讲座B", "2026-11-27T20:00:00+08:00", "2026-11-27T22:00:00+08:00")

    reply = handle_text(conn, "o1", "#2", settings, NOW)
    assert "#2 讲座B" in reply
    assert "冲突：#1" in reply
    assert "开始前 30 分钟、开始时" in reply

    assert "未找到 #99" in handle_text(conn, "o1", "#99", settings, NOW)


def test_edit_time_shifts_end_and_reports_diff(env):
    conn, settings = env
    add_activity(conn, 1, "讲座A", "2026-11-27T19:00:00+08:00", "2026-11-27T21:00:00+08:00")
    add_activity(conn, 2, "讲座B", "2026-11-27T20:00:00+08:00", "2026-11-27T22:00:00+08:00")

    reply = handle_text(conn, "o1", "改 2 时间 20:30", settings, NOW)
    assert "已更新 #2" in reply
    assert "20:00-22:00" in reply
    assert "20:30-22:30" in reply
    assert "冲突" in reply

    row = conn.execute("SELECT * FROM activities WHERE short_no=2").fetchone()
    assert row["start_at"] == "2026-11-27T20:30:00+08:00"
    assert row["end_at"] == "2026-11-27T22:30:00+08:00"
    assert row["sync_status"] == "pending"
    assert row["sequence"] == 1


def test_edit_title_and_invalid_time(env):
    conn, settings = env
    add_activity(conn, 1, "旧名称", "2026-11-27T19:00:00+08:00")

    reply = handle_text(conn, "o1", "改 1 名称 新名称", settings, NOW)
    assert "名称：旧名称 → 新名称" in reply
    assert "时间格式没看懂" in handle_text(conn, "o1", "改 1 时间 瞎写", settings, NOW)


def test_delete_requires_confirmation(env):
    conn, settings = env
    add_activity(conn, 1, "讲座A", "2026-11-27T19:00:00+08:00")

    confirm = handle_text(conn, "o1", "删 1", settings, NOW)
    assert "确认删除 #1" in confirm
    row = conn.execute("SELECT lifecycle FROM activities WHERE short_no=1").fetchone()
    assert row["lifecycle"] == "active"

    done = handle_text(conn, "o1", "1", settings, NOW)
    assert "已删除 #1" in done
    row = conn.execute("SELECT lifecycle, sync_status FROM activities WHERE short_no=1").fetchone()
    assert row["lifecycle"] == "deleted"


def test_delete_cancel(env):
    conn, settings = env
    add_activity(conn, 1, "讲座A", "2026-11-27T19:00:00+08:00")
    handle_text(conn, "o1", "删 1", settings, NOW)

    reply = handle_text(conn, "o1", "0", settings, NOW)
    assert "已取消" in reply
    row = conn.execute("SELECT lifecycle FROM activities WHERE short_no=1").fetchone()
    assert row["lifecycle"] == "active"


def test_conflict_filter_and_help(env):
    conn, settings = env
    add_activity(conn, 1, "A", "2026-11-27T19:00:00+08:00", "2026-11-27T21:00:00+08:00")
    add_activity(conn, 2, "B", "2026-11-27T20:00:00+08:00", "2026-11-27T22:00:00+08:00")

    reply = handle_text(conn, "o1", "冲突", settings, NOW)
    assert "冲突日程" in reply and "#1" in reply and "#2" in reply
    assert "【查看】" in handle_text(conn, "o1", "帮助", settings, NOW)
    assert "没看懂" in handle_text(conn, "o1", "随便说点", settings, NOW)


def test_low_confidence_confirm(env):
    conn, settings = env
    add_activity(conn, 3, "社团招新", "2026-11-28T00:00:00+08:00", "2026-11-29T00:00:00+08:00", all_day=1, sync_status="not_synced")
    create_pending(conn, "o1", "time_confirm", {"short_no": 3}, now=NOW)

    reply = handle_text(conn, "o1", "1", settings, NOW)
    assert "已确认 #3" in reply
    row = conn.execute("SELECT sync_status FROM activities WHERE short_no=3").fetchone()
    assert row["sync_status"] == "pending"


def test_config_contains_caldav_url(env):
    _, settings = env
    reply = handle_text(env[0], "o1", "配置", settings, NOW)
    assert "https://example.com/radicale/" in reply
    assert "DAVx5" in reply
