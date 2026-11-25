"""中文活动时间归一化（PRD FR-08）。

设计原则：
- 时区固定 Asia/Shanghai；
- 基准时间由调用方注入，便于测试与消息回溯；
- 不做猜测性填充：无法确定时返回 unresolved 或低置信度；
- 返回 basis 供回复文案回显推断依据（PRD FR-08 AC2）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")

__all__ = ["TZ", "NormalizedTime", "normalize_time_expression", "ensure_aware"]

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------

_UNRESOLVED_RE = re.compile(r"待定|另行通知|未定|暂无|TBD|TBC", re.IGNORECASE)
_ALL_DAY_RE = re.compile(r"全天|整天|全天候|一整天")

_FULL_DATE_RE = re.compile(
    r"(?<!\d)(?P<y>20\d{2})\s*[年\-/.]\s*(?P<m>1[0-2]|0?[1-9])\s*[月\-/.]\s*"
    r"(?P<d>3[01]|[12]\d|0?[1-9])\s*日?"
)
_MONTH_DAY_RE = re.compile(
    r"(?<![\d:])(?P<m>1[0-2]|0?[1-9])\s*[月\-/.]\s*"
    r"(?P<d>3[01]|[12]\d|0?[1-9])\s*日?(?![\d:])"
)
_RELATIVE_DAY_RE = re.compile(
    r"(?P<word>大后天|后天|明晚|明早|明下午|明天|明日|今晚|今早|今下午|今晚上|今天|今日)"
)
_WEEKDAY_RE = re.compile(
    r"(?:(?P<prefix>下下|下|本|这)(?:个)?)?(?:周|星期|礼拜)(?P<wd>[一二三四五六日天1-7])"
)

_COLON_RANGE_RE = re.compile(
    r"(?<!\d)(?P<h1>\d{1,2}):(?P<m1>\d{2})\s*(?:-|~|—|–|至|到)\s*"
    r"(?P<cross>次日|第二天|翌日)?\s*(?P<h2>\d{1,2}):(?P<m2>\d{2})(?!\d)"
)
_DIAN_RANGE_RE = re.compile(
    r"(?<!\d)(?P<h1>\d{1,2})点(?P<min1>半|\d{1,2}分?)?\s*(?:-|~|—|–|至|到)\s*"
    r"(?P<cross>次日|第二天|翌日)?\s*(?P<h2>\d{1,2})点(?P<min2>半|\d{1,2}分?)?"
)
_COLON_SINGLE_RE = re.compile(r"(?<!\d)(?P<h>\d{1,2}):(?P<m>\d{2})(?!\d)")
_DIAN_SINGLE_RE = re.compile(r"(?<!\d)(?P<h>\d{1,2})点(?P<min>半|\d{1,2}分?)?")

_PERIOD_RE = re.compile(r"凌晨|早上|上午|中午|下午|傍晚|晚上|晚|夜里|夜间")
_EVENING_PERIODS = {"下午", "傍晚", "晚上", "晚", "夜里", "夜间"}

_WD_INDEX = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}
_WD_NAME = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

_RELATIVE_OFFSET = {
    "今天": 0, "今日": 0, "今晚": 0, "今早": 0, "今下午": 0, "今晚上": 0,
    "明天": 1, "明日": 1, "明晚": 1, "明早": 1, "明下午": 1,
    "后天": 2,
    "大后天": 3,
}


@dataclass(frozen=True)
class NormalizedTime:
    start: datetime | None
    end: datetime | None
    all_day: bool
    confidence: float
    basis: str
    unresolved: bool = False
    is_past: bool = False


@dataclass(frozen=True)
class _TimeParse:
    has_time: bool
    start: time | None = None
    end: time | None = None
    cross_day: bool = False


@dataclass(frozen=True)
class _DateParse:
    value: date | None
    kind: str  # explicit | relative | weekday | none
    confidence: float
    basis: str


def ensure_aware(dt: datetime, tz: ZoneInfo = TZ) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _valid_hm(hour: int, minute: int) -> bool:
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _minute(token: str | None) -> int:
    if not token:
        return 0
    if token == "半":
        return 30
    digits = re.sub(r"\D", "", token)
    return int(digits) if digits else 0


def _period_before(text: str, pos: int) -> str | None:
    """取时间表达之前最近的一个时段词；没有则取文中第一个。"""
    found: str | None = None
    for m in _PERIOD_RE.finditer(text):
        if m.start() <= pos:
            found = m.group(0)
        else:
            break
    if found is None:
        m = _PERIOD_RE.search(text)
        found = m.group(0) if m else None
    return found


def _to_24h(hour: int, period: str | None) -> int:
    if period in _EVENING_PERIODS and hour < 12:
        return hour + 12
    if period == "中午" and hour < 11:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def _parse_time(text: str) -> _TimeParse:
    # 1) 19:00-21:00 / 19:00至次日1:00
    m = _COLON_RANGE_RE.search(text)
    if m:
        h1, m1 = int(m["h1"]), int(m["m1"])
        h2, m2 = int(m["h2"]), int(m["m2"])
        if _valid_hm(h1, m1) and _valid_hm(h2, m2):
            cross = bool(m["cross"]) or (h2, m2) <= (h1, m1)
            return _TimeParse(True, time(h1, m1), time(h2, m2), cross)

    # 2) 晚7点到9点 / 下午2点至4点
    m = _DIAN_RANGE_RE.search(text)
    if m:
        period = _period_before(text, m.start())
        h1 = _to_24h(int(m["h1"]), period)
        h2 = _to_24h(int(m["h2"]), period)
        m1, m2 = _minute(m["min1"]), _minute(m["min2"])
        if _valid_hm(h1, m1) and _valid_hm(h2, m2):
            cross = bool(m["cross"]) or (h2, m2) <= (h1, m1)
            return _TimeParse(True, time(h1, m1), time(h2, m2), cross)

    # 3) 单个 19:30
    m = _COLON_SINGLE_RE.search(text)
    if m:
        h, minute = int(m["h"]), int(m["m"])
        if _valid_hm(h, minute):
            return _TimeParse(True, time(h, minute), None, False)

    # 4) 单个 晚7点 / 下午2点
    m = _DIAN_SINGLE_RE.search(text)
    if m:
        period = _period_before(text, m.start())
        h = _to_24h(int(m["h"]), period)
        minute = _minute(m["min"])
        if _valid_hm(h, minute):
            return _TimeParse(True, time(h, minute), None, False)

    return _TimeParse(False)


def _parse_date(text: str, base: datetime) -> _DateParse:
    base_day = base.date()

    m = _FULL_DATE_RE.search(text)
    if m:
        d = date(int(m["y"]), int(m["m"]), int(m["d"]))
        return _DateParse(d, "explicit", 0.97, f"日期按原文 {d.isoformat()} 识别")

    m = _MONTH_DAY_RE.search(text)
    if m:
        year = base.year
        d = date(year, int(m["m"]), int(m["d"]))
        # 跨年：原文日期已过去很久（>30 天）时按明年理解
        if d < base_day - timedelta(days=30):
            d = date(year + 1, int(m["m"]), int(m["d"]))
        return _DateParse(d, "explicit", 0.95, f"日期按原文 {d.isoformat()} 识别")

    m = _RELATIVE_DAY_RE.search(text)
    if m:
        word = m.group("word")
        d = base_day + timedelta(days=_RELATIVE_OFFSET[word])
        return _DateParse(d, "relative", 0.92, f"日期按「{word}」推断为 {d.isoformat()}")

    m = _WEEKDAY_RE.search(text)
    if m:
        prefix = m.group("prefix")
        idx = _WD_INDEX[m.group("wd")]
        monday = base_day - timedelta(days=base_day.weekday())
        if prefix == "下下":
            d = monday + timedelta(days=14 + idx)
            basis = f"日期按「下下周{_WD_NAME[idx][1:]}」推断为 {d.isoformat()}"
        elif prefix == "下":
            d = monday + timedelta(days=7 + idx)
            basis = f"日期按「下周{_WD_NAME[idx][1:]}」推断为 {d.isoformat()}"
        elif prefix in ("本", "这"):
            d = monday + timedelta(days=idx)
            if d < base_day:
                d += timedelta(days=7)
                basis = f"本周该日已过，顺延到 {d.isoformat()}（{_WD_NAME[idx]}）"
            else:
                basis = f"日期按「本周{_WD_NAME[idx][1:]}」推断为 {d.isoformat()}"
        else:
            delta = (idx - base_day.weekday()) % 7
            d = base_day + timedelta(days=delta)
            basis = f"日期按最近的{_WD_NAME[idx]}推断为 {d.isoformat()}"
        return _DateParse(d, "weekday", 0.88, basis)

    return _DateParse(None, "none", 0.0, "")


def normalize_time_expression(
    expr: str,
    base: datetime | None = None,
) -> NormalizedTime:
    """把一段中文时间表达归一化为 Asia/Shanghai 的绝对时间。

    base 是消息到达时间，测试时应显式注入。
    """
    text = (expr or "").strip()
    base = ensure_aware(base or datetime.now(TZ))

    if not text or _UNRESOLVED_RE.search(text):
        return NormalizedTime(
            None, None, False, 0.0, "时间待定，需补充具体时间", unresolved=True
        )

    dp = _parse_date(text, base)
    tp = _parse_time(text)
    explicit_all_day = bool(_ALL_DAY_RE.search(text))

    if dp.value is None and not tp.has_time:
        return NormalizedTime(
            None, None, False, 0.0, "未识别到日期与时间，需补充", unresolved=True
        )

    d = dp.value or base.date()
    all_day = explicit_all_day or (dp.value is not None and not tp.has_time)

    basis_parts: list[str] = []
    if dp.basis:
        basis_parts.append(dp.basis)
    if dp.value is None and tp.has_time:
        basis_parts.append("未识别到日期，暂按今天推断")
    if all_day and not explicit_all_day:
        basis_parts.append("只有日期没有具体时刻，按全天处理")
    if explicit_all_day:
        basis_parts.append("原文标注全天")
    if tp.cross_day:
        basis_parts.append("结束时间早于开始时间，按跨天处理")

    if all_day:
        start = datetime.combine(d, time(0, 0), tzinfo=TZ)
        end = start + timedelta(days=1)
        is_past = d < base.date()
        if dp.kind == "explicit":
            confidence = 0.85 if explicit_all_day else 0.70
        elif dp.kind == "weekday":
            confidence = 0.62
        elif dp.kind == "relative":
            confidence = 0.75
        else:
            confidence = 0.40
    else:
        assert tp.start is not None
        start = datetime.combine(d, tp.start, tzinfo=TZ)
        end = None
        if tp.end is not None:
            end_date = d + timedelta(days=1) if tp.cross_day else d
            end = datetime.combine(end_date, tp.end, tzinfo=TZ)
            if end <= start:
                end = datetime.combine(d + timedelta(days=1), tp.end, tzinfo=TZ)
                basis_parts.append("结束时间不晚于开始时间，按次日处理")
        is_past = start < base
        confidence = dp.confidence if dp.value is not None else 0.45

    if is_past:
        basis_parts.append("该时间已过去，请确认")

    basis = "；".join(dict.fromkeys(basis_parts)) or "按原文识别"

    return NormalizedTime(
        start=start,
        end=end,
        all_day=all_day,
        confidence=confidence,
        basis=basis,
        unresolved=False,
        is_past=is_past,
    )
