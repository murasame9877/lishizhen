"""公众号文章抓取与活动字段抽取。

只做服务端抓取与轻量清洗；反爬失败时抛出明确错误，由 Worker 提示用户
改为「复制正文」或「截图」，不创建半成品记录。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time

import httpx
from lxml import etree
from lxml import html as lxml_html

from app.parsing.extract_rules import ParsedActivity
from app.parsing.time_norm import TZ, ensure_aware, normalize_time_expression

__all__ = [
    "Article",
    "ArticleFetchError",
    "fetch_article",
    "extract_article_activity",
    "extract_wechat_url",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 MicroMessenger/8.0.47(0x18002f2f) NetType/WIFI Language/zh_CN"
)

_WECHAT_URL_RE = re.compile(
    r"https?://mp\.weixin\.qq\.com/[^\s\"'<>，。；;）)】\]、]+"
)
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[|｜\-–—]\s*(?:清华大学|清华|微信公众平台|微信公众号)\s*$"
)

_TIME_LABEL_RE = re.compile(
    r"(?:活动时间|讲座时间|举办时间|开始时间|(?<!发布)时间)\s*[:：]?\s*"
    r"([^\n。；;]{2,80})"
)
_LOCATION_LABEL_RE = re.compile(
    r"(?:活动地点|讲座地点|举办地点|地点|地址|场地)\s*[:：]?\s*"
    r"([^\n。；;]{2,60})"
)
_DEADLINE_LABEL_RE = re.compile(
    r"(?:报名截止时间|报名截止|截止时间|截止)\s*[:：]?\s*"
    r"([^\n。；;]{2,40})"
)
_ORGANIZER_LABEL_RE = re.compile(
    r"(?:主办单位|主办方|主办|承办单位|承办方|承办)\s*[:：]?\s*"
    r"([^\n。；;]{2,40})"
)

_TRIM_CHARS = " \t\r\n：:，,。；;、|·•-—…「」『』【】[]（）()<>《》\"'“”‘’"
_BAD_LINE_WORDS = ("发布", "编辑", "阅读", "关注", "投稿", "排版", "点击", "扫码")
_SAFE_LINE_HINT_RE = re.compile(
    r"(活动|讲座|时间|开始|周[一二三四五六日天]|星期|"
    r"\d{1,2}\s*月\s*\d{1,2}\s*日)"
)


@dataclass(frozen=True)
class Article:
    title: str
    text: str
    url: str


class ArticleFetchError(RuntimeError):
    pass


def extract_wechat_url(text: str) -> str | None:
    match = _WECHAT_URL_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip("，。；;）)】]\"'")


def _clean(value: str) -> str:
    return value.strip(_TRIM_CHARS).strip()


def _extract_title(doc) -> str:
    title = " ".join(
        " ".join(doc.xpath('//h1[@id="activity-name"]//text()')).split()
    ).strip()
    if not title:
        meta = doc.xpath('//meta[@property="og:title"]/@content')
        if meta:
            title = " ".join(meta[0].split()).strip()
    if not title:
        nodes = doc.xpath("//title/text()")
        if nodes:
            title = " ".join(nodes[0].split()).strip()
    return _TITLE_SUFFIX_RE.sub("", title).strip()


def _extract_body(doc) -> str:
    nodes = doc.xpath('//div[@id="js_content"]')
    if not nodes:
        nodes = doc.xpath('//div[contains(@class, "rich_media_content")]')
    if not nodes:
        return ""
    raw = nodes[0].text_content()
    lines = []
    for line in raw.splitlines():
        cleaned = re.sub(r"[ \t　]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def fetch_article(
    url: str,
    *,
    timeout: float = 15.0,
    max_chars: int = 12000,
    user_agent: str = DEFAULT_USER_AGENT,
    transport: httpx.BaseTransport | None = None,
) -> Article:
    url = (url or "").strip()
    if not _WECHAT_URL_RE.match(url):
        raise ArticleFetchError("仅支持 mp.weixin.qq.com 文章链接")

    headers = {
        "User-Agent": user_agent,
        "Referer": "https://mp.weixin.qq.com/",
    }
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        ) as client:
            response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ArticleFetchError(f"网络请求失败（{type(exc).__name__}）") from exc

    if response.status_code != 200:
        raise ArticleFetchError(f"文章返回状态码 {response.status_code}")

    html_text = response.text
    if "js_content" not in html_text and any(
        marker in html_text for marker in ("环境异常", "完成验证", "去验证")
    ):
        raise ArticleFetchError("微信要求环境验证，服务端暂时抓不到正文")

    try:
        doc = lxml_html.fromstring(html_text)
    except (etree.ParserError, ValueError) as exc:
        raise ArticleFetchError("文章页面解析失败") from exc

    title = _extract_title(doc)
    body = _extract_body(doc)
    if not body:
        raise ArticleFetchError("没有抓到正文（可能需要验证或文章已删除）")

    return Article(title=title, text=body[:max_chars], url=url)


def _find_label(pattern: re.Pattern, text: str) -> tuple[str | None, str]:
    match = pattern.search(text)
    if not match:
        return None, text
    value = _clean(match.group(1))
    return (value or None), text.replace(match.group(0), " ")


def _extract_deadline(text: str, base: datetime) -> tuple[datetime | None, str]:
    value, remaining = _find_label(_DEADLINE_LABEL_RE, text)
    if not value:
        return None, remaining
    normalized = normalize_time_expression(value, base)
    if normalized.start is None:
        return None, remaining
    if normalized.all_day:
        deadline = datetime.combine(
            normalized.start.date(), time(23, 59), tzinfo=TZ
        )
    else:
        deadline = normalized.start
    return deadline, remaining


def _fallback_time(text: str, base: datetime):
    for line in text.splitlines()[:60]:
        if any(word in line for word in _BAD_LINE_WORDS):
            continue
        if not _SAFE_LINE_HINT_RE.search(line):
            continue
        if "点" not in line and ":" not in line and "：" not in line:
            continue
        normalized = normalize_time_expression(line, base)
        if normalized.start is not None:
            return normalized
    return normalize_time_expression("", base)


def extract_article_activity(
    article: Article,
    base: datetime,
) -> ParsedActivity | None:
    base = ensure_aware(base)
    title = _clean(article.title)
    if not title:
        title = "未命名活动"
        title_confidence = 0.4
        title_uncertain = True
    else:
        title_confidence = 0.9
        title_uncertain = False

    working = article.text
    deadline_at, working = _extract_deadline(working, base)
    organizer, working = _find_label(_ORGANIZER_LABEL_RE, working)
    location, working = _find_label(_LOCATION_LABEL_RE, working)
    time_text, _ = _find_label(_TIME_LABEL_RE, working)

    if time_text:
        normalized = normalize_time_expression(time_text, base)
        if normalized.start is None:
            normalized = _fallback_time(working, base)
    else:
        normalized = _fallback_time(working, base)

    start_at = normalized.start
    if start_at is None and not article.text and not article.title:
        return None

    confidence: dict[str, float] = {
        "title": round(title_confidence, 2),
        "start_at": round(normalized.confidence if start_at else 0.0, 2),
    }
    if location:
        confidence["location"] = 0.8
    if deadline_at:
        confidence["deadline_at"] = 0.85

    return ParsedActivity(
        title=title,
        start_at=start_at,
        end_at=normalized.end,
        all_day=normalized.all_day if start_at else False,
        location=location,
        deadline_at=deadline_at,
        organizer=organizer,
        notes=None,
        confidence=confidence,
        time_basis=normalized.basis,
        title_uncertain=title_uncertain,
        unresolved_time=start_at is None,
    )
