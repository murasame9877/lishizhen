import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "share-token"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "share.sqlite3"),
        share_ingest_token=TOKEN,
        share_user_openid="oUser1",
        radicale_enabled=False,
        worker_enabled=False,
        sync_scheduler_enabled=False,
        wechat_push_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, app


def test_share_ingest_creates_link_message(client):
    test_client, app = client
    response = test_client.post(
        "/share/ingest",
        headers={"X-Share-Token": TOKEN},
        json={"url": "https://mp.weixin.qq.com/s/abc123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["task_no"].startswith("A")

    row = app.state.db.execute("SELECT * FROM messages").fetchone()
    assert row["msg_type"] == "link"
    assert row["status"] == "parse_queued"
    assert row["openid"] == "oUser1"
    assert "https://mp.weixin.qq.com/s/abc123" in row["raw_xml"]


def test_share_ingest_accepts_text_with_url(client):
    test_client, app = client
    response = test_client.post(
        "/share/ingest",
        headers={"X-Share-Token": TOKEN},
        json={"text": "看看这个 https://mp.weixin.qq.com/s/xyz，周五晚7点"},
    )
    assert response.status_code == 200
    row = app.state.db.execute("SELECT * FROM messages").fetchone()
    assert "https://mp.weixin.qq.com/s/xyz" in row["raw_xml"]


def test_share_ingest_rejects_bad_token(client):
    test_client, _ = client
    response = test_client.post(
        "/share/ingest",
        headers={"X-Share-Token": "bad"},
        json={"url": "https://mp.weixin.qq.com/s/abc"},
    )
    assert response.status_code == 403


def test_share_ingest_rejects_non_wechat_url(client):
    test_client, _ = client
    response = test_client.post(
        "/share/ingest",
        headers={"X-Share-Token": TOKEN},
        json={"url": "https://example.com/a"},
    )
    assert response.status_code == 400
