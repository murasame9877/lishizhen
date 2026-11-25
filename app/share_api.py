"""手机分享入口：`POST /share/ingest`。

用途：Android 分享目标（HTTP Shortcuts / 自建 App）把公众号链接 POST 过来，
后端落一条 link 消息，交给现有 Worker 解析并推送卡片。

安全：必须带 X-Share-Token；不暴露 openid；只接受 mp.weixin.qq.com 链接。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

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
from app.parsing.ocr import (
    OCRUnavailable,
    cleanup_images,
    ocr_image_bytes,
    save_image,
)
from app.parsing.time_norm import TZ
from app.storage.repo_activities import get_conflict_ids, insert_activity
from app.storage.repo_pending import create_pending
from app.wechat.gateway import classify_text, make_task_no

__all__ = ["create_share_router"]


class SharePayload(BaseModel):
    url: str | None = None
    text: str | None = None


class ShareHandlePayload(BaseModel):
    url: str | None = None
    text: str | None = None
    image_base64: str | None = None


def _decode_image(value: str) -> bytes:
    raw = value.strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    raw = "".join(raw.split())
    if not raw:
        raise HTTPException(status_code=400, detail="image_base64 为空")
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="image_base64 不是合法的 base64"
        ) from exc


def _share_xml(url: str, openid: str, msg_id: str) -> str:
    return (
        "<xml>"
        "<ToUserName><![CDATA[gh_share]]></ToUserName>"
        f"<FromUserName><![CDATA[{openid}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[link]]></MsgType>"
        "<Title><![CDATA[分享文章]]></Title>"
        f"<Url><![CDATA[{url}]]></Url>"
        f"<MsgId>{msg_id}</MsgId>"
        "</xml>"
    )


def create_share_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.post("/share/ingest")
    async def share_ingest(
        request: Request,
        payload: SharePayload,
        x_share_token: str = Header(default=""),
    ) -> dict:
        if not settings.share_ingest_token:
            raise HTTPException(status_code=503, detail="share ingest not configured")
        if not secrets.compare_digest(x_share_token, settings.share_ingest_token):
            raise HTTPException(status_code=403, detail="invalid share token")
        if not settings.share_user_openid:
            raise HTTPException(status_code=503, detail="share user not configured")

        raw = (payload.url or payload.text or "").strip()
        url = extract_wechat_url(raw)
        if url is None:
            raise HTTPException(
                status_code=400,
                detail="仅支持 mp.weixin.qq.com 文章链接",
            )

        msg_id = f"share-{uuid.uuid4().hex}"
        task_no = make_task_no(msg_id)
        xml = _share_xml(url, settings.share_user_openid, msg_id)

        conn = request.app.state.db
        conn.execute(
            """
            INSERT OR IGNORE INTO messages
                (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
            VALUES (?, ?, 'link', ?, 'parse_queued', ?, ?)
            """,
            (
                msg_id,
                settings.share_user_openid,
                xml,
                task_no,
                datetime.now(TZ).isoformat(),
            ),
        )
        conn.commit()

        return {
            "ok": True,
            "task_no": task_no,
            "message": "已收到，解析完成后会推送到服务号",
        }

    @router.post("/share/handle")
    async def share_handle(
        request: Request,
        payload: ShareHandlePayload,
        x_share_token: str = Header(default=""),
    ) -> dict:
        if not settings.share_ingest_token:
            raise HTTPException(status_code=503, detail="share ingest not configured")
        if not secrets.compare_digest(x_share_token, settings.share_ingest_token):
            raise HTTPException(status_code=403, detail="invalid share token")
        openid = settings.share_user_openid
        if not openid:
            raise HTTPException(status_code=503, detail="share user not configured")

        text = (payload.text or "").strip()
        image_bytes: bytes | None = None
        if payload.image_base64:
            image_bytes = _decode_image(payload.image_base64)
            if len(image_bytes) > settings.image_max_bytes:
                raise HTTPException(status_code=413, detail="图片太大（上限 10MB）")
        if not payload.url and not text and image_bytes is None:
            raise HTTPException(status_code=400, detail="url, text or image required")

        conn = request.app.state.db
        now = datetime.now(TZ)
        audit_id = f"web-{uuid.uuid4().hex}"
        audit_payload: dict = {"url": payload.url, "text": text or None}
        if image_bytes is not None:
            # 不把 base64 原文塞进数据库
            audit_payload["image"] = f"<{len(image_bytes)} bytes>"
        conn.execute(
            """
            INSERT OR IGNORE INTO messages
                (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
            VALUES (?, ?, 'web', ?, 'web_received', ?, ?)
            """,
            (
                audit_id,
                openid,
                json.dumps(audit_payload, ensure_ascii=False),
                make_task_no(audit_id),
                now.isoformat(),
            ),
        )
        conn.commit()

        def finish(status: str, reply: str) -> None:
            conn.execute(
                "UPDATE messages SET status = ?, result_text = ? WHERE msg_id = ?",
                (status, reply, audit_id),
            )
            conn.commit()

        def card_for(
            parsed,
            source_type: str,
            source_url: str | None,
            source_raw: str | None = None,
        ) -> str:
            activity = insert_activity(
                conn,
                openid,
                parsed,
                settings,
                source_type=source_type,
                source_url=source_url,
                source_raw=source_raw,
            )
            conflicts = get_conflict_ids(conn, openid, activity)
            card = render_activity_card(
                activity,
                conflicts,
                settings,
                calendar_enabled=is_calendar_enabled(settings, openid),
            )
            confidence = json.loads(activity.get("confidence") or "{}")
            if (
                activity.get("sync_status") == "not_synced"
                and activity.get("start_at")
                and float(confidence.get("start_at", 0) or 0)
                < settings.confidence_threshold
            ):
                create_pending(
                    conn,
                    openid,
                    "time_confirm",
                    {"short_no": int(activity["short_no"])},
                    now=now,
                )
            return card

        try:
            if image_bytes is not None:
                if not settings.ocr_enabled:
                    reply = "图片识别暂未开启，请把活动文字或链接发给我。"
                    finish("web_not_activity", reply)
                    return {"ok": True, "reply": reply}

                image_path = await asyncio.to_thread(
                    save_image, image_bytes, settings.image_dir, now=now
                )
                await asyncio.to_thread(
                    cleanup_images,
                    settings.image_dir,
                    ttl_days=settings.image_retention_days,
                )
                try:
                    ocr_text = await asyncio.wait_for(
                        asyncio.to_thread(
                            ocr_image_bytes,
                            image_bytes,
                            min_score=settings.ocr_min_score,
                        ),
                        timeout=settings.ocr_timeout,
                    )
                except TimeoutError:
                    reply = "图片识别超时了，请把活动文字或链接发给我。"
                    finish("web_failed", reply)
                    return {"ok": True, "reply": reply}
                except OCRUnavailable:
                    reply = "图片识别组件不可用，请把活动文字或链接发给我。"
                    finish("web_failed", reply)
                    return {"ok": True, "reply": reply}
                except ValueError:
                    reply = "这张图片格式不支持，请换成 JPG/PNG 截图。"
                    finish("web_failed", reply)
                    return {"ok": True, "reply": reply}

                ocr_text = ocr_text.strip()
                if not ocr_text:
                    reply = "图片里没识别到文字，请截取活动海报正文区域再发一次。"
                    finish("web_not_activity", reply)
                    return {"ok": True, "reply": reply}

                parsed = extract_activity(ocr_text, now)
                if parsed is None:
                    preview = " ".join(ocr_text.split())[:80]
                    reply = (
                        "识别到文字但没找到活动信息：\n"
                        f"{preview}\n"
                        "请把活动时间和地点补一句发给我。"
                    )
                    finish("web_not_activity", reply)
                    return {
                        "ok": True,
                        "reply": reply,
                        "ocr_text": ocr_text[:1000],
                    }
                card = card_for(parsed, "image", None, source_raw=str(image_path))
                finish("web_handled", card)
                return {"ok": True, "reply": card, "ocr_text": ocr_text[:1000]}

            if payload.url:
                url = extract_wechat_url(payload.url) or payload.url.strip()
                article = await asyncio.to_thread(
                    fetch_article,
                    url,
                    timeout=settings.article_timeout,
                    max_chars=settings.article_max_chars,
                    user_agent=settings.article_user_agent or DEFAULT_USER_AGENT,
                )
                parsed = extract_article_activity(article, now)
                if parsed is None:
                    reply = "文章里没识别到活动信息。请把活动时间和地点复制发给我。"
                    finish("web_not_activity", reply)
                    return {"ok": True, "reply": reply}
                card = card_for(parsed, "link", url)
                finish("web_handled", card)
                return {"ok": True, "reply": card}

            if classify_text(text) == "command":
                reply = await asyncio.to_thread(
                    handle_text, conn, openid, text, settings, now
                )
                finish("web_handled", reply)
                return {"ok": True, "reply": reply}

            parsed = extract_activity(text, now)
            if parsed is None:
                reply = (
                    "没识别到活动信息。直接发送活动文字或公众号文章链接。\n"
                    "例如：周五晚7点 大礼堂 新生舞会"
                )
                finish("web_not_activity", reply)
                return {"ok": True, "reply": reply}
            card = card_for(parsed, "text", None)
            finish("web_handled", card)
            return {"ok": True, "reply": card}
        except ArticleFetchError as exc:
            reply = (
                f"文章抓取失败：{exc}\n"
                "请长按复制活动正文发送，或发送活动海报截图。"
            )
            finish("web_failed", reply)
            return {"ok": True, "reply": reply}
        except Exception:
            reply = "处理消息时出错了，请稍后重试。"
            finish("web_failed", reply)
            return {"ok": True, "reply": reply}

    return router
