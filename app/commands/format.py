"""回复文案共用格式。"""

from __future__ import annotations

from datetime import datetime

from app.parsing.time_norm import ensure_aware

_WEEKDAYS = "一二三四五六日"

SYNC_ICONS = {
    "pending": "⏳",
    "synced": "✅",
    "update_pending": "🔄",
    "delete_pending": "🗑️",
    "deleted": "🗑️",
    "failed": "❌",
    "not_synced": "🟡",
    "external_removed": "⚠️",
}

SYNC_TEXT = {
    "pending": "待同步 ⏳",
    "synced": "已同步 ✅",
    "update_pending": "待更新 🔄",
    "delete_pending": "待删除 🗑️",
    "deleted": "已删除",
    "failed": "同步失败 ❌",
    "not_synced": "待确认 🟡",
    "external_removed": "已从日历移除 ⚠️",
}

__all__ = [
    "parse_dt",
    "format_day",
    "format_dt",
    "format_time",
    "sync_icon",
    "sync_text",
]


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def format_day(dt: datetime) -> str:
    return f"{dt.month:02d}-{dt.day:02d} 周{_WEEKDAYS[dt.weekday()]}"


def format_dt(dt: datetime) -> str:
    return f"{format_day(dt)} {dt:%H:%M}"


def format_time(start: datetime | None, end: datetime | None, all_day: bool) -> str:
    if start is None:
        return "时间待补"
    if all_day:
        return f"{format_day(start)} 全天"
    if end is not None:
        return f"{format_dt(start)}-{end:%H:%M}"
    return format_dt(start)


def sync_icon(status: str | None) -> str:
    return SYNC_ICONS.get(status or "", "⏳")


def sync_text(status: str | None) -> str:
    return SYNC_TEXT.get(status or "", status or "未知")
