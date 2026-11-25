"""异步解析 Worker：消费 messages 中 parse_queued 的文本消息。

回调网关只落库与回执；真正的抽取、入库、冲突计算、卡片推送在这里完成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime

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
from app.parsing.time_norm import TZ, ensure_aware
from app.storage.db import init_db
from app.storage.repo_activities import (
    get_conflict_ids,
    insert_activity,
)
from app.storage.repo_pending import create_pending
from app.wechat.client import WeChatClient
from app.wechat.crypto import parse_message

logger = logging.getLogger(__name__)

_NOT_TEXT_REPLY = "图片解析正在接入中，请先把活动文字粘贴给我。"
_NOT_ACTIVITY_REPLY = (
    "没识别到活动信息。直接发送活动文字、公众号链接或海报截图。\n"
    "例如：周五晚7点 大礼堂 新生舞会"
)


def _connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _recover_stale(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    try:
        count = conn.execute(
            "UPDATE messages SET status='parse_queued' WHERE status='processing'"
        ).rowcount
        conn.commit()
        if count:
            logger.warning("recovered %s stale processing messages", count)
    finally:
        conn.close()


def _finish(
    conn: sqlite3.Connection, msg_id: str, status: str, result_text: str
) -> None:
    conn.execute(
        "UPDATE messages SET status=?, result_text=? WHERE msg_id=?",
        (status, result_text, msg_id),
    )
    conn.commit()


def _base_time(message: dict[str, str], fallback_iso: str) -> datetime:
    try:
        return datetime.fromtimestamp(int(message.get("CreateTime", "")), TZ)
    except (TypeError, ValueError, OSError):
        return ensure_aware(datetime.fromisoformat(fallback_iso))


async def _push(
    client: WeChatClient, settings: Settings, openid: str, text: str
) -> bool:
    if not settings.wechat_push_enabled:
        return False
    try:
        await client.send_text(openid, text)
        return True
    except Exception:
        logger.exception("客服消息推送失败 openid=%s", openid)
        return False


async def _store_and_push(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    settings: Settings,
    client: WeChatClient,
    parsed,
    *,
    source_type: str,
    source_url: str | None = None,
) -> None:
    openid = row["openid"]
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
    _finish(conn, row["msg_id"], "done", card)

    # 低置信时间：记录仍创建，但写入待确认态，等用户回复 1/2
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

    await _push(client, settings, openid, card)


async def _handle_article(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    message: dict[str, str],
    settings: Settings,
    client: WeChatClient,
    base: datetime,
    *,
    url: str | None = None,
) -> None:
    openid = row["openid"]
    target = (url or message.get("Url") or "").strip()
    if not target:
        reply = "没有识别到公众号链接。请直接粘贴 mp.weixin.qq.com 文章链接。"
        _finish(conn, row["msg_id"], "failed", reply)
        await _push(client, settings, openid, reply)
        return

    try:
        article = fetch_article(
            target,
            timeout=settings.article_timeout,
            max_chars=settings.article_max_chars,
            user_agent=settings.article_user_agent or DEFAULT_USER_AGENT,
        )
        parsed = extract_article_activity(article, base)
    except ArticleFetchError as exc:
        reply = (
            f"文章抓取失败：{exc}\n"
            "请长按复制活动正文发送，或发送活动海报截图。"
        )
        _finish(conn, row["msg_id"], "failed", reply)
        await _push(client, settings, openid, reply)
        return

    if parsed is None:
        reply = "文章里没识别到活动信息。请把活动时间和地点复制发给我。"
        _finish(conn, row["msg_id"], "not_activity", reply)
        await _push(client, settings, openid, reply)
        return

    await _store_and_push(
        conn,
        row,
        settings,
        client,
        parsed,
        source_type="link",
        source_url=target,
    )


async def _handle(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    settings: Settings,
    client: WeChatClient,
) -> None:
    msg_id = row["msg_id"]
    openid = row["openid"]
    message = parse_message(row["raw_xml"] or "")
    base = _base_time(message, row["created_at"])
    msg_type = row["msg_type"]

    if msg_type == "link":
        await _handle_article(conn, row, message, settings, client, base)
        return

    if msg_type == "text":
        content = (message.get("Content") or "").strip()
        if not content:
            _finish(conn, msg_id, "failed", "没有读到文字内容，请重新发送。")
            return

        url = extract_wechat_url(content)
        if url:
            await _handle_article(
                conn, row, message, settings, client, base, url=url
            )
            return

        parsed = extract_activity(content, base)
        if parsed is None:
            _finish(conn, msg_id, "not_activity", _NOT_ACTIVITY_REPLY)
            await _push(client, settings, openid, _NOT_ACTIVITY_REPLY)
            return

        await _store_and_push(
            conn, row, settings, client, parsed, source_type="text"
        )
        return

    _finish(conn, msg_id, "deferred", _NOT_TEXT_REPLY)
    await _push(client, settings, openid, _NOT_TEXT_REPLY)


async def process_one(settings: Settings, client: WeChatClient) -> bool:
    """处理一条待解析消息；没有待处理消息返回 False。"""
    conn = _connect(settings)
    try:
        row = conn.execute(
            "SELECT * FROM messages WHERE status='parse_queued' "
            "ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return False

        claimed = conn.execute(
            "UPDATE messages SET status='processing' "
            "WHERE msg_id=? AND status='parse_queued'",
            (row["msg_id"],),
        ).rowcount
        conn.commit()
        if not claimed:
            return True

        try:
            await _handle(conn, row, settings, client)
        except Exception:
            logger.exception("解析失败 msg_id=%s", row["msg_id"])
            conn.execute(
                "UPDATE messages SET status='failed' WHERE msg_id=?",
                (row["msg_id"],),
            )
            conn.commit()
        return True
    finally:
        conn.close()


async def worker_loop(
    settings: Settings,
    client: WeChatClient | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    client = client or WeChatClient(settings)
    _recover_stale(settings)
    logger.info("解析 Worker 已启动")

    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            processed = await process_one(settings, client)
        except Exception:
            logger.exception("Worker 循环异常")
            processed = False
        if not processed:
            await asyncio.sleep(settings.worker_poll_seconds)
