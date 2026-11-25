from datetime import datetime

from app.parsing.time_norm import TZ, normalize_time_expression

# PRD FR-08 的基准日：2026-11-22，周日
BASE = datetime(2026, 11, 22, 10, 0, tzinfo=TZ)


def test_tomorrow_afternoon():
    r = normalize_time_expression("明天下午2点", BASE)
    assert r.start == datetime(2026, 11, 23, 14, 0, tzinfo=TZ)
    assert r.end is None
    assert not r.all_day
    assert r.confidence >= 0.8
    assert "明天" in r.basis


def test_explicit_date_range():
    r = normalize_time_expression("11月27日 19:00-21:00", BASE)
    assert r.start == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert r.end == datetime(2026, 11, 27, 21, 0, tzinfo=TZ)
    assert not r.all_day
    assert r.confidence >= 0.8


def test_friday_evening():
    r = normalize_time_expression("周五晚7点", BASE)
    assert r.start == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert r.end is None
    assert not r.all_day
    assert r.confidence >= 0.8


def test_next_wednesday():
    r = normalize_time_expression("下周三", BASE)
    assert r.start == datetime(2026, 11, 25, 0, 0, tzinfo=TZ)
    assert r.end == datetime(2026, 11, 26, 0, 0, tzinfo=TZ)
    assert r.all_day
    assert r.confidence < 0.8  # 只有星期 → 待确认


def test_saturday_all_day():
    r = normalize_time_expression("周六", BASE)
    assert r.start == datetime(2026, 11, 28, 0, 0, tzinfo=TZ)
    assert r.all_day
    assert r.confidence == 0.62


def test_cross_year_range():
    r = normalize_time_expression("12月31日 22:00-次日1:00", BASE)
    assert r.start == datetime(2026, 12, 31, 22, 0, tzinfo=TZ)
    assert r.end == datetime(2027, 1, 1, 1, 0, tzinfo=TZ)
    assert not r.all_day


def test_unresolved():
    r = normalize_time_expression("时间待定", BASE)
    assert r.unresolved
    assert r.start is None
    assert r.confidence == 0.0


def test_dian_range_applies_period_to_both():
    r = normalize_time_expression("周五晚7点到9点", BASE)
    assert r.start == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert r.end == datetime(2026, 11, 27, 21, 0, tzinfo=TZ)


def test_past_time_is_flagged():
    r = normalize_time_expression("11月20日 19:00", BASE)
    assert r.start == datetime(2026, 11, 20, 19, 0, tzinfo=TZ)
    assert r.is_past
    assert "已过去" in r.basis


def test_month_day_rolls_to_next_year_when_far_past():
    r = normalize_time_expression("1月5日", BASE)
    assert r.start == datetime(2027, 1, 5, 0, 0, tzinfo=TZ)
    assert r.all_day


def test_tomorrow_all_day():
    r = normalize_time_expression("明天", BASE)
    assert r.start == datetime(2026, 11, 23, 0, 0, tzinfo=TZ)
    assert r.end == datetime(2026, 11, 24, 0, 0, tzinfo=TZ)
    assert r.all_day


def test_time_without_date_is_low_confidence():
    r = normalize_time_expression("晚上7点", BASE)
    assert r.start == datetime(2026, 11, 22, 19, 0, tzinfo=TZ)
    assert r.confidence < 0.8
    assert "未识别到日期" in r.basis


def test_no_date_no_time_is_unresolved():
    r = normalize_time_expression("有个讲座在六教", BASE)
    assert r.unresolved
    assert r.start is None
