"""微信主动接口：access_token 缓存与客服消息（48 小时窗口内）。"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.config import Settings

__all__ = ["WeChatAPIError", "WeChatClient"]


class WeChatAPIError(RuntimeError):
    def __init__(self, errcode, errmsg):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeChat API error {errcode}: {errmsg}")


class WeChatClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=15, transport=self._transport)

    async def get_access_token(self, force: bool = False) -> str:
        if not self._settings.wechat_appid or not self._settings.wechat_appsecret:
            raise WeChatAPIError(None, "缺少 appID/appsecret")

        async with self._lock:
            now = time.monotonic()
            if not force and self._token and now < self._expires_at:
                return self._token

            async with self._client() as client:
                response = await client.get(
                    f"{self._settings.wechat_api_base}/cgi-bin/token",
                    params={
                        "grant_type": "client_credential",
                        "appid": self._settings.wechat_appid,
                        "secret": self._settings.wechat_appsecret,
                    },
                )
                data = response.json()

            token = data.get("access_token")
            if not token:
                raise WeChatAPIError(data.get("errcode"), data.get("errmsg"))

            self._token = token
            self._expires_at = now + int(data.get("expires_in", 7200)) - 120
            return token

    async def _send_text_once(
        self, token: str, openid: str, content: str
    ) -> dict:
        payload = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": content},
        }
        async with self._client() as client:
            response = await client.post(
                f"{self._settings.wechat_api_base}/cgi-bin/message/custom/send",
                params={"access_token": token},
                json=payload,
            )
            return response.json()

    async def send_text(self, openid: str, content: str) -> bool:
        token = await self.get_access_token()
        data = await self._send_text_once(token, openid, content)

        if data.get("errcode") in (40001, 42001):
            token = await self.get_access_token(force=True)
            data = await self._send_text_once(token, openid, content)

        errcode = data.get("errcode", 0)
        if errcode not in (0, None):
            raise WeChatAPIError(errcode, data.get("errmsg"))
        return True
