"""规则抽取：中文活动文本 → 结构化字段（FR-04 ~ FR-10）。

不做猜测性填充；抽不到就留空并降低置信度。
LLM 后续接在同一个返回结构上，不改变调用方。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time

from app.parsing.time_norm import TZ, ensure_aware, normalize_time_expression

__all__ = ["ParsedActivity", "extract_activity"]


@dataclass(frozen=True)
class ParsedActivity:
    title: str
    start_at: datetime | None
    end_at: datetime | None
    all_day: bool
    location: str | None
    deadline_at: datetime | None
    organizer: str | None
    notes: str | None
    confidence: dict[str, float]
    time_basis: str
    title_uncertain: bool = False
    unresolved_time: bool = False


# 用于过滤时间片段，避免把「迎新晚会」里的「晚」误判成时间
_TIME_TOKEN_RE = re.compile(
    r"(今天|今日|明天|明日|后天|大后天|今晚|明晚|"
    r"(?:下下|下|本|这)?(?:周|星期|礼拜)[一二三四五六日天1-7]|"
    r"\d{1,2}[:：]\d{2}|"
    r"\d{1,2}\s*点|"
    r"\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?|"
    r"全天|整天|"
    r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|晚)\s*\d{1,2}\s*点)"
)

_TOKEN_SPLIT_RE = re.compile(r"[\s，,。;；、|·•]+")

_PLACE_SUFFIX = (
    r"(?:大礼堂|礼堂|教室|教学楼|楼|馆|厅|室|场|堂|院|操场|操|中心|广场|校区|教)"
)
_PLACE_TOKEN_RE = re.compile(r"^[一-龥A-Za-z0-9]{1,12}" + _PLACE_SUFFIX + r"$")

_LOCATION_LABEL_RE = re.compile(
    r"(?:活动|集合|举办)?(?:地点|地址|场地)\s*[:：]?\s*([^\s，,。;；、|]{2,20})"
)
_LOCATION_AT_RE = re.compile(r"@\s*([^\s，,。;；、|]{2,20})")
_LOCATION_ZAI_RE = re.compile(
    r"(?<![现正存所])在\s*([一-龥A-Za-z0-9]{1,12}" + _PLACE_SUFFIX + r")"
)

_DEADLINE_RE = re.compile(
    r"(?:报名截止时间|报名截止|截止时间|截止|ddl|DDL)\s*[:：]?\s*([^\s，,。;；]{2,30})"
)
_DEADLINE_TIME_RE = re.compile(
    r"[ \t]*(?:\d{1,2}\s*[:：]\s*\d{2}|\d{1,2}\s*点(?:\s*\d{1,2}\s*分)?)"
)
_TIME_IN_TEXT_RE = re.compile(r"\d{1,2}\s*[:：]\s*\d{2}|\d{1,2}\s*点")
_ORGANIZER_RE = re.compile(
    r"(?:主办单位|主办方|主办|承办单位|承办方|承办)\s*[:：]?\s*([^\s，,。;；]{2,30})"
)
_TITLE_LABEL_RE = re.compile(r"(?:活动名称|活动主题|主题|名称)\s*[:：]\s*")
_FIELD_LABEL_RE = re.compile(
    r"^(?:活动)?(?:时间|日期|地点|地址|场地|主办(?:单位|方)?|承办(?:单位|方)?|"
    r"报名(?:截止)?|截止(?:时间)?|备注)$"
)
_LEADING_NOISE_RE = re.compile(r"^(?:有个|有一场|一场|关于)")
_ACTIVITY_WORDS_RE = re.compile(
    r"讲座|活动|会议|演出|比赛|招新|报名|沙龙|论坛|分享会|舞会|音乐会|展览|"
    r"培训|课程|宣讲|社团|聚会|典礼|开幕式|闭幕式|工作坊|训练营|招聘|路演|"
    r"放映|读书会|见面会|运动会|晚会"
)

_TRIM_CHARS = " \t\r\n「」『』【】[]（）()<>《》\"'“”‘’·•-—…"


def _tokens(text: str) -> list[str]:
    return [part.strip() for part in _TOKEN_SPLIT_RE.split(text) if part.strip()]


def _clean(value: str) -> str:
    return value.strip(_TRIM_CHARS).strip()


def _extract_deadline(text: str, base: datetime) -> tuple[datetime | None, str]:
    match = _DEADLINE_RE.search(text)
    if not match:
        return None, text

    value = match.group(1)
    removal = match.group(0)
    # 日期与时间之间常有空格（OCR 也会拆行），把紧随其后的时间并进来
    if not _TIME_IN_TEXT_RE.search(value):
        tail = _DEADLINE_TIME_RE.match(text, match.end())
        if tail:
            value = f"{value} {tail.group(0).strip()}"
            removal = text[match.start():tail.end()]

    normalized = normalize_time_expression(value, base)
    deadline: datetime | None = None
    if normalized.start is not None:
        if normalized.all_day:
            # 24:00 归一为 23:59（PRD FR-07 AC1 允许二选一，全局一致）
            deadline = datetime.combine(
                normalized.start.date(), time(23, 59), tzinfo=TZ
            )
        else:
            deadline = normalized.start
    return deadline, text.replace(removal, " ")


def _extract_organizer(text: str) -> tuple[str | None, str]:
    match = _ORGANIZER_RE.search(text)
    if not match:
        return None, text
    organizer = _clean(match.group(1))
    return (organizer or None), text.replace(match.group(0), " ")


def _extract_location(text: str) -> tuple[str | None, float, str]:
    for pattern, confidence in (
        (_LOCATION_LABEL_RE, 0.85),
        (_LOCATION_AT_RE, 0.85),
        (_LOCATION_ZAI_RE, 0.8),
    ):
        match = pattern.search(text)
        if match:
            location = _clean(match.group(1))
            if location:
                return location, confidence, text.replace(match.group(0), " ")

    for token in _tokens(text):
        cleaned = _clean(token)
        if len(cleaned) >= 2 and _PLACE_TOKEN_RE.match(cleaned):
            return cleaned, 0.7, text.replace(token, " ")

    return None, 0.0, text


def _score_title_line(value: str, location: str | None) -> float | None:
    if not value or len(value) < 4 or len(value) > 60:
        return None
    if _TIME_TOKEN_RE.search(value):
        return None
    if location and location in value:
        return None
    if value.startswith(("http", "www", "<")):
        return None
    score = 0.0
    if _ACTIVITY_WORDS_RE.search(value):
        score += 3
    if 6 <= len(value) <= 30:
        score += 2
    if value.endswith(("，", ",", "。", ";", "；", "：", ":")):
        score -= 0.5
    if re.search(r"\d", value):
        score -= 0.2
    return score


def _extract_title_from_lines(
    text: str, location: str | None
) -> str | None:
    best: tuple[float, str] | None = None
    for line in text.splitlines():
        value = _TITLE_LABEL_RE.sub("", _clean(line))
        value = _LEADING_NOISE_RE.sub("", value).strip(_TRIM_CHARS)
        if not value or _FIELD_LABEL_RE.match(value):
            continue
        score = _score_title_line(value, location)
        if score is None:
            continue
        if best is None or score > best[0]:
            best = (score, value)
    if best and best[0] > 0.5:
        return best[1][:40]
    return None


def _extract_title(text: str, location: str | None) -> tuple[str, float, bool]:
    # OCR / 长文：逐行挑标题，避免把整篇正文拼成标题
    if len(text) > 200 or text.count("\n") >= 6:
        line_title = _extract_title_from_lines(text, location)
        if line_title:
            return line_title, 0.65, False

    candidates: list[str] = []
    for token in _tokens(text):
        value = _clean(token)
        if not value:
            continue
        if _TIME_TOKEN_RE.search(value):
            continue
        if location and value == location:
            continue
        value = _TITLE_LABEL_RE.sub("", value)
        value = _LEADING_NOISE_RE.sub("", value).strip(_TRIM_CHARS)
        if value and not _FIELD_LABEL_RE.match(value):
            candidates.append(value)

    if candidates:
        return " ".join(candidates), 0.8, False

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    fallback = _clean(first_line)[:30] or "未命名活动"
    return fallback, 0.4, True


def _extract_labeled_time(text: str, base: datetime):
    """优先取「活动时间：…」标签后的时间，避免抓成文章发布日期。"""
    lines = [line.strip() for line in text.splitlines()]
    pattern = re.compile(
        r"(?:活动时间|举办时间|活动日期|举办日期|时间|日期)\s*[:：]?\s*(.*)"
    )
    for index, line in enumerate(lines):
        if not line or "截止" in line or "报名" in line:
            continue
        match = pattern.search(line)
        if not match:
            continue
        candidates = []
        if match.group(1).strip():
            candidates.append(match.group(1).strip())
        candidates.extend(lines[index + 1:index + 3])
        for candidate in candidates:
            if not candidate:
                continue
            normalized = normalize_time_expression(candidate, base)
            if normalized.start is not None and not normalized.unresolved:
                return normalized
    return None


def extract_activity(
    text: str,
    base: datetime,
    *,
    source_type: str = "text",
    source_url: str | None = None,
) -> ParsedActivity | None:
    """从一段文本抽取一条活动；纯闲聊返回 None。"""
    raw = (text or "").strip()
    if not raw:
        return None
    base = ensure_aware(base)

    # 先摘掉报名截止，避免它的日期被误当成活动日期
    working = raw
    deadline_at, working = _extract_deadline(working, base)
    organizer, working = _extract_organizer(working)
    normalized = _extract_labeled_time(working, base) or normalize_time_expression(
        working, base
    )
    location, location_confidence, working = _extract_location(working)
    title, title_confidence, title_uncertain = _extract_title(working, location)

    # 纯闲聊：无时间、无地点、也没有活动关键词 → 不建记录（FR-04 AC3）
    if (
        normalized.unresolved
        and location is None
        and not _ACTIVITY_WORDS_RE.search(raw)
    ):
        return None

    start_at = normalized.start
    end_at = normalized.end
    confidence: dict[str, float] = {
        "title": round(title_confidence, 2),
        "start_at": round(normalized.confidence if start_at else 0.0, 2),
    }
    if location is not None:
        confidence["location"] = round(location_confidence, 2)
    if deadline_at is not None:
        confidence["deadline_at"] = 0.85

    return ParsedActivity(
        title=title,
        start_at=start_at,
        end_at=end_at,
        all_day=normalized.all_day if start_at else False,
        location=location,
        deadline_at=deadline_at,
        organizer=organizer,
        notes=source_url,
        confidence=confidence,
        time_basis=normalized.basis,
        title_uncertain=title_uncertain,
        unresolved_time=start_at is None,
    )
