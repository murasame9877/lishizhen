"""微信对话框指令解析（PRD 第 7 章）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["Command", "parse_command", "resolve_field", "FIELD_ALIASES"]


@dataclass(frozen=True)
class Command:
    kind: str
    args: dict = field(default_factory=dict)


FIELD_ALIASES: dict[str, str] = {
    "活动名称": "title",
    "报名截止时间": "deadline",
    "什么时候": "start",
    "活动名": "title",
    "报名截止": "deadline",
    "提醒时间": "remind",
    "提前多久": "remind",
    "标题": "title",
    "名称": "title",
    "名字": "title",
    "时间": "start",
    "开始": "start",
    "日期": "start",
    "结束": "end",
    "到几点": "end",
    "地点": "location",
    "地址": "location",
    "在哪里": "location",
    "场地": "location",
    "截止": "deadline",
    "ddl": "deadline",
    "提醒": "remind",
}

_EXACT: dict[str, str] = {
    "列表": "list",
    "日程": "list",
    "我的日程": "list",
    "更多": "more",
    "下一页": "more",
    "全部": "list_all",
    "帮助": "help",
    "?": "help",
    "？": "help",
    "配置": "config",
    "配置完成": "config_done",
    "结果": "result",
    "最新结果": "result",
    "同步": "sync",
    "立即同步": "sync",
    "撤销": "undo",
    "冲突": "filter_conflict",
    "今天": "filter_today",
    "明天": "filter_tomorrow",
    "本周": "filter_week",
    "下周": "filter_next_week",
}

_EDIT_RE = re.compile(r"^改\s*(\d+)\s*(\S+)\s*(.+)$")
_DETAIL_HASH_RE = re.compile(r"^[#＃](\d+)$")
_DETAIL_WORD_RE = re.compile(r"^详情\s*(\d+)$")
_NUMBER_RE = re.compile(r"^(\d+)$")
_DELETE_RE = re.compile(r"^删\s*([\d,，\s]+)$")
_AUTO_SYNC_RE = re.compile(r"^自动同步\s*(开|关)?$")
_KEYWORD_RE = re.compile(r"^关键词\s*(.+)$")
_LOCATION_RE = re.compile(r"^地点\s*(.+)$")
_READD_RE = re.compile(r"^重新加回\s*(\d+)$")
_REMIND_RE = re.compile(r"^提醒\s*(\d+)\s*(.+)$")
_DEFAULT_REMIND_RE = re.compile(r"^默认提醒\s*(.+)$")
_CLEAR_RE = re.compile(r"^清空(本周|全部)$")


def resolve_field(value: str) -> str | None:
    value = value.strip()
    if value in FIELD_ALIASES:
        return FIELD_ALIASES[value]
    for alias in sorted(FIELD_ALIASES, key=len, reverse=True):
        if value.startswith(alias):
            return FIELD_ALIASES[alias]
    return None


def _parse_numbers(value: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", value)]


def parse_command(text: str) -> Command | None:
    text = (text or "").strip()
    if not text:
        return None

    if text in _EXACT:
        return Command(_EXACT[text])

    match = _EDIT_RE.match(text)
    if match:
        return Command(
            "edit",
            {
                "short_no": int(match.group(1)),
                "field": match.group(2),
                "value": match.group(3).strip(),
            },
        )

    match = _DETAIL_HASH_RE.match(text) or _DETAIL_WORD_RE.match(text)
    if match:
        return Command("detail", {"short_no": int(match.group(1))})

    match = _NUMBER_RE.match(text)
    if match:
        return Command("number", {"short_no": int(match.group(1))})

    match = _DELETE_RE.match(text)
    if match:
        numbers = _parse_numbers(match.group(1))
        if numbers:
            return Command("delete", {"short_nos": numbers})

    match = _AUTO_SYNC_RE.match(text)
    if match:
        return Command("auto_sync", {"value": match.group(1)})

    match = _KEYWORD_RE.match(text)
    if match:
        return Command("keyword", {"value": match.group(1).strip()})

    match = _LOCATION_RE.match(text)
    if match:
        return Command("search_location", {"value": match.group(1).strip()})

    match = _READD_RE.match(text)
    if match:
        return Command("readd", {"short_no": int(match.group(1))})

    match = _REMIND_RE.match(text)
    if match:
        return Command(
            "remind",
            {"short_no": int(match.group(1)), "value": match.group(2).strip()},
        )

    match = _DEFAULT_REMIND_RE.match(text)
    if match:
        return Command("default_remind", {"value": match.group(1).strip()})

    match = _CLEAR_RE.match(text)
    if match:
        return Command("clear", {"scope": match.group(1)})

    return None
