from datetime import datetime

from app.parsing.extract_rules import extract_activity
from app.parsing.time_norm import TZ

BASE = datetime(2026, 11, 22, 10, 0, tzinfo=TZ)  # 周日


def test_when_where_what():
    parsed = extract_activity("周五晚7点 大礼堂 新生舞会", BASE)
    assert parsed is not None
    assert parsed.title == "新生舞会"
    assert parsed.start_at == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert parsed.end_at is None
    assert not parsed.all_day
    assert parsed.location == "大礼堂"
    assert parsed.confidence["start_at"] >= 0.8
    assert not parsed.unresolved_time


def test_date_time_range_and_place():
    parsed = extract_activity("11/27 20:00-22:00 六教 讲座B", BASE)
    assert parsed is not None
    assert parsed.title == "讲座B"
    assert parsed.start_at == datetime(2026, 11, 27, 20, 0, tzinfo=TZ)
    assert parsed.end_at == datetime(2026, 11, 27, 22, 0, tzinfo=TZ)
    assert parsed.location == "六教"


def test_weekday_only_is_low_confidence_all_day():
    parsed = extract_activity("周六 社团招新", BASE)
    assert parsed is not None
    assert parsed.title == "社团招新"
    assert parsed.all_day
    assert parsed.start_at == datetime(2026, 11, 28, 0, 0, tzinfo=TZ)
    assert parsed.confidence["start_at"] < 0.8


def test_incomplete_activity_is_kept():
    parsed = extract_activity("有个讲座在六教", BASE)
    assert parsed is not None
    assert parsed.title == "讲座"
    assert parsed.location == "六教"
    assert parsed.start_at is None
    assert parsed.unresolved_time


def test_pure_chat_is_not_an_activity():
    assert extract_activity("你好", BASE) is None
    assert extract_activity("在吗", BASE) is None


def test_deadline_is_extracted_without_stealing_event_date():
    parsed = extract_activity(
        "报名截止 11月25日 24:00 周五晚7点 大礼堂 新生舞会", BASE
    )
    assert parsed is not None
    assert parsed.title == "新生舞会"
    assert parsed.start_at == datetime(2026, 11, 27, 19, 0, tzinfo=TZ)
    assert parsed.deadline_at == datetime(2026, 11, 25, 23, 59, tzinfo=TZ)


def test_trailing_bracket_from_copy_is_stripped():
    parsed = extract_activity("周五晚7点 大礼堂 新生舞会」", BASE)
    assert parsed is not None
    assert parsed.title == "新生舞会"


def test_tomorrow_afternoon():
    parsed = extract_activity("明天下午2点 六教 讲座", BASE)
    assert parsed is not None
    assert parsed.title == "讲座"
    assert parsed.start_at == datetime(2026, 11, 23, 14, 0, tzinfo=TZ)
    assert parsed.location == "六教"


def test_ocr_screenshot_uses_labeled_time_and_line_title():
    text = (
        "10:32Q\n@5..=46l口82%\n清华大学图书馆\n2026年11月21日10:00北京\n"
        "1人AI摘要\n2026\n清华大学国書馆\n第十一届\n"
        "阅见新资源 悦享新服务\n图书馆服务宣传月\n"
        "新火传书·旧卷逢新一2026年赠书转赠活动\n"
        "一本旧书，也曾被某盏灯照亮；一次转赠，让文字在校园里再遇新知。\n"
        "活动时间\n2026年11月25日（星期三）9:00-18:00\n"
        "活动地点\n清华大学人文社科图书馆G层大同厅\n"
    )
    parsed = extract_activity(text, BASE)
    assert parsed is not None
    assert parsed.title.startswith("新火传书")
    assert len(parsed.title) <= 40
    assert parsed.start_at == datetime(2026, 11, 25, 9, 0, tzinfo=TZ)
    assert parsed.end_at == datetime(2026, 11, 25, 18, 0, tzinfo=TZ)
    assert parsed.location == "清华大学人文社科图书馆G层大同厅"
