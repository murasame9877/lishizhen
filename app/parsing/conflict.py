"""冲突检测（PRD FR-12 / 8.2）。

- 冲突是派生状态，不落库；
- 仅定时活动参与硬冲突判定，半开区间 [start, end)；
- 全天活动与同日定时活动只做「同日多活动」提示；
- end 缺失时仅用于冲突计算，按默认 2 小时估算，不写回记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DURATION = timedelta(hours=2)

__all__ = [
    "TZ",
    "DEFAULT_DURATION",
    "Span",
    "effective_end",
    "find_conflicts",
    "find_same_day_groups",
]


@dataclass(frozen=True)
class Span:
    id: int
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    lifecycle: str = "active"


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def effective_end(span: Span) -> datetime:
    if span.end is not None:
        return _aware(span.end)
    return _aware(span.start) + DEFAULT_DURATION


def _overlap(a: Span, b: Span) -> bool:
    a_start, a_end = _aware(a.start), effective_end(a)
    b_start, b_end = _aware(b.start), effective_end(b)
    return a_start < b_end and b_start < a_end


def find_conflicts(spans: list[Span]) -> dict[int, list[int]]:
    """返回 {活动 id: [冲突 id, ...]}，只包含存在硬冲突的活动。"""
    active = [
        s
        for s in spans
        if s.lifecycle == "active" and not s.all_day and s.start is not None
    ]
    by_day: dict[date, list[Span]] = {}
    for s in active:
        by_day.setdefault(_aware(s.start).date(), []).append(s)

    result: dict[int, list[int]] = {}
    for items in by_day.values():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if _overlap(a, b):
                    result.setdefault(a.id, []).append(b.id)
                    result.setdefault(b.id, []).append(a.id)

    return {k: sorted(set(v)) for k, v in result.items()}


def find_same_day_groups(spans: list[Span]) -> dict[date, list[int]]:
    """同日（含全天）活动分组，用于「同日多活动」轻提示。"""
    groups: dict[date, list[int]] = {}
    for s in spans:
        if s.lifecycle != "active" or s.start is None:
            continue
        groups.setdefault(_aware(s.start).date(), []).append(s.id)
    return {d: sorted(ids) for d, ids in groups.items() if len(ids) > 1}
