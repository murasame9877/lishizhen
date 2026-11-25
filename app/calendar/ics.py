"""生成 CalDAV 事件（ICS），包含系统级 VALARM 提醒（PRD FR-24 / FR-28）。

关键约束：
- UID 由调用方生成并永久复用；
- 定时活动默认两档提醒：开始前 30 分钟、开始时；
- 全天活动默认当天 09:00 绝对时间提醒；多天只在第一天；
- 当天 09:00 之后创建且活动就是今天 → 改为创建后 10 分钟；
- 活动日期已过 → 不写提醒；
- 中国无夏令时，全天提醒也可降级为相对触发 -PT15H（等价 09:00）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_EVENT_DURATION = timedelta(hours=2)
DEFAULT_REMIND_OFFSETS: tuple[int, ...] = (-30, 0)

__all__ = [
    "TZ",
    "DEFAULT_EVENT_DURATION",
    "DEFAULT_REMIND_OFFSETS",
    "build_event_ics",
]


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _fmt_local(dt: datetime) -> str:
    return _aware(dt).strftime("%Y%m%dT%H%M%S")


def _fmt_utc(dt: datetime) -> str:
    return _aware(dt).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545：单行不超过 75 个八位组，续行以空格开头。"""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line

    chunks: list[bytes] = []
    first = True
    while data:
        limit = 75 if first else 74
        if len(data) <= limit:
            chunks.append(data)
            break
        cut = limit
        # 不切断多字节 UTF-8 字符
        while cut > 0 and (data[cut] & 0xC0) == 0x80:
            cut -= 1
        if cut == 0:
            cut = limit
        chunks.append(data[:cut])
        data = data[cut:]
        first = False

    out = chunks[0].decode("utf-8")
    for chunk in chunks[1:]:
        out += "\r\n " + chunk.decode("utf-8")
    return out


def _relative_trigger(minutes: int) -> str:
    if minutes == 0:
        return "PT0M"
    sign = "-" if minutes < 0 else ""
    return f"{sign}PT{abs(minutes)}M"


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    try:
        hour_s, minute_s = value.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
    except (ValueError, AttributeError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _all_day_alarm_at(
    start_date: date,
    remind_at: str,
    now: datetime,
) -> datetime | None:
    """全天活动的单次绝对提醒时间（PRD FR-28 AC2）。"""
    hhmm = _parse_hhmm(remind_at)
    if hhmm is None:
        return None
    hour, minute = hhmm
    today = now.date()

    if start_date < today:
        return None

    scheduled = datetime.combine(start_date, time(hour, minute), tzinfo=TZ)
    if start_date == today and now >= scheduled:
        return now + timedelta(minutes=10)
    return scheduled


def build_event_ics(
    *,
    uid: str,
    title: str,
    start: datetime,
    end: datetime | None = None,
    all_day: bool = False,
    location: str | None = None,
    description: str | None = None,
    url: str | None = None,
    sequence: int = 0,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    remind_offsets: Sequence[int] | None = DEFAULT_REMIND_OFFSETS,
    all_day_remind_at: str | None = "09:00",
    now: datetime | None = None,
) -> str:
    now = _aware(now or datetime.now(TZ))
    start = _aware(start)
    created_at = _aware(created_at or now)
    updated_at = _aware(updated_at or now)

    desc_parts: list[str] = []
    if description:
        desc_parts.append(description)
    if url:
        desc_parts.append(f"原文：{url}")
    desc = "\n".join(desc_parts)

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SDG//WeChat Schedule Agent//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(now)}",
        f"CREATED:{_fmt_utc(created_at)}",
        f"LAST-MODIFIED:{_fmt_utc(updated_at)}",
        f"SEQUENCE:{max(0, int(sequence))}",
        f"SUMMARY:{_escape_text(title or '未命名活动')}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]

    if all_day:
        start_date = start.date()
        end_date = end.date() if end else start_date + timedelta(days=1)
        if end_date <= start_date:
            end_date = start_date + timedelta(days=1)
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_date(start_date)}")
        lines.append(f"DTEND;VALUE=DATE:{_fmt_date(end_date)}")
    else:
        event_end = _aware(end) if end else start + DEFAULT_EVENT_DURATION
        if event_end <= start:
            event_end = start + DEFAULT_EVENT_DURATION
        lines.append(f"DTSTART;TZID=Asia/Shanghai:{_fmt_local(start)}")
        lines.append(f"DTEND;TZID=Asia/Shanghai:{_fmt_local(event_end)}")

    if location:
        lines.append(f"LOCATION:{_escape_text(location)}")
    if desc:
        lines.append(f"DESCRIPTION:{_escape_text(desc)}")
    if url:
        lines.append(f"URL:{url}")

    alarm_desc = f"{title or '活动'}"
    if location:
        alarm_desc += f" @ {location}"
    alarm_desc = _escape_text(alarm_desc)

    if all_day:
        if all_day_remind_at:
            alarm_at = _all_day_alarm_at(start.date(), all_day_remind_at, now)
            if alarm_at is not None:
                lines.extend(
                    [
                        "BEGIN:VALARM",
                        "ACTION:DISPLAY",
                        f"TRIGGER;VALUE=DATE-TIME:{_fmt_utc(alarm_at)}",
                        f"DESCRIPTION:{alarm_desc}",
                        "END:VALARM",
                    ]
                )
    else:
        offsets = DEFAULT_REMIND_OFFSETS if remind_offsets is None else remind_offsets
        seen: set[int] = set()
        for offset in offsets:
            offset = int(offset)
            if offset in seen:
                continue
            seen.add(offset)
            lines.extend(
                [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"TRIGGER:{_relative_trigger(offset)}",
                    f"DESCRIPTION:{alarm_desc}",
                    "END:VALARM",
                ]
            )

    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
