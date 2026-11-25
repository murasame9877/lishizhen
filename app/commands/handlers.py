"""微信对话框指令处理（PRD 6.3、7.3、7.5）。"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, time, timedelta

from app.commands.format import (
    format_day,
    format_dt,
    format_time,
    parse_dt,
    sync_icon,
    sync_text,
)
from app.commands.parser import Command, parse_command, resolve_field
from app.config import Settings, is_calendar_enabled
from app.parsing.extract_rules import ParsedActivity
from app.parsing.time_norm import TZ, ensure_aware, normalize_time_expression
from app.storage.repo_activities import (
    ensure_user_prefs,
    get_activity,
    get_by_short_nos,
    get_conflict_ids,
    insert_activity,
    list_all_active,
    list_future,
    count_future,
    soft_delete,
    update_activity,
)
from app.storage.repo_pending import consume_pending, create_pending, get_pending

__all__ = ["handle_text"]

_LIST_PAGE_SIZE = 6
_UNKNOWN = (
    "没看懂这条指令。常用操作：\n"
    "· 列表 —— 查看日程\n"
    "· #3 —— 查看详情\n"
    "· 改 3 时间 11-27 19:30\n"
    "· 删 3\n"
    "· 同步\n"
    "回复 帮助 查看全部指令。"
)

_HELP = (
    "【记录】直接发送：公众号链接 / 活动文字 / 海报截图\n"
    "【查看】列表｜#3｜今天｜明天｜本周｜冲突｜关键词 讲座\n"
    "【修改】改 3 时间 11-27 19:30｜改 3 地点 大礼堂\n"
    "【删除】删 3 → 回复 1 确认｜删 3,5\n"
    "【同步】同步｜自动同步 开｜自动同步 关\n"
    "【提醒】提醒 3 提前1小时｜提醒 3 关闭｜默认提醒 提前30分钟\n"
    "【其他】重新加回 3｜撤销｜帮助｜配置"
)

_FIELD_LABELS = {
    "title": "名称",
    "start": "时间",
    "end": "结束",
    "location": "地点",
    "deadline": "报名截止",
}

_DATE_HINT_RE = re.compile(
    r"(今天|明天|后天|大后天|周[一二三四五六日天]|下周|本周|"
    r"\d{1,2}\s*[月\-/.]\s*\d{1,2})"
)

_SYNC_LOCKS: dict[str, threading.Lock] = {}
_SYNC_LOCKS_GUARD = threading.Lock()


def _lock_for(openid: str) -> threading.Lock:
    with _SYNC_LOCKS_GUARD:
        return _SYNC_LOCKS.setdefault(openid, threading.Lock())


def handle_text(
    conn,
    openid: str,
    text: str,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    now = ensure_aware(now or datetime.now(TZ))
    stripped = (text or "").strip()
    if not stripped:
        return _UNKNOWN

    pending = get_pending(conn, openid, now=now)
    if pending is not None and stripped in ("1", "0", "2"):
        return _handle_pending(conn, openid, pending, stripped, settings, now)

    command = parse_command(stripped)
    if command is None:
        return _UNKNOWN
    return _dispatch(conn, openid, command, settings, now)


def _dispatch(
    conn, openid: str, command: Command, settings: Settings, now: datetime
) -> str:
    kind = command.kind
    args = command.args

    if kind == "list":
        return _handle_list(conn, openid, settings, now, scope="future", reset=True)
    if kind == "list_all":
        return _handle_list(conn, openid, settings, now, scope="all", reset=True)
    if kind == "more":
        return _handle_more(conn, openid, settings, now)
    if kind in ("detail", "number"):
        return _handle_detail(conn, openid, int(args["short_no"]), settings, now)
    if kind == "edit":
        return _handle_edit(conn, openid, command, settings, now)
    if kind == "delete":
        return _handle_delete(conn, openid, args["short_nos"], settings, now)
    if kind == "sync":
        return _handle_sync(conn, openid, settings, now)
    if kind == "auto_sync":
        return _handle_auto_sync(conn, openid, args.get("value"), now)
    if kind == "result":
        return _handle_result(conn, openid)
    if kind == "help":
        return _HELP
    if kind == "config":
        return _handle_config(settings, openid)
    if kind == "config_done":
        return _handle_config_done(conn, openid, settings, now)
    if kind == "filter_conflict":
        return _handle_filter(conn, openid, "conflict", now)
    if kind == "filter_today":
        return _handle_filter(conn, openid, "today", now)
    if kind == "filter_tomorrow":
        return _handle_filter(conn, openid, "tomorrow", now)
    if kind == "filter_week":
        return _handle_filter(conn, openid, "week", now)
    if kind == "filter_next_week":
        return _handle_filter(conn, openid, "next_week", now)
    if kind == "keyword":
        return _handle_search(conn, openid, "keyword", args["value"], now)
    if kind == "search_location":
        return _handle_search(conn, openid, "location", args["value"], now)
    if kind == "readd":
        return _handle_readd(conn, openid, int(args["short_no"]), settings, now)
    if kind in ("undo", "clear", "remind", "default_remind"):
        return "该功能将在下一阶段接入。当前可用：列表 / 详情 / 改 / 删 / 同步。"
    return _UNKNOWN


def _handle_pending(
    conn,
    openid: str,
    pending: dict,
    digit: str,
    settings: Settings,
    now: datetime,
) -> str:
    kind = pending["kind"]
    payload = pending.get("payload") or {}

    if kind == "delete_confirm":
        short_nos = payload.get("short_nos") or []
        if digit == "0":
            consume_pending(conn, pending["id"], now=now)
            return "已取消删除。"
        if digit != "1":
            return "回复 1 确认删除，0 取消。"
        consume_pending(conn, pending["id"], now=now)
        return _apply_delete(conn, openid, short_nos, settings, now)

    if kind == "time_confirm":
        short_no = int(payload.get("short_no", 0))
        if digit == "2":
            consume_pending(conn, pending["id"], now=now)
            return f"回复 改 {short_no} 时间 11-27 19:00 修改为具体时间。"
        if digit == "0":
            consume_pending(conn, pending["id"], now=now)
            return "已取消确认，记录仍保留。"
        consume_pending(conn, pending["id"], now=now)
        update_activity(conn, openid, short_no, {}, sync_status="pending", now=now)
        if not is_calendar_enabled(settings, openid):
            return f"已确认 #{short_no}（演示模式，仅保存在微信内）。"
        return f"已确认 #{short_no}，将在下一轮同步写入系统日历。"

    consume_pending(conn, pending["id"], now=now)
    return "已取消。"


# ---------------------------------------------------------------------------
# 列表与详情
# ---------------------------------------------------------------------------


def _set_list_offset(conn, openid: str, offset: int, now: datetime) -> None:
    ensure_user_prefs(conn, openid, now)
    conn.execute(
        "UPDATE user_prefs SET list_offset = ?, updated_at = ? WHERE openid = ?",
        (offset, now.isoformat(), openid),
    )
    conn.commit()


def _handle_list(
    conn,
    openid: str,
    settings: Settings,
    now: datetime,
    *,
    scope: str,
    reset: bool,
    offset: int = 0,
) -> str:
    if reset:
        offset = 0

    if scope == "future":
        start = now
        end = now + timedelta(days=14)
        total = count_future(conn, openid, start, end)
        page = list_future(
            conn, openid, start, end, limit=_LIST_PAGE_SIZE, offset=offset
        )
        header = (
            f"📅 未来日程（{now:%m-%d} ~ {end:%m-%d}）共 {total} 条"
        )
    else:
        rows = list_all_active(conn, openid)
        total = len(rows)
        page = rows[offset : offset + _LIST_PAGE_SIZE]
        header = f"📅 全部日程 共 {total} 条"

    if total == 0:
        _set_list_offset(conn, openid, 0, now)
        return (
            "还没有记录任何活动。\n"
            "直接发送活动文字、公众号链接或海报截图，例如：\n"
            "周五晚7点 大礼堂 新生舞会"
        )

    if not page and offset > 0:
        _set_list_offset(conn, openid, offset, now)
        return "没有更多日程了。回复 列表 回到第一页。"

    conflicts = _conflict_map(conn, openid)
    lines = [header]
    for activity in page:
        lines.append(_list_item(activity, conflicts.get(activity["short_no"], [])))

    next_offset = offset + len(page)
    _set_list_offset(conn, openid, next_offset, now)

    if next_offset < total:
        lines.append(
            f"回复 #编号 看详情｜改｜删｜回复 更多 查看剩余 {total - next_offset} 条"
        )
    else:
        lines.append("回复 #编号 看详情｜改｜删")
    if not is_calendar_enabled(settings, openid):
        lines.append("🧪 演示模式：活动仅保存在微信内，不写入系统日历。")
    return "\n".join(lines)


def _handle_more(
    conn, openid: str, settings: Settings, now: datetime
) -> str:
    prefs = ensure_user_prefs(conn, openid, now)
    offset = int(prefs["list_offset"] or 0)
    return _handle_list(
        conn, openid, settings, now, scope="future", reset=False, offset=offset
    )


def _conflict_map(conn, openid: str) -> dict[int, list[int]]:
    from app.parsing.conflict import Span, find_conflicts

    spans = []
    for activity in list_all_active(conn, openid):
        start = parse_dt(activity.get("start_at"))
        if start is None:
            continue
        spans.append(
            Span(
                id=int(activity["short_no"]),
                start=start,
                end=parse_dt(activity.get("end_at")),
                all_day=bool(activity.get("all_day")),
            )
        )
    return find_conflicts(spans)


def _list_item(activity: dict, conflict_ids: list[int]) -> str:
    short_no = int(activity["short_no"])
    start = parse_dt(activity.get("start_at"))
    all_day = bool(activity.get("all_day"))
    if start is None:
        time_part = "时间待补"
    elif all_day:
        time_part = f"{format_day(start)} 全天"
    else:
        time_part = f"{format_day(start)} {start:%H:%M}"

    title = (activity.get("title") or "未命名活动")[:24]
    first = f"#{short_no} {time_part} {title}"

    meta: list[str] = []
    if activity.get("location"):
        meta.append(f"📍{activity['location']}")
    if conflict_ids:
        meta.append("⚠️" + "、".join(f"#{i}" for i in conflict_ids))
    meta.append(sync_icon(activity.get("sync_status")))
    return first + "\n   " + " ".join(meta)


def _handle_detail(
    conn,
    openid: str,
    short_no: int,
    settings: Settings,
    now: datetime,
) -> str:
    try:
        activity = get_activity(conn, openid, short_no)
    except KeyError:
        return f"未找到 #{short_no}，回复 列表 查看现有日程。"

    if activity.get("lifecycle") == "deleted":
        return f"#{short_no} 已删除。"

    start = parse_dt(activity.get("start_at"))
    end = parse_dt(activity.get("end_at"))
    all_day = bool(activity.get("all_day"))
    confidence = _load_json(activity.get("confidence"), {})
    title_confidence = float(confidence.get("title", 1) or 1)
    time_confidence = float(confidence.get("start_at", 0) or 0)

    title = activity.get("title") or "未命名活动"
    if title_confidence < 0.5:
        title += "（标题待确认）"
    lines = [f"#{short_no} {title}"]

    if start is None:
        lines.append("🕒 时间：未填写")
    else:
        lines.append(f"🕒 {format_time(start, end, all_day)}")
        if not all_day and end is None:
            lines.append("🕒 结束：未填写")

    lines.append(f"📍 地点：{activity.get('location') or '未填写'}")
    deadline = parse_dt(activity.get("deadline_at"))
    lines.append(
        f"⏰ 报名截止：{format_dt(deadline) if deadline else '未填写'}"
    )
    lines.append(f"📝 主办：{activity.get('organizer') or '未填写'}")

    if activity.get("source_url"):
        lines.append(f"🔗 原文：{activity['source_url']}")

    conflict_ids = get_conflict_ids(conn, openid, activity)
    if conflict_ids:
        parts = []
        for cid in conflict_ids:
            try:
                other = get_activity(conn, openid, cid)
            except KeyError:
                continue
            other_start = parse_dt(other.get("start_at"))
            when = (
                format_time(other_start, parse_dt(other.get("end_at")), bool(other.get("all_day")))
                if other_start
                else "时间待补"
            )
            parts.append(f"#{cid} {other.get('title')}（{when}）")
        if parts:
            lines.append("⚠️ 冲突：" + "、".join(parts))

    lines.append(f"⏰ 提醒：{_remind_text(activity)}")
    if is_calendar_enabled(settings, openid):
        lines.append(f"📤 同步：{sync_text(activity.get('sync_status'))}")
    else:
        lines.append("📤 同步：演示模式（仅微信内）")

    created = parse_dt(activity.get("created_at"))
    if created:
        lines.append(f"创建：{format_dt(created)}")

    if start is not None and time_confidence < settings.confidence_threshold:
        lines.append(
            f"⚠️ 时间置信度 {time_confidence:.2f}，回复 1 确认或 2 修改。"
        )

    lines.append(
        f"回复 改 {short_no} 时间 ...｜删 {short_no}｜提醒 {short_no} 提前1小时"
    )
    return "\n".join(lines)


def _remind_text(activity: dict) -> str:
    if activity.get("all_day"):
        return f"当天 {activity.get('remind_at') or '09:00'}"
    offsets = _load_json(activity.get("remind_offsets"), [-30, 0])
    if not isinstance(offsets, list) or not offsets:
        return "已关闭"
    parts = []
    for offset in offsets:
        offset = int(offset)
        if offset == 0:
            parts.append("开始时")
        elif offset < 0:
            parts.append(f"开始前 {abs(offset)} 分钟")
        else:
            parts.append(f"开始后 {offset} 分钟")
    return "、".join(parts)


# ---------------------------------------------------------------------------
# 修改与删除
# ---------------------------------------------------------------------------


def _handle_edit(
    conn,
    openid: str,
    command: Command,
    settings: Settings,
    now: datetime,
) -> str:
    short_no = int(command.args["short_no"])
    raw_field = command.args["field"]
    value = command.args["value"]
    field = resolve_field(raw_field)

    try:
        activity = get_activity(conn, openid, short_no)
    except KeyError:
        return f"未找到 #{short_no}，回复 列表 查看现有日程。"
    if activity.get("lifecycle") == "deleted":
        return f"#{short_no} 已删除。"

    if field is None:
        return (
            "没认出要改哪个字段。可用字段：\n"
            "名称 / 时间 / 结束 / 地点 / 报名截止\n"
            "示例：改 3 时间 11-27 19:30"
        )

    old_start = parse_dt(activity.get("start_at"))
    old_end = parse_dt(activity.get("end_at"))
    fields: dict = {}

    if field == "start":
        normalized = normalize_time_expression(value, now)
        if normalized.unresolved or normalized.start is None:
            return (
                "时间格式没看懂。示例：\n"
                "改 3 时间 11-27 19:30\n"
                "改 3 时间 明天下午2点\n"
                "改 3 时间 周六（全天）"
            )
        new_start = normalized.start
        # 「改 2 时间 20:30」这种只给时刻的写法，保留原活动日期
        if (
            old_start is not None
            and not normalized.all_day
            and not _DATE_HINT_RE.search(value)
        ):
            new_start = datetime.combine(
                old_start.date(), normalized.start.time(), tzinfo=TZ
            )
        new_end = normalized.end
        if normalized.all_day:
            new_end = new_start + timedelta(days=1)
        elif new_end is None and old_end is not None and old_start is not None:
            new_end = old_end + (new_start - old_start)
        fields = {
            "start_at": new_start.isoformat(),
            "end_at": new_end.isoformat() if new_end else None,
            "all_day": 1 if normalized.all_day else 0,
        }
    elif field == "end":
        normalized = normalize_time_expression(value, now)
        new_end = normalized.start or normalized.end
        if normalized.unresolved or new_end is None:
            return "结束时间格式没看懂。示例：改 3 结束 11-27 21:00"
        if old_end is not None and not _DATE_HINT_RE.search(value):
            new_end = datetime.combine(
                old_end.date(), new_end.time(), tzinfo=TZ
            )
        if old_start is not None and new_end <= old_start:
            return "结束时间必须晚于开始时间。"
        fields = {"end_at": new_end.isoformat()}
    elif field == "deadline":
        normalized = normalize_time_expression(value, now)
        if normalized.unresolved or normalized.start is None:
            return "报名截止格式没看懂。示例：改 3 报名截止 11-25 23:59"
        deadline = (
            datetime.combine(normalized.start.date(), time(23, 59), tzinfo=TZ)
            if normalized.all_day
            else normalized.start
        )
        fields = {"deadline_at": deadline.isoformat()}
    elif field == "title":
        title = value.strip()
        if not title:
            return "名称不能为空。示例：改 3 名称 新生舞会"
        fields = {"title": title[:100]}
    elif field == "location":
        location = value.strip()
        if not location:
            return "地点不能为空。示例：改 3 地点 大礼堂"
        fields = {"location": location[:100]}
    else:
        return "该字段暂不支持修改。可用：名称 / 时间 / 结束 / 地点 / 报名截止。"

    start_after = parse_dt(fields.get("start_at", activity.get("start_at")))
    if start_after is None:
        new_sync = "not_synced"
    elif activity.get("sync_status") in ("synced", "update_pending"):
        new_sync = "update_pending"
    else:
        new_sync = "pending"

    updated = update_activity(
        conn, openid, short_no, fields, sync_status=new_sync, now=now
    )

    label = _FIELD_LABELS.get(field, field)
    old_display = _field_value(activity, field)
    new_display = _field_value(updated, field)
    lines = [
        f"✏️ 已更新 #{short_no}",
        f"{label}：{old_display} → {new_display}",
    ]
    if not is_calendar_enabled(settings, openid):
        lines.append("演示模式：仅保存在微信内，不写入系统日历。")
    elif new_sync == "update_pending":
        lines.append("将在下一轮同步更新系统日历。")
    elif new_sync == "pending":
        lines.append("将在下一轮同步写入系统日历。")
    else:
        lines.append("补全时间后才会写入系统日历。")

    conflicts = get_conflict_ids(conn, openid, updated)
    if conflicts:
        lines.append(
            "⚠️ 现在与 " + "、".join(f"#{i}" for i in conflicts) + " 冲突"
        )
    return "\n".join(lines)


def _field_value(activity: dict, field: str) -> str:
    start = parse_dt(activity.get("start_at"))
    end = parse_dt(activity.get("end_at"))
    if field == "start":
        if start is None:
            return "未填写"
        return format_time(start, end, bool(activity.get("all_day")))
    if field == "end":
        return format_dt(end) if end else "未填写"
    if field == "deadline":
        deadline = parse_dt(activity.get("deadline_at"))
        return format_dt(deadline) if deadline else "未填写"
    if field == "title":
        return activity.get("title") or "未填写"
    if field == "location":
        return activity.get("location") or "未填写"
    return "未填写"


def _handle_delete(
    conn,
    openid: str,
    short_nos: list[int],
    settings: Settings,
    now: datetime,
) -> str:
    found: list[dict] = []
    missing: list[int] = []
    for short_no in short_nos:
        try:
            activity = get_activity(conn, openid, short_no)
        except KeyError:
            missing.append(short_no)
            continue
        if activity.get("lifecycle") != "active":
            missing.append(short_no)
            continue
        found.append(activity)

    if missing and not found:
        return "未找到 " + "、".join(f"#{i}" for i in missing) + "。"

    if not found:
        return "未找到这些活动。"

    if is_calendar_enabled(settings, openid):
        tail = "删除后将同时从系统日历移除。"
    else:
        tail = "删除后将从微信记录中移除（演示模式不涉及系统日历）。"

    if len(found) == 1:
        activity = found[0]
        when = format_time(
            parse_dt(activity.get("start_at")),
            parse_dt(activity.get("end_at")),
            bool(activity.get("all_day")),
        )
        confirm = (
            f"确认删除 #{activity['short_no']} {activity.get('title')}（{when}）？\n"
            f"{tail}\n"
            "回复 1 确认，0 取消。"
        )
    else:
        lines = [f"确认删除以下活动？{tail}"]
        for activity in found:
            lines.append(f"#{activity['short_no']} {activity.get('title')}")
        lines.append("回复 1 确认，0 取消。")
        confirm = "\n".join(lines)

    create_pending(
        conn,
        openid,
        "delete_confirm",
        {"short_nos": [int(a["short_no"]) for a in found]},
        now=now,
    )
    if missing:
        confirm += "\n未找到：" + "、".join(f"#{i}" for i in missing)
    return confirm


def _apply_delete(
    conn,
    openid: str,
    short_nos: list[int],
    settings: Settings,
    now: datetime,
) -> str:
    deleted: list[int] = []
    needs_sync = False

    for short_no in short_nos:
        try:
            activity = get_activity(conn, openid, short_no)
        except KeyError:
            continue
        if activity.get("lifecycle") != "active":
            continue
        updated = soft_delete(conn, openid, short_no, now=now)
        deleted.append(short_no)
        if updated.get("sync_status") == "delete_pending":
            needs_sync = True

    if not deleted:
        return "没有可删除的活动。"

    ids = "、".join(f"#{i}" for i in deleted)
    if not needs_sync:
        return f"已删除 {ids}。"

    try:
        from app.calendar.sync import sync_openid

        counts = sync_openid(conn, openid, settings, now=now)
    except Exception:
        return f"已删除 {ids}，但日历删除失败，回复 同步 重试。"

    if counts.get("failed", 0) == 0:
        return f"已删除 {ids}，并已从系统日历移除。"
    return f"已删除 {ids}，但日历删除失败，回复 同步 重试。"


# ---------------------------------------------------------------------------
# 同步、配置、帮助
# ---------------------------------------------------------------------------


def _handle_sync(conn, openid: str, settings: Settings, now: datetime) -> str:
    if not is_calendar_enabled(settings, openid):
        return (
            "🧪 现场演示模式：日历同步仅对演示账号开放。\n"
            "你可以在微信里完整体验记录、列表、修改和删除；"
            "活动只保存在微信内。"
        )
    if not settings.caldav_password:
        return "还没有配置日历账户。回复 配置 查看一次性配置步骤。"
    if not settings.caldav_username:
        return "日历账户用户名未配置，请检查 .env。"

    lock = _lock_for(openid)
    if not lock.acquire(blocking=False):
        return "同步进行中，请稍候。"

    try:
        from app.calendar.sync import sync_openid

        # 用户主动同步时，把上次失败的项重新纳入本轮；已删除的仍走删除
        conn.execute(
            """
            UPDATE activities
            SET sync_status = CASE WHEN lifecycle = 'deleted'
                THEN 'delete_pending' ELSE 'pending' END
            WHERE openid = ? AND sync_status = 'failed'
            """,
            (openid,),
        )
        conn.commit()
        counts = sync_openid(conn, openid, settings, now=now)
    except Exception:
        return "同步失败：无法连接日历服务。回复 同步 重试。"
    finally:
        lock.release()

    total = counts.get("created", 0) + counts.get("updated", 0) + counts.get("deleted", 0)
    if total == 0 and counts.get("failed", 0) == 0:
        return "当前无待同步项。"

    lines = [
        "🔄 同步完成",
        f"新增 {counts.get('created', 0)}｜更新 {counts.get('updated', 0)}"
        f"｜删除 {counts.get('deleted', 0)}｜失败 {counts.get('failed', 0)}",
    ]
    if counts.get("failed"):
        failed = "、".join(f"#{i}" for i in counts.get("failed_ids", []))
        lines.append(f"失败：{failed}，回复 同步 重试。")
    return "\n".join(lines)


def _handle_auto_sync(conn, openid: str, value: str | None, now: datetime) -> str:
    prefs = ensure_user_prefs(conn, openid, now)
    if value is None:
        state = "开启" if prefs["auto_sync_enabled"] else "关闭"
        return f"自动同步当前：{state}。回复 自动同步 开/关 切换。"
    enabled = 1 if value == "开" else 0
    conn.execute(
        "UPDATE user_prefs SET auto_sync_enabled = ?, updated_at = ? WHERE openid = ?",
        (enabled, now.isoformat(), openid),
    )
    conn.commit()
    return f"自动同步已{'开启，10 分钟内处理待同步项。' if enabled else '关闭，新建活动不会自动进入系统日历。'}"


def _handle_config(settings: Settings, openid: str) -> str:
    if not is_calendar_enabled(settings, openid):
        return (
            "🧪 现场演示模式：\n"
            "你可以完整体验：发活动、收卡片、列表、详情、改、删。\n"
            "系统日历同步仅对演示账号开放；你的活动只保存在微信内。"
        )
    base = (settings.public_base_url or "").rstrip("/")
    caldav = f"{base}/radicale/"
    return (
        "📱 一次性配置系统日历（只需一次）\n"
        "1. Android 安装 DAVx5\n"
        "2. 添加账户 → 使用 URL 和用户名登录\n"
        f"   地址：{caldav}\n"
        f"   用户名：{settings.caldav_username or 'sdg'}\n"
        "   密码：向管理员获取（不通过微信发送）\n"
        "3. 勾选「日程Agent」日历，开启同步\n"
        "4. 在系统日历中勾选该日历，并允许通知\n"
        "5. 完成后回复 配置完成，我会写入一条 2 分钟后的测试事件\n"
        "在系统日历中删除事件不会同步回微信。"
    )


def _handle_config_done(
    conn, openid: str, settings: Settings, now: datetime
) -> str:
    if not is_calendar_enabled(settings, openid):
        return (
            "🧪 现场演示模式：日历同步仅对演示账号开放。\n"
            "你的活动会保存在微信内，可体验卡片、列表、修改和删除。"
        )

    start = now + timedelta(minutes=2)
    parsed = ParsedActivity(
        title="系统日历测试",
        start_at=start,
        end_at=start + timedelta(hours=1),
        all_day=False,
        location=None,
        deadline_at=None,
        organizer=None,
        notes=None,
        confidence={"start_at": 1.0, "title": 1.0},
        time_basis="配置测试",
    )
    activity = insert_activity(
        conn, openid, parsed, settings, source_type="text", now=now
    )

    try:
        from app.calendar.sync import sync_openid

        counts = sync_openid(conn, openid, settings, now=now)
    except Exception:
        return "测试事件写入失败：无法连接日历服务。回复 同步 重试。"

    if counts.get("failed"):
        return "测试事件写入失败，请检查 DAVx5 与日历服务。回复 同步 重试。"

    return (
        f"已写入测试事件 #{activity['short_no']}（2 分钟后）。\n"
        "请在 DAVx5 里点一次「立即同步」，然后查看系统日历。\n"
        "2 分钟后应收到系统提醒。\n"
        "若没有：检查日历通知权限、电池优化、系统日历是否勾选该账户。"
    )


def _handle_result(conn, openid: str) -> str:
    row = conn.execute(
        """
        SELECT result_text FROM messages
        WHERE openid = ? AND result_text IS NOT NULL AND result_text <> ''
        ORDER BY created_at DESC LIMIT 1
        """,
        (openid,),
    ).fetchone()
    if row and row["result_text"]:
        return row["result_text"]
    return "还没有可展示的解析结果，请先发送活动文字。"


def _handle_readd(
    conn, openid: str, short_no: int, settings: Settings, now: datetime
) -> str:
    if not is_calendar_enabled(settings, openid):
        return "🧪 演示模式：日历同步仅对演示账号开放。"
    try:
        activity = get_activity(conn, openid, short_no)
    except KeyError:
        return f"未找到 #{short_no}。"
    if activity.get("sync_status") == "delete_pending":
        return f"#{short_no} 正在删除，不能重新加回。"
    update_activity(
        conn, openid, short_no, {}, sync_status="update_pending", now=now
    )
    return f"已安排重新写入系统日历，回复 同步 立即执行。"


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------


def _handle_filter(conn, openid: str, kind: str, now: datetime) -> str:
    rows = list_all_active(conn, openid)
    conflicts = _conflict_map(conn, openid)

    if kind == "today":
        label = f"今天（{now:%m-%d}）"
        selected = [
            a
            for a in rows
            if parse_dt(a.get("start_at")) is not None
            and parse_dt(a["start_at"]).date() == now.date()
        ]
    elif kind == "tomorrow":
        target = now.date() + timedelta(days=1)
        label = f"明天（{target:%m-%d}）"
        selected = [
            a
            for a in rows
            if parse_dt(a.get("start_at")) is not None
            and parse_dt(a["start_at"]).date() == target
        ]
    elif kind in ("week", "next_week"):
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if kind == "next_week":
            monday += timedelta(days=7)
        end = monday + timedelta(days=7)
        label = f"{'下周' if kind == 'next_week' else '本周'}（{monday:%m-%d} ~ {end - timedelta(days=1):%m-%d}）"
        selected = [
            a
            for a in rows
            if parse_dt(a.get("start_at")) is not None
            and monday <= parse_dt(a["start_at"]) < end
        ]
    else:
        label = "冲突日程"
        selected = [a for a in rows if conflicts.get(a["short_no"])]

    if not selected:
        return f"{label}没有日程。"

    lines = [f"📅 {label} 共 {len(selected)} 条"]
    for activity in selected:
        lines.append(_list_item(activity, conflicts.get(activity["short_no"], [])))
    lines.append("回复 #编号 看详情｜改｜删")
    return "\n".join(lines)


def _handle_search(
    conn, openid: str, kind: str, value: str, now: datetime
) -> str:
    value = value.strip()
    if not value:
        return "请给出关键词。示例：关键词 讲座｜地点 大礼堂"
    rows = list_all_active(conn, openid)
    conflicts = _conflict_map(conn, openid)
    selected = []
    for activity in rows:
        haystack = " ".join(
            str(activity.get(key) or "")
            for key in ("title", "location", "notes")
        )
        if value in haystack:
            selected.append(activity)

    if not selected:
        return f"没有找到包含「{value}」的日程。"

    lines = [f"🔍 「{value}」共 {len(selected)} 条"]
    for activity in selected:
        lines.append(_list_item(activity, conflicts.get(activity["short_no"], [])))
    lines.append("回复 #编号 看详情｜改｜删")
    return "\n".join(lines)


def _load_json(value, default):
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed
    except (TypeError, ValueError):
        return default
