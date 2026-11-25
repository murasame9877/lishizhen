"""微信对话框回复模板（PRD 7.5）。"""

from __future__ import annotations

import json
from datetime import datetime

from app.config import Settings
from app.parsing.time_norm import ensure_aware

__all__ = ["render_activity_card"]

_WEEKDAYS = "一二三四五六日"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def _fmt_day(dt: datetime) -> str:
    return f"{dt.month:02d}-{dt.day:02d} 周{_WEEKDAYS[dt.weekday()]}"


def _fmt_dt(dt: datetime) -> str:
    return f"{_fmt_day(dt)} {dt:%H:%M}"


def _load_confidence(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def render_activity_card(
    activity: dict,
    conflict_ids: list[int],
    settings: Settings,
    *,
    calendar_enabled: bool = True,
) -> str:
    short_no = int(activity["short_no"])
    title = activity.get("title") or "未命名活动"
    confidence = _load_confidence(activity.get("confidence"))
    time_confidence = float(confidence.get("start_at", 0) or 0)
    title_confidence = float(confidence.get("title", 1) or 1)

    start = _parse_dt(activity.get("start_at"))
    end = _parse_dt(activity.get("end_at"))
    all_day = bool(activity.get("all_day"))
    location = activity.get("location")
    deadline = _parse_dt(activity.get("deadline_at"))
    source_url = activity.get("source_url")

    lines: list[str] = []
    if start is None:
        lines.append(f"🟡 已记录 #{short_no}，信息不完整：")
        time_line = "🕒 未识别到时间"
    elif time_confidence < settings.confidence_threshold:
        lines.append(f"🟡 已记录 #{short_no}，但时间不确定：")
        if all_day:
            time_line = f"🕒 {_fmt_day(start)}（全天）?"
        else:
            time_line = f"🕒 {_fmt_dt(start)}?"
    else:
        lines.append(f"✅ 已记录 #{short_no}")
        if all_day:
            time_line = f"📅 {_fmt_day(start)}（全天）"
        elif end is not None:
            time_line = f"🕒 {_fmt_dt(start)}-{end:%H:%M}"
        else:
            time_line = f"🕒 {_fmt_dt(start)}"

    title_line = f"📌 {title}"
    if title_confidence < 0.5:
        title_line += "（标题待确认）"

    lines.append(title_line)
    lines.append(time_line)
    if location:
        lines.append(f"📍 {location}")
    if deadline is not None:
        lines.append(f"⏰ 报名截止 {_fmt_dt(deadline)}")
    if conflict_ids:
        ids = "、".join(f"#{i}" for i in conflict_ids)
        lines.append(f"⚠️ 与 {ids} 时间冲突（两条均已保留）")
    if source_url:
        lines.append(f"🔗 原文：{source_url}")

    sync_status = activity.get("sync_status")
    if not calendar_enabled:
        lines.append("状态：演示模式（仅保存在微信内，不写入系统日历）")
    elif start is None:
        lines.append("状态：信息不完整（补全时间后才会写入系统日历）")
    elif sync_status == "not_synced":
        lines.append("状态：待确认（确认后才会写入系统日历）")
    elif sync_status == "synced":
        lines.append("状态：已同步 ✅")
    elif sync_status == "failed":
        lines.append("状态：同步失败 ❌（回复 重试）")
    else:
        lines.append("状态：待同步（开启自动同步，10 分钟内进入系统日历）")

    if start is None:
        lines.append(f"回复 改 {short_no} 时间 11-27 19:00 补全时间")
    elif time_confidence < settings.confidence_threshold:
        lines.append("请回复 1 确认，或 2 修改为具体时间。")
        lines.append("确认前不会写入系统日历。")
    else:
        lines.append(
            f"回复 #{short_no} 看详情｜改 {short_no} 时间 ...｜删 {short_no}"
        )

    return "\n".join(lines)
