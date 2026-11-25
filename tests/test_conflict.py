from datetime import datetime, timedelta

from app.parsing.conflict import TZ, Span, find_conflicts, find_same_day_groups


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def test_overlapping_events_conflict_both_ways():
    spans = [
        Span(1, dt(27, 19, 0), dt(27, 21, 0)),
        Span(2, dt(27, 20, 0), dt(27, 22, 0)),
    ]
    assert find_conflicts(spans) == {1: [2], 2: [1]}


def test_adjacent_events_do_not_conflict():
    spans = [
        Span(1, dt(27, 19, 0), dt(27, 21, 0)),
        Span(2, dt(27, 21, 0), dt(27, 23, 0)),
    ]
    assert find_conflicts(spans) == {}


def test_all_day_is_not_hard_conflict():
    spans = [
        Span(1, dt(27, 0, 0), dt(28, 0, 0), all_day=True),
        Span(2, dt(27, 19, 0), dt(27, 21, 0)),
    ]
    assert find_conflicts(spans) == {}
    assert find_same_day_groups(spans) == {dt(27, 0, 0).date(): [1, 2]}


def test_deleted_activity_is_ignored():
    spans = [
        Span(1, dt(27, 19, 0), dt(27, 21, 0), lifecycle="deleted"),
        Span(2, dt(27, 20, 0), dt(27, 22, 0)),
    ]
    assert find_conflicts(spans) == {}


def test_missing_end_uses_default_duration_for_conflict_only():
    spans = [
        Span(1, dt(27, 19, 0)),  # 默认按 2 小时
        Span(2, dt(27, 20, 0), dt(27, 22, 0)),
    ]
    assert find_conflicts(spans) == {1: [2], 2: [1]}


def test_different_days_do_not_conflict():
    spans = [
        Span(1, dt(27, 19, 0), dt(27, 21, 0)),
        Span(2, dt(28, 19, 0), dt(28, 21, 0)),
    ]
    assert find_conflicts(spans) == {}
