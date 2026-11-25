import asyncio
import sqlite3

import pytest

from app.config import Settings
from app.jobs.worker import process_one
from app.parsing.article import Article, ArticleFetchError
from app.storage.db import init_db


class FakeClient:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, openid: str, content: str) -> bool:
        self.sent.append((openid, content))
        return True


def message_xml(content: str, msg_type: str = "text") -> str:
    return f"""<xml>
      <ToUserName><![CDATA[gh_test]]></ToUserName>
      <FromUserName><![CDATA[oUser1]]></FromUserName>
      <MsgType><![CDATA[{msg_type}]]></MsgType>
      <Content><![CDATA[{content}]]></Content>
      <PicUrl><![CDATA[https://example.com/p.jpg]]></PicUrl>
      <MsgId>m1</MsgId>
    </xml>"""


@pytest.fixture
def env(tmp_path):
    db_path = tmp_path / "worker.sqlite3"
    conn = init_db(db_path)
    settings = Settings(
        db_path=str(db_path),
        worker_enabled=False,
        wechat_push_enabled=True,
        demo_mode=False,
    )
    yield conn, settings
    conn.close()


def add_message(conn, content: str, msg_id: str, msg_type: str = "text"):
    conn.execute(
        """
        INSERT INTO messages
            (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
        VALUES (?, ?, ?, ?, 'parse_queued', ?, ?)
        """,
        (
            msg_id,
            "oUser1",
            msg_type,
            message_xml(content, msg_type),
            "A0001",
            "2026-11-22T10:00:00+08:00",
        ),
    )
    conn.commit()


def test_text_message_becomes_card(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "周五晚7点 大礼堂 新生舞会", "m1")

    assert asyncio.run(process_one(settings, client)) is True
    assert len(client.sent) == 1
    openid, card = client.sent[0]
    assert openid == "oUser1"
    assert "已记录 #1" in card
    assert "新生舞会" in card
    assert "11-27 周五 19:00" in card
    assert "大礼堂" in card

    activity = conn.execute(
        "SELECT * FROM activities WHERE short_no = 1"
    ).fetchone()
    assert activity["title"] == "新生舞会"
    assert activity["sync_status"] == "pending"
    assert activity["calendar_uid"].startswith("sdg-")

    row = conn.execute("SELECT * FROM messages WHERE msg_id='m1'").fetchone()
    assert row["status"] == "done"
    assert row["result_text"] == card


def test_second_overlapping_activity_marks_conflict(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "11/27 19:00-21:00 大礼堂 讲座A", "m1")
    asyncio.run(process_one(settings, client))

    add_message(conn, "11/27 20:00-22:00 六教 讲座B", "m2")
    asyncio.run(process_one(settings, client))

    assert len(client.sent) == 2
    card = client.sent[1][1]
    assert "已记录 #2" in card
    assert "⚠️ 与 #1 时间冲突" in card

    count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert count == 2


def test_low_confidence_activity_is_not_sync_ready(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "周六 社团招新", "m1")
    asyncio.run(process_one(settings, client))

    card = client.sent[0][1]
    assert "时间不确定" in card
    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["sync_status"] == "not_synced"


def test_incomplete_activity_is_kept(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "有个讲座在六教", "m1")
    asyncio.run(process_one(settings, client))

    card = client.sent[0][1]
    assert "信息不完整" in card
    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["start_at"] is None


def test_pure_chat_creates_no_activity(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "你好", "m1")
    asyncio.run(process_one(settings, client))

    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
    row = conn.execute("SELECT * FROM messages WHERE msg_id='m1'").fetchone()
    assert row["status"] == "not_activity"
    assert "没识别到活动信息" in client.sent[0][1]


def test_non_text_is_deferred(env):
    conn, settings = env
    client = FakeClient()
    add_message(conn, "", "m1", msg_type="image")
    asyncio.run(process_one(settings, client))

    row = conn.execute("SELECT * FROM messages WHERE msg_id='m1'").fetchone()
    assert row["status"] == "deferred"
    assert "图片解析正在接入中" in client.sent[0][1]


def test_no_pending_message_returns_false(env):
    _, settings = env
    assert asyncio.run(process_one(settings, FakeClient())) is False


def test_failed_parse_is_marked_failed(env, monkeypatch):
    conn, settings = env
    add_message(conn, "周五晚7点 大礼堂 新生舞会", "m1")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.jobs.worker.insert_activity", boom)
    asyncio.run(process_one(settings, FakeClient()))

    row = conn.execute("SELECT * FROM messages WHERE msg_id='m1'").fetchone()
    assert row["status"] == "failed"


def link_xml(url: str, msg_id: str = "link-1") -> str:
    return f"""<xml>
      <ToUserName><![CDATA[gh_test]]></ToUserName>
      <FromUserName><![CDATA[oUser1]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[link]]></MsgType>
      <Title><![CDATA[新生舞会]]></Title>
      <Url><![CDATA[{url}]]></Url>
      <MsgId>{msg_id}</MsgId>
    </xml>"""


def add_raw_message(conn, raw_xml: str, msg_id: str, msg_type: str = "link"):
    conn.execute(
        """
        INSERT INTO messages
            (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
        VALUES (?, ?, ?, ?, 'parse_queued', ?, ?)
        """,
        (
            msg_id,
            "oUser1",
            msg_type,
            raw_xml,
            "A0002",
            "2026-11-22T10:00:00+08:00",
        ),
    )
    conn.commit()


def test_link_message_creates_activity(env, monkeypatch):
    conn, settings = env
    client = FakeClient()
    article = Article(
        title="新生舞会",
        text="活动时间：11月27日 19:00-21:00\n活动地点：大礼堂",
        url="https://mp.weixin.qq.com/s/abc",
    )
    monkeypatch.setattr(
        "app.jobs.worker.fetch_article", lambda *args, **kwargs: article
    )
    add_raw_message(conn, link_xml("https://mp.weixin.qq.com/s/abc"), "link-1")

    asyncio.run(process_one(settings, client))

    assert len(client.sent) == 1
    assert "已记录 #1" in client.sent[0][1]
    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["source_type"] == "link"
    assert activity["source_url"] == "https://mp.weixin.qq.com/s/abc"
    assert activity["location"] == "大礼堂"


def test_text_with_wechat_url_uses_article(env, monkeypatch):
    conn, settings = env
    client = FakeClient()
    article = Article(
        title="讲座B",
        text="活动时间：11月27日 20:00-22:00\n活动地点：六教",
        url="https://mp.weixin.qq.com/s/xyz",
    )
    monkeypatch.setattr(
        "app.jobs.worker.fetch_article", lambda *args, **kwargs: article
    )
    add_message(conn, "https://mp.weixin.qq.com/s/xyz", "m1")

    asyncio.run(process_one(settings, client))

    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["source_type"] == "link"
    assert activity["title"] == "讲座B"


def test_link_fetch_failure_is_reported(env, monkeypatch):
    conn, settings = env
    client = FakeClient()

    def boom(*args, **kwargs):
        raise ArticleFetchError("微信要求环境验证")

    monkeypatch.setattr("app.jobs.worker.fetch_article", boom)
    add_raw_message(conn, link_xml("https://mp.weixin.qq.com/s/bad"), "link-1")

    asyncio.run(process_one(settings, client))

    row = conn.execute("SELECT * FROM messages WHERE msg_id='link-1'").fetchone()
    assert row["status"] == "failed"
    assert "文章抓取失败" in client.sent[0][1]
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
