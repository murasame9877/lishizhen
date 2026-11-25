from datetime import datetime

from app.calendar.ics import TZ, build_event_ics


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def build(**overrides):
    kwargs = dict(
        uid="sdg-test-uid@sdg.local",
        title="新生舞会",
        start=dt(27, 19, 0),
        end=dt(27, 21, 0),
        location="大礼堂",
        url="https://mp.weixin.qq.com/s/xxxx",
        now=dt(22, 10, 0),
        created_at=dt(22, 10, 0),
    )
    kwargs.update(overrides)
    return build_event_ics(**kwargs)


def test_timed_event_has_two_default_alarms():
    ics = build()
    assert "BEGIN:VCALENDAR" in ics
    assert "TZID:Asia/Shanghai" in ics
    assert "DTSTART;TZID=Asia/Shanghai:20261127T190000" in ics
    assert "TRIGGER:-PT30M" in ics
    assert "TRIGGER:PT0M" in ics
    assert ics.count("BEGIN:VALARM") == 2
    assert "UID:sdg-test-uid@sdg.local" in ics
    assert ics.endswith("\r\n")


def test_all_day_event_alarm_is_absolute_0900():
    ics = build(
        start=dt(28, 0, 0),
        end=dt(29, 0, 0),
        all_day=True,
        title="社团开放日",
    )
    assert "DTSTART;VALUE=DATE:20261128" in ics
    assert "DTEND;VALUE=DATE:20261129" in ics
    assert "TRIGGER;VALUE=DATE-TIME:20261128T010000Z" in ics
    assert ics.count("BEGIN:VALARM") == 1


def test_all_day_created_after_0900_same_day_uses_plus_10_minutes():
    ics = build(
        start=dt(28, 0, 0),
        end=dt(29, 0, 0),
        all_day=True,
        now=dt(28, 10, 0),
        created_at=dt(28, 10, 0),
    )
    assert "TRIGGER;VALUE=DATE-TIME:20261128T021000Z" in ics
    assert ics.count("BEGIN:VALARM") == 1


def test_all_day_in_the_past_has_no_alarm():
    ics = build(
        start=dt(20, 0, 0),
        end=dt(21, 0, 0),
        all_day=True,
        now=dt(22, 10, 0),
    )
    assert "BEGIN:VALARM" not in ics


def test_long_lines_are_folded_to_75_octets():
    ics = build(title="很长的活动标题" * 30)
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_sequence_is_written():
    ics = build(sequence=3)
    assert "SEQUENCE:3" in ics


def test_custom_remind_offsets():
    ics = build(remind_offsets=(-60,))
    assert "TRIGGER:-PT60M" in ics
    assert ics.count("BEGIN:VALARM") == 1


def test_empty_remind_offsets_means_no_alarm():
    ics = build(remind_offsets=())
    assert "BEGIN:VALARM" not in ics
