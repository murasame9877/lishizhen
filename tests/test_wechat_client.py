import asyncio
import json

import httpx

from app.config import Settings
from app.wechat.client import WeChatClient


def test_access_token_is_cached_and_text_is_sent():
    calls = {"token": 0, "send": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cgi-bin/token"):
            calls["token"] += 1
            return httpx.Response(
                200, json={"access_token": "tok-1", "expires_in": 7200}
            )
        if request.url.path.endswith("/cgi-bin/message/custom/send"):
            calls["send"] += 1
            body = json.loads(request.content)
            assert body["touser"] == "oUser1"
            assert body["msgtype"] == "text"
            assert body["text"]["content"] == "hello"
            assert request.url.params["access_token"] == "tok-1"
            return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        return httpx.Response(404)

    settings = Settings(
        wechat_appid="wx-test",
        wechat_appsecret="secret",
        worker_enabled=False,
        demo_mode=False,
    )
    client = WeChatClient(settings, transport=httpx.MockTransport(handler))

    async def run():
        await client.send_text("oUser1", "hello")
        await client.send_text("oUser1", "hello")

    asyncio.run(run())
    assert calls == {"token": 1, "send": 2}


def test_api_error_is_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cgi-bin/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(200, json={"errcode": 48001, "errmsg": "api unauthorized"})

    settings = Settings(
        wechat_appid="wx-test",
        wechat_appsecret="secret",
        worker_enabled=False,
        demo_mode=False,
    )
    client = WeChatClient(settings, transport=httpx.MockTransport(handler))

    try:
        asyncio.run(client.send_text("oUser1", "hello"))
    except Exception as exc:
        assert "48001" in str(exc)
    else:
        raise AssertionError("expected WeChatAPIError")
