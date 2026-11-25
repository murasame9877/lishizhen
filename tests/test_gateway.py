import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
APPID = "gh_test_account"


def sign(timestamp: str = "1700000000", nonce: str = "n1") -> str:
    raw = "".join(sorted([TOKEN, timestamp, nonce]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def text_xml(content: str, msg_id: str = "1001") -> str:
    return f"""<xml>
      <ToUserName><![CDATA[{APPID}]]></ToUserName>
      <FromUserName><![CDATA[oUser1]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[text]]></MsgType>
      <Content><![CDATA[{content}]]></Content>
      <MsgId>{msg_id}</MsgId>
    </xml>"""


def image_xml(msg_id: str = "2001") -> str:
    return f"""<xml>
      <ToUserName><![CDATA[{APPID}]]></ToUserName>
      <FromUserName><![CDATA[oUser1]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[image]]></MsgType>
      <PicUrl><![CDATA[https://example.com/p.jpg]]></PicUrl>
      <MediaId><![CDATA[media-1]]></MediaId>
      <MsgId>{msg_id}</MsgId>
    </xml>"""


def voice_xml(msg_id: str = "3001") -> str:
    return f"""<xml>
      <ToUserName><![CDATA[{APPID}]]></ToUserName>
      <FromUserName><![CDATA[oUser1]]></FromUserName>
      <CreateTime>1700000000</CreateTime>
      <MsgType><![CDATA[voice]]></MsgType>
      <MsgId>{msg_id}</MsgId>
    </xml>"""


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        wechat_token=TOKEN,
        wechat_appid=APPID,
        db_path=str(tmp_path / "test.sqlite3"),
        radicale_enabled=False,
        worker_enabled=False,
        wechat_push_enabled=False,
        sync_scheduler_enabled=False,
        demo_mode=False,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, app


def post(client, xml: str, signature: str | None = None):
    return client.post(
        "/wechat",
        params={
            "signature": signature if signature is not None else sign(),
            "timestamp": "1700000000",
            "nonce": "n1",
        },
        content=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
    )


def message_count(app) -> int:
    return app.state.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def test_echostr_verification(client):
    test_client, _ = client
    response = test_client.get(
        "/wechat",
        params={
            "signature": sign(),
            "timestamp": "1700000000",
            "nonce": "n1",
            "echostr": "hello-wechat",
        },
    )
    assert response.status_code == 200
    assert response.text == "hello-wechat"


def test_echostr_rejects_bad_signature(client):
    test_client, _ = client
    response = test_client.get(
        "/wechat",
        params={
            "signature": "bad",
            "timestamp": "1700000000",
            "nonce": "n1",
            "echostr": "hello",
        },
    )
    assert response.status_code == 403


def test_text_activity_gets_receipt_and_is_queued(client):
    test_client, app = client
    response = post(test_client, text_xml("周五晚7点 大礼堂 新生舞会"))
    assert response.status_code == 200
    assert "已收到 #A" in response.text
    assert "30 秒" in response.text
    row = app.state.db.execute("SELECT * FROM messages WHERE msg_id='1001'").fetchone()
    assert row["status"] == "parse_queued"
    assert row["openid"] == "oUser1"
    assert message_count(app) == 1


def test_duplicate_msg_id_is_idempotent(client):
    test_client, app = client
    first = post(test_client, text_xml("周五晚7点 大礼堂 新生舞会", msg_id="dup-1"))
    second = post(test_client, text_xml("周五晚7点 大礼堂 新生舞会", msg_id="dup-1"))
    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert message_count(app) == 1


def test_command_is_not_queued_for_parsing(client):
    test_client, app = client
    response = post(test_client, text_xml("列表", msg_id="cmd-1"))
    assert response.status_code == 200
    row = app.state.db.execute(
        "SELECT status FROM messages WHERE msg_id='cmd-1'"
    ).fetchone()
    assert row["status"] == "command_handled"


def test_result_command_returns_latest_card(client):
    test_client, app = client
    app.state.db.execute(
        """
        INSERT INTO messages
            (msg_id, openid, msg_type, status, result_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("old-1", "oUser1", "text", "done", "CARD-CONTENT", "2026-11-22T10:00:00+08:00"),
    )
    app.state.db.commit()

    response = post(test_client, text_xml("结果", msg_id="res-1"))
    assert response.status_code == 200
    assert "CARD-CONTENT" in response.text
    row = app.state.db.execute(
        "SELECT status FROM messages WHERE msg_id='res-1'"
    ).fetchone()
    assert row["status"] == "command_handled"


def test_result_command_without_history(client):
    test_client, app = client
    response = post(test_client, text_xml("结果", msg_id="res-2"))
    assert "还没有可展示的解析结果" in response.text


def test_image_receipt_mentions_90_seconds(client):
    test_client, app = client
    response = post(test_client, image_xml())
    assert "90 秒" in response.text
    row = app.state.db.execute(
        "SELECT status FROM messages WHERE msg_id='2001'"
    ).fetchone()
    assert row["status"] == "parse_queued"


def test_unsupported_message_gets_guidance_without_task(client):
    test_client, app = client
    response = post(test_client, voice_xml())
    assert "暂不支持该格式" in response.text
    row = app.state.db.execute(
        "SELECT status FROM messages WHERE msg_id='3001'"
    ).fetchone()
    assert row["status"] == "unsupported"


def test_invalid_signature_is_rejected(client):
    test_client, app = client
    response = post(test_client, text_xml("列表"), signature="bad")
    assert response.status_code == 403
    assert message_count(app) == 0
