import asyncio

import pytest

from app.config import Settings
from app.parsing.article import Article
from app.storage.db import init_db
from app.wecom_kf import handle_kf_message


class FakeKF:
    def __init__(self):
        self.sent: list[tuple[str, str, str | None]] = []

    async def send_text(self, external_userid, content, open_kfid=None):
        self.sent.append((external_userid, content, open_kfid))
        return True


@pytest.fixture
def env(tmp_path):
    conn = init_db(tmp_path / "kf.sqlite3")
    settings = Settings(
        db_path=str(tmp_path / "kf.sqlite3"),
        wecom_kf_user_openid="oUser1",
        wecom_kf_id="kfc-test",
        worker_enabled=False,
        radicale_enabled=False,
        sync_scheduler_enabled=False,
        wechat_push_enabled=False,
    )
    yield conn, settings
    conn.close()


def kf_msg(msgtype: str, **kwargs):
    base = {
        "origin": 3,
        "external_userid": "kfuser1",
        "open_kfid": "kfc-test",
        "msgid": "m1",
        "msgtype": msgtype,
    }
    base.update(kwargs)
    return base


def run(conn, settings, client, msg):
    asyncio.run(handle_kf_message(conn, msg, settings, client))


def test_text_command_is_handled(env):
    conn, settings = env
    client = FakeKF()
    run(conn, settings, client, kf_msg("text", text={"content": "列表"}))

    assert len(client.sent) == 1
    assert "还没有记录" in client.sent[0][1]
    row = conn.execute("SELECT * FROM messages WHERE msg_id='kf:m1'").fetchone()
    assert row["status"] == "kf_handled"
    assert row["openid"] == "oUser1"


def test_text_activity_creates_card(env):
    conn, settings = env
    client = FakeKF()
    run(
        conn,
        settings,
        client,
        kf_msg("text", text={"content": "周五晚7点 大礼堂 新生舞会"}),
    )

    assert len(client.sent) == 1
    assert "已记录 #1" in client.sent[0][1]
    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["title"] == "新生舞会"
    assert activity["location"] == "大礼堂"


def test_link_message_creates_activity(env, monkeypatch):
    conn, settings = env
    client = FakeKF()
    article = Article(
        title="讲座B",
        text="活动时间：11月27日 20:00-22:00\n活动地点：六教",
        url="https://mp.weixin.qq.com/s/abc",
    )
    monkeypatch.setattr(
        "app.wecom_kf.fetch_article", lambda *args, **kwargs: article
    )

    run(
        conn,
        settings,
        client,
        kf_msg("link", link={"url": "https://mp.weixin.qq.com/s/abc"}),
    )

    assert len(client.sent) == 1
    assert "已记录 #1" in client.sent[0][1]
    activity = conn.execute("SELECT * FROM activities").fetchone()
    assert activity["source_type"] == "link"
    assert activity["source_url"] == "https://mp.weixin.qq.com/s/abc"


def test_duplicate_msgid_is_ignored(env):
    conn, settings = env
    client = FakeKF()
    msg = kf_msg("text", text={"content": "周五晚7点 大礼堂 新生舞会"})
    run(conn, settings, client, msg)
    run(conn, settings, client, msg)

    assert len(client.sent) == 1
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1


def test_servicer_origin_is_ignored(env):
    conn, settings = env
    client = FakeKF()
    run(
        conn,
        settings,
        client,
        kf_msg("text", origin=5, text={"content": "列表"}),
    )
    assert client.sent == []
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_image_is_deferred(env):
    conn, settings = env
    client = FakeKF()
    run(conn, settings, client, kf_msg("image", image={"media_id": "media-1"}))

    assert "图片解析正在接入中" in client.sent[0][1]
    row = conn.execute("SELECT * FROM messages WHERE msg_id='kf:m1'").fetchone()
    assert row["status"] == "kf_deferred"
