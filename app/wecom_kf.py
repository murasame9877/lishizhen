"""企业微信「微信客服」接入。

官方聊天对象：用户在微信里打开客服链接，发送/转发消息；后端通过
`kf/sync_msg` 主动拉取（不需要公网回调），用 `kf/send_msg` 回复。
复用现有文章解析、指令、冲突、卡片与日历同步。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime

import httpx

from app.commands.handlers import handle_text
from app.commands.render import render_activity_card
from app.config import Settings, is_calendar_enabled
from app.parsing.article import (
    DEFAULT_USER_AGENT,
    ArticleFetchError,
    extract_article_activity,
    extract_wechat_url,
    fetch_article,
)
from app.parsing.extract_rules import extract_activity
from app.parsing.time_norm import TZ
from app.storage.db import init_db
from app.storage.repo_activities import get_conflict_ids, insert_activity
from app.storage.repo_pending import create_pending
from app.wechat.gateway import classify_text, make_task_no

logger = logging.getLogger(__name__)

_NOT_ACTIVITY = (
    "没识别到活动信息。直接发送活动文字、公众号文章链接或海报截图。\n"
    "例如：周五晚7点 大礼堂 新生舞会"
)
_IMAGE_REPLY = "图片解析正在接入中，请先把活动文字或文章链接发给我。"

__all__ = ["WeComKFClient", "handle_kf_message", "kf_loop"]


class WeComKFError(RuntimeError):
    pass


class WeComKFClient:
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
        self._base = "https://qyapi.weixin.qq.com"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=15, transport=self._transport)

    async def get_access_token(self, force: bool = False) -> str:
        if not self._settings.wecom_corp_id or not self._settings.wecom_kf_secret:
            raise WeComKFError("缺少企业 ID 或微信客服 Secret")

        async with self._lock:
            now = time.monotonic()
            if not force and self._token and now < self._expires_at:
                return self._token

            async with self._client() as client:
                response = await client.get(
                    f"{self._base}/cgi-bin/gettoken",
                    params={
                        "corpid": self._settings.wecom_corp_id,
                        "corpsecret": self._settings.wecom_kf_secret,
                    },
                )
                data = response.json()

            token = data.get("access_token")
            if not token:
                raise WeComKFError(
                    f"gettoken 失败 errcode={data.get('errcode')} "
                    f"errmsg={data.get('errmsg')}"
                )
            self._token = token
            self._expires_at = now + int(data.get("expires_in", 7200)) - 120
            return token

    async def sync_msg(self, cursor: str = "", token: str = "") -> dict:
        access = await self.get_access_token()
        payload = {
            "cursor": cursor or "",
            "token": token or "",
            "limit": 1000,
            "open_kfid": self._settings.wecom_kf_id,
        }
        async with self._client() as client:
            response = await client.post(
                f"{self._base}/cgi-bin/kf/sync_msg",
                params={"access_token": access},
                json=payload,
            )
            data = response.json()

        if data.get("errcode") in (40014, 42001, 42009):
            access = await self.get_access_token(force=True)
            async with self._client() as client:
                response = await client.post(
                    f"{self._base}/cgi-bin/kf/sync_msg",
                    params={"access_token": access},
                    json=payload,
                )
                data = response.json()

        if data.get("errcode") not in (0, None):
            raise WeComKFError(
                f"sync_msg 失败 errcode={data.get('errcode')} "
                f"errmsg={data.get('errmsg')}"
            )
        return data

    async def send_text(
        self,
        external_userid: str,
        content: str,
        open_kfid: str | None = None,
    ) -> bool:
        access = await self.get_access_token()
        payload = {
            "touser": external_userid,
            "open_kfid": open_kfid or self._settings.wecom_kf_id,
            "msgtype": "text",
            "text": {"content": content[:2000]},
        }
        async with self._client() as client:
            response = await client.post(
                f"{self._base}/cgi-bin/kf/send_msg",
                params={"access_token": access},
                json=payload,
            )
            data = response.json()

        if data.get("errcode") in (40014, 42001, 42009):
            access = await self.get_access_token(force=True)
            async with self._client() as client:
                response = await client.post(
                    f"{self._base}/cgi-bin/kf/send_msg",
                    params={"access_token": access},
                    json=payload,
                )
                data = response.json()

        if data.get("errcode") not in (0, None):
            raise WeComKFError(
                f"send_msg 失败 errcode={data.get('errcode')} "
                f"errmsg={data.get('errmsg')}"
            )
        return True


def _session_conn(settings: Settings):
    conn = init_db(settings.db_path)
    return conn


def _get_state(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM kf_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_state(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO kf_state(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, datetime.now(TZ).isoformat()),
    )
    conn.commit()


def _finish(conn, msg_id: str, reply: str, status: str = "kf_handled") -> None:
    conn.execute(
        "UPDATE messages SET status = ?, result_text = ? WHERE msg_id = ?",
        (status, reply, msg_id),
    )
    conn.commit()


async def _send(client, external_userid: str, open_kfid: str, text: str) -> None:
    try:
        await client.send_text(external_userid, text, open_kfid)
    except Exception:
        logger.exception("微信客服回复失败 external_userid=%s", external_userid)


async def _store_and_send(
    conn,
    kf_msg_id: str,
    openid: str,
    parsed,
    external_userid: str,
    open_kfid: str,
    settings: Settings,
    client,
    *,
    source_type: str,
    source_url: str | None,
) -> None:
    activity = insert_activity(
        conn,
        openid,
        parsed,
        settings,
        source_type=source_type,
        source_url=source_url,
    )
    conflicts = get_conflict_ids(conn, openid, activity)
    card = render_activity_card(
        activity,
        conflicts,
        settings,
        calendar_enabled=is_calendar_enabled(settings, openid),
    )
    _finish(conn, kf_msg_id, card)

    confidence = json.loads(activity.get("confidence") or "{}")
    if (
        activity.get("sync_status") == "not_synced"
        and activity.get("start_at")
        and float(confidence.get("start_at", 0) or 0) < settings.confidence_threshold
    ):
        create_pending(
            conn,
            openid,
            "time_confirm",
            {"short_no": int(activity["short_no"])},
            now=datetime.now(TZ),
        )

    await _send(client, external_userid, open_kfid, card)


async def _handle_article(
    conn,
    kf_msg_id: str,
    openid: str,
    external_userid: str,
    open_kfid: str,
    url: str,
    settings: Settings,
    client,
) -> None:
    try:
        article = await asyncio.to_thread(
            fetch_article,
            url,
            timeout=settings.article_timeout,
            max_chars=settings.article_max_chars,
            user_agent=settings.article_user_agent or DEFAULT_USER_AGENT,
        )
        parsed = extract_article_activity(article, datetime.now(TZ))
    except ArticleFetchError as exc:
        reply = (
            f"文章抓取失败：{exc}\n"
            "请长按复制活动正文发送，或发送活动海报截图。"
        )
        _finish(conn, kf_msg_id, reply, "kf_failed")
        await _send(client, external_userid, open_kfid, reply)
        return

    if parsed is None:
        reply = "文章里没识别到活动信息。请把活动时间和地点复制发给我。"
        _finish(conn, kf_msg_id, reply, "kf_failed")
        await _send(client, external_userid, open_kfid, reply)
        return

    await _store_and_send(
        conn,
        kf_msg_id,
        openid,
        parsed,
        external_userid,
        open_kfid,
        settings,
        client,
        source_type="link",
        source_url=url,
    )


async def handle_kf_message(
    conn,
    msg: dict,
    settings: Settings,
    client: WeComKFClient,
) -> None:
    """处理一条微信客服消息（只处理客户发送 origin=3）。"""
    if int(msg.get("origin", 0) or 0) != 3:
        return

    external_userid = msg.get("external_userid") or ""
    open_kfid = msg.get("open_kfid") or settings.wecom_kf_id
    msgid = msg.get("msgid") or ""
    if not external_userid or not msgid:
        return

    openid = settings.wecom_kf_user_openid
    if not openid:
        logger.warning("WECOM_KF_USER_OPENID 未配置，忽略消息")
        return

    kf_msg_id = f"kf:{msgid}"
    now = datetime.now(TZ)
    created = conn.execute(
        """
        INSERT OR IGNORE INTO messages
            (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
        VALUES (?, ?, ?, ?, 'kf_received', ?, ?)
        """,
        (
            kf_msg_id,
            openid,
            msg.get("msgtype") or "unknown",
            json.dumps(msg, ensure_ascii=False),
            make_task_no(kf_msg_id),
            now.isoformat(),
        ),
    ).rowcount
    conn.commit()
    if not created:
        return

    msgtype = (msg.get("msgtype") or "").lower()
    try:
        if msgtype == "text":
            content = ((msg.get("text") or {}).get("content") or "").strip()
            if not content:
                return
            url = extract_wechat_url(content)
            if url:
                await _handle_article(
                    conn,
                    kf_msg_id,
                    openid,
                    external_userid,
                    open_kfid,
                    url,
                    settings,
                    client,
                )
                return

            if classify_text(content) == "command":
                reply = await asyncio.to_thread(
                    handle_text, conn, openid, content, settings, now
                )
                _finish(conn, kf_msg_id, reply)
                await _send(client, external_userid, open_kfid, reply)
                return

            parsed = extract_activity(content, now)
            if parsed is None:
                _finish(conn, kf_msg_id, _NOT_ACTIVITY, "kf_not_activity")
                await _send(client, external_userid, open_kfid, _NOT_ACTIVITY)
                return
            await _store_and_send(
                conn,
                kf_msg_id,
                openid,
                parsed,
                external_userid,
                open_kfid,
                settings,
                client,
                source_type="text",
                source_url=None,
            )
            return

        if msgtype == "link":
            link = msg.get("link") or {}
            url = link.get("url") or extract_wechat_url(
                json.dumps(link, ensure_ascii=False)
            )
            if not url:
                reply = "这个链接卡片没有带上地址，请长按复制链接，以文字发给我。"
                _finish(conn, kf_msg_id, reply, "kf_failed")
                await _send(client, external_userid, open_kfid, reply)
                return
            await _handle_article(
                conn,
                kf_msg_id,
                openid,
                external_userid,
                open_kfid,
                url,
                settings,
                client,
            )
            return

        if msgtype == "image":
            _finish(conn, kf_msg_id, _IMAGE_REPLY, "kf_deferred")
            await _send(client, external_userid, open_kfid, _IMAGE_REPLY)
            return

        reply = "暂不支持该消息类型，请发送活动文字或公众号文章链接。"
        _finish(conn, kf_msg_id, reply, "kf_unsupported")
        await _send(client, external_userid, open_kfid, reply)
    except Exception:
        logger.exception("微信客服消息处理失败 msgid=%s", msgid)
        reply = "处理消息时出错了，请稍后重试。"
        _finish(conn, kf_msg_id, reply, "kf_failed")
        await _send(client, external_userid, open_kfid, reply)


async def kf_loop(
    settings: Settings,
    client: WeComKFClient | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    client = client or WeComKFClient(settings)
    conn = _session_conn(settings)
    cursor = _get_state(conn, "kf_cursor") or ""
    token = _get_state(conn, "kf_token") or ""
    initialized = _get_state(conn, "kf_initialized") == "1"
    logger.info("微信客服轮询已启动 initialized=%s", initialized)

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                data = await client.sync_msg(cursor, token)
                messages = data.get("msg_list") or []
                if initialized:
                    for msg in messages:
                        await handle_kf_message(conn, msg, settings, client)
                else:
                    _set_state(conn, "kf_initialized", "1")
                    initialized = True

                cursor = data.get("next_cursor", cursor) or cursor
                token = data.get("token", token) or token
                _set_state(conn, "kf_cursor", cursor)
                _set_state(conn, "kf_token", token)

                if not data.get("has_more"):
                    await asyncio.sleep(settings.wecom_kf_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("微信客服轮询异常")
                await asyncio.sleep(5)
    finally:
        conn.close()
