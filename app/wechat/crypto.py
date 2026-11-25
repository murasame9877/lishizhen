"""微信回调的验签、XML 解析与被动回复构造（C1、NFR-06）。"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Mapping

from lxml import etree

__all__ = [
    "check_signature",
    "parse_message",
    "cdata_escape",
    "build_text_reply",
    "message_to_openid",
]


def check_signature(
    token: str,
    timestamp: str,
    nonce: str,
    signature: str,
) -> bool:
    """明文模式签名：sha1(sort(token, timestamp, nonce))。"""
    if not token or not timestamp or not nonce or not signature:
        return False
    raw = "".join(sorted([str(token), str(timestamp), str(nonce)]))
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return digest == str(signature)


def parse_message(xml_text: str | bytes) -> dict[str, str]:
    """安全解析微信回调 XML，禁用实体解析与网络加载。"""
    payload = xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False,
        huge_tree=False,
    )
    root = etree.fromstring(payload, parser=parser)
    message: dict[str, str] = {}
    for child in root:
        if isinstance(child.tag, str):
            message[child.tag] = child.text or ""
    return message


def cdata_escape(value: object) -> str:
    """CDATA 内容中不能出现 `]]>`。"""
    return str(value).replace("]]>", "]]]]><![CDATA[>")


def build_text_reply(
    *,
    to_user: str,
    from_user: str,
    content: str,
    create_time: int | None = None,
) -> str:
    """构造被动回复文本 XML。

    to_user: 接收者（用户 openid）
    from_user: 发送者（公众号原始 ID）
    """
    ts = int(create_time if create_time is not None else time.time())
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{cdata_escape(to_user)}]]></ToUserName>"
        f"<FromUserName><![CDATA[{cdata_escape(from_user)}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{cdata_escape(content)}]]></Content>"
        "</xml>"
    )


def message_to_openid(message: Mapping[str, str]) -> str:
    return message.get("FromUserName", "")
