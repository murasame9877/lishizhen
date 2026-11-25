"""Radicale CalDAV 客户端：PUT / DELETE / HEAD。

本机同步走 127.0.0.1，避免绕公网隧道；手机端仍用公网地址。
"""

from __future__ import annotations

import httpx

from app.config import Settings

__all__ = ["CalDAVError", "CalDAVClient"]


class CalDAVError(RuntimeError):
    pass


class CalDAVClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        base = settings.caldav_internal_url.rstrip("/")
        self.collection = f"{base}/{settings.caldav_username}/calendar/"
        self._auth = (settings.caldav_username, settings.caldav_password)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self._settings.caldav_timeout,
            transport=self._transport,
        )

    def event_url(self, uid: str) -> str:
        return f"{self.collection}{uid}.ics"

    def event_href(self, uid: str) -> str:
        prefix = self._settings.radicale_prefix.rstrip("/")
        return f"{prefix}/{self._settings.caldav_username}/calendar/{uid}.ics"

    def get_etag(self, uid: str) -> str | None:
        with self._client() as client:
            response = client.head(self.event_url(uid), auth=self._auth)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CalDAVError(
                f"HEAD {response.status_code}: {response.text[:200]}"
            )
        return response.headers.get("ETag")

    def put_event(
        self,
        uid: str,
        ics: str,
        etag: str | None = None,
    ) -> str | None:
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            headers["If-Match"] = etag

        with self._client() as client:
            response = client.put(
                self.event_url(uid),
                content=ics.encode("utf-8"),
                headers=headers,
                auth=self._auth,
            )

        if response.status_code in (200, 201, 204):
            return response.headers.get("ETag") or self.get_etag(uid)

        if response.status_code == 412 and etag:
            fresh_etag = self.get_etag(uid)
            return self.put_event(uid, ics, fresh_etag)

        if response.status_code in (404, 409):
            raise CalDAVError(
                "日历集合不存在（404/409）。请先创建 Radicale 日历集合。"
            )
        raise CalDAVError(
            f"PUT {response.status_code}: {response.text[:200]}"
        )

    def delete_event(self, uid: str) -> bool:
        with self._client() as client:
            response = client.delete(self.event_url(uid), auth=self._auth)
        # 404/410：远端本来就没有，视为删除成功（PRD FR-25 AC4）
        if response.status_code in (200, 204, 404, 410):
            return True
        raise CalDAVError(
            f"DELETE {response.status_code}: {response.text[:200]}"
        )
