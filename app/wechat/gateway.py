"""微信回调处理：只做验签后的轻量落库与 5 秒被动回执（PRD FR-01、C1、C2）。

解析、OCR、LLM 抽取全部异步，绝不在这里执行。
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import datetime

from app.config import Settings
from app.parsing.time_norm import TZ, ensure_aware
from app.wechat.crypto import build_text_reply, parse_message

logger = logging.getLogger(__name__)

_COMMAND_PATTERNS = [
    r"^(列表|日程|我的日程|更多|下一页|全部|帮助|\?|同步|立即同步|重试|撤销|配置|配置完成|今天|明天|本周|下周|冲突|结果|最新结果)$",
    r"^自动同步\s*(开|关)?$",
    r"^默认提醒\b",
    r"^提醒\s+\d+\b",
    r"^重新加回\s+\d+$",
    r"^清空(本周|全部)$",
    r"^关键词\s+.+$",
    r"^地点\s+.+$",
    r"^取消\s+[A-Za-z]?\d+$",
    r"^[#＃]?\d+$",
    r"^(改|删)\s+\d+",
]
_COMMAND_RE = re.compile("|".join(f"(?:{p})" for p in _COMMAND_PATTERNS))

UNSUPPORTED_REPLY = "暂不支持该格式，请长按文字复制后发送，或截图发送。"
WELCOME_REPLY = (
    "欢迎使用日程助手 📅\n"
    "把公众号文章链接、活动文字或海报截图直接发给我，"
    "我会自动整理并写入手机系统日历。\n"
    "首次使用请回复「配置」，完成一次性日历账户设置。\n"
    "示例：\n"
    "· 粘贴 mp.weixin.qq.com 文章链接\n"
    "· 发送「周五晚7点 大礼堂 新生舞会」\n"
    "· 发送活动海报截图"
)


def make_task_no(msg_id: str) -> str:
    """稳定的短任务号，便于用户引用，也便于重试时回显同一个编号。"""
    number = int(hashlib.sha1(msg_id.encode("utf-8")).hexdigest()[:8], 16) % 9000 + 1000
    return f"A{number}"


def classify_text(content: str) -> str:
    return "command" if _COMMAND_RE.search(content.strip()) else "parse"


def _reply_xml(message: dict[str, str], content: str, now: datetime) -> str:
    return build_text_reply(
        to_user=message.get("FromUserName", ""),
        from_user=message.get("ToUserName", ""),
        content=content,
        create_time=int(now.timestamp()),
    )


def process_callback(
    conn: sqlite3.Connection,
    raw_xml: str | bytes,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    """返回被动回复 XML；无需回复时返回 "success"。"""
    now = ensure_aware(now or datetime.now(TZ))
    message = parse_message(raw_xml)

    openid = message.get("FromUserName", "")
    msg_type = message.get("MsgType", "").lower()
    created_at = now.isoformat()
    raw_text = raw_xml.decode("utf-8", "replace") if isinstance(raw_xml, bytes) else raw_xml

    # event 消息没有 MsgId，用 openid+时间+事件名构造幂等键
    msg_id = message.get("MsgId") or (
        f"evt:{openid}:{message.get('CreateTime', '')}:{message.get('Event', '')}"
    )
    task_no = make_task_no(msg_id)

    status = "unsupported"
    reply: str | None = None

    if msg_type == "text":
        content = message.get("Content", "")
        stripped = content.strip()
        if classify_text(content) == "command":
            status = "command_handled"
            try:
                from app.commands.handlers import handle_text

                reply = handle_text(conn, openid, content, settings, now)
            except Exception:
                logger.exception("指令处理失败 openid=%s", openid)
                reply = "处理指令时出错了，请稍后重试。回复 帮助 查看可用指令。"
        else:
            status = "parse_queued"
            reply = (
                f"已收到 #{task_no}，正在解析，预计 30 秒内完成。\n"
                f"回复 取消 {task_no} 可撤销本次解析。"
            )
    elif msg_type == "link":
        status = "parse_queued"
        reply = (
            f"已收到 #{task_no}，正在解析，预计 30 秒内完成。\n"
            f"回复 取消 {task_no} 可撤销本次解析。"
        )
    elif msg_type == "image":
        status = "parse_queued"
        reply = (
            f"已收到 #{task_no}，正在识别图片，预计 90 秒内完成。\n"
            f"回复 取消 {task_no} 可撤销本次解析。"
        )
    elif msg_type == "event":
        event = message.get("Event", "").lower()
        if event == "subscribe":
            status = "event_subscribe"
            reply = WELCOME_REPLY
        elif event == "unsubscribe":
            status = "event_unsubscribe"
            reply = None
        else:
            status = f"event_{event or 'unknown'}"
            reply = None
    else:
        status = "unsupported"
        reply = UNSUPPORTED_REPLY

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO messages
            (msg_id, openid, msg_type, raw_xml, status, task_no, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (msg_id, openid, msg_type, raw_text, status, task_no, created_at),
    )
    conn.commit()

    if cursor.rowcount == 0:
        logger.info("duplicate callback ignored: msg_id=%s", msg_id)

    if reply is None:
        return "success"
    return _reply_xml(message, reply, now)
