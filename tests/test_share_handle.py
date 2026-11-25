import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.parsing.article import Article

TOKEN = "share-token"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "handle.sqlite3"),
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


def test_handle_text_command(client):
    test_client, app = client
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"text": "列表"},
    )
    assert response.status_code == 200
    assert "还没有记录" in response.json()["reply"]


def test_handle_text_activity(client):
    test_client, app = client
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"text": "周五晚7点 大礼堂 新生舞会"},
    )
    assert response.status_code == 200
    assert "已记录 #1" in response.json()["reply"]
    activity = app.state.db.execute("SELECT * FROM activities").fetchone()
    assert activity["title"] == "新生舞会"
    assert activity["source_type"] == "text"


def test_handle_url_creates_link_activity(client, monkeypatch):
    test_client, app = client
    article = Article(
        title="讲座B",
        text="活动时间：11月27日 20:00-22:00\n活动地点：六教",
        url="https://mp.weixin.qq.com/s/abc",
    )
    monkeypatch.setattr(
        "app.share_api.fetch_article", lambda *args, **kwargs: article
    )
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"url": "https://mp.weixin.qq.com/s/abc"},
    )
    assert response.status_code == 200
    assert "已记录 #1" in response.json()["reply"]
    activity = app.state.db.execute("SELECT * FROM activities").fetchone()
    assert activity["source_type"] == "link"
    assert activity["source_url"] == "https://mp.weixin.qq.com/s/abc"


def test_handle_rejects_bad_token(client):
    test_client, _ = client
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": "bad"},
        json={"text": "列表"},
    )
    assert response.status_code == 403
