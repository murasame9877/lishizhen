import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.parsing.ocr import OCRUnavailable

TOKEN = "share-token"


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "image.sqlite3"),
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


def test_handle_image_creates_activity(client, monkeypatch):
    test_client, app = client
    monkeypatch.setattr(
        "app.share_api.ocr_image_bytes",
        lambda data, **kwargs: "活动时间：11月29日 19:00\n活动地点：大礼堂\n竞赛招募",
    )
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": base64.b64encode(_png_bytes()).decode()},
    )
    assert response.status_code == 200
    body = response.json()
    assert "已记录 #1" in body["reply"]
    assert "大礼堂" in body["reply"]
    activity = app.state.db.execute("SELECT * FROM activities").fetchone()
    assert activity["source_type"] == "image"
    assert activity["source_raw"]
    assert activity["source_raw"].endswith(".png")
    assert "image_base64" not in activity["source_raw"]


def test_handle_image_data_url(client, monkeypatch):
    test_client, app = client
    monkeypatch.setattr(
        "app.share_api.ocr_image_bytes",
        lambda data, **kwargs: "周五晚7点 大礼堂 新生舞会",
    )
    encoded = base64.b64encode(_png_bytes()).decode()
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": f"data:image/png;base64,{encoded}"},
    )
    assert response.status_code == 200
    assert "已记录 #1" in response.json()["reply"]


def test_handle_image_without_text(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(
        "app.share_api.ocr_image_bytes", lambda data, **kwargs: ""
    )
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": base64.b64encode(_png_bytes()).decode()},
    )
    assert response.status_code == 200
    assert "没识别到文字" in response.json()["reply"]


def test_handle_image_ocr_unavailable(client, monkeypatch):
    test_client, _ = client

    def boom(data, **kwargs):
        raise OCRUnavailable("not installed")

    monkeypatch.setattr("app.share_api.ocr_image_bytes", boom)
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": base64.b64encode(_png_bytes()).decode()},
    )
    assert response.status_code == 200
    assert "图片识别组件不可用" in response.json()["reply"]


def test_handle_image_bad_base64(client):
    test_client, _ = client
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": "not-base64!!"},
    )
    assert response.status_code == 400


def test_handle_image_too_large(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(
        "app.share_api.ocr_image_bytes", lambda data, **kwargs: "x"
    )
    big = base64.b64encode(b"\0" * (11 * 1024 * 1024)).decode()
    response = test_client.post(
        "/share/handle",
        headers={"X-Share-Token": TOKEN},
        json={"image_base64": big},
    )
    assert response.status_code == 413
