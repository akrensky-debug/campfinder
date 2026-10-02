from datetime import date, time

import pytest

from campfinder.activity.schedule import (
    Slot, TimeWindow, describe, find_conflicts, normalize_days, occurrences, parse_time, rrule_days, weekly_rrule,
)


def test_normalize_days_accepts_what_parents_say():
    assert normalize_days(["weekdays"]) == ["MO", "TU", "WE", "TH", "FR"]
    assert normalize_days(["Saturday", "sun"]) == ["SA", "SU"]
    assert normalize_days(["TU", "tuesday"]) == ["TU"]
    with pytest.raises(ValueError):
        normalize_days(["someday"])


def test_parse_time_formats():
    assert parse_time("15:30") == time(15, 30)
    assert parse_time("4pm") == time(16, 0)
    assert parse_time("4:30 pm") == time(16, 30)
    assert parse_time("12am") == time(0, 0)
    assert parse_time("16:00:00") == time(16, 0)


def test_occurrences_skip_holidays_and_respect_bounds():
    # Tuesdays Sept 8 - Oct 27 2026, no class Oct 13
    days = occurrences(date(2026, 9, 8), date(2026, 10, 27), weekly_rrule(["TU"]), ["2026-10-13"])
    assert days[0] == date(2026, 9, 8) and days[-1] == date(2026, 10, 27)
    assert date(2026, 10, 13) not in days
    assert len(days) == 7
    clipped = occurrences(date(2026, 9, 8), date(2026, 10, 27), "FREQ=WEEKLY;BYDAY=TU", window_start=date(2026, 10, 1))
    assert clipped[0] == date(2026, 10, 6)


def test_occurrences_without_rrule_is_every_day():
    assert len(occurrences(date(2027, 7, 6), date(2027, 7, 10), None)) == 5


def test_rrule_days_and_describe():
    assert rrule_days("FREQ=WEEKLY;BYDAY=TH,TU") == ["TU", "TH"]
    assert describe(["TU"], time(16), time(16, 30)) == "Tuesdays 4–4:30pm"
    assert describe(["TU", "TH"], time(11), time(13)) == "Tue & Thu 11am–1pm"


def test_time_window():
    w = TimeWindow.build(["weekdays"], "15:30")
    assert w.check(["TU"], time(16), time(17)) == (True, None)
    ok, why = w.check(["TU"], time(15), time(16))
    assert not ok and "before 3:30pm" in why
    ok, why = w.check(["SA"], time(10), time(11))
    assert not ok and "Saturday" in why
    mornings = TimeWindow.build(["Saturday"], time_of_day="morning")
    assert mornings.check(["SA"], time(9, 30), time(10))[0]
    assert not mornings.check(["SA"], time(11, 30), time(12, 30))[0]


def _tuesdays(child: str, start: time, end: time, title: str = "x") -> Slot:
    return Slot(title, occurrences(date(2026, 9, 8), date(2026, 10, 27), "FREQ=WEEKLY;BYDAY=TU"), start, end, child)


def test_conflicts_same_child_clash():
    new = _tuesdays("Maya", time(16), time(16, 30), "Swim")
    c = find_conflicts(new, [_tuesdays("Maya", time(15, 45), time(16, 15), "Piano")])
    assert [x.severity for x in c] == ["clash"]
    assert c[0].dates[0] == date(2026, 9, 8)


def test_conflicts_other_child_pickup_within_buffer():
    new = _tuesdays("Maya", time(16), time(16, 30), "Swim")
    pickup = _tuesdays("Leo", time(16, 40), time(17, 30), "Soccer")
    assert [x.severity for x in find_conflicts(new, [pickup], buffer_minutes=15)] == ["logistics"]
    assert find_conflicts(new, [pickup], buffer_minutes=5) == []


def test_conflicts_all_day_camp_week_for_same_child_only():
    new = _tuesdays("Maya", time(16), time(16, 30))
    camp = Slot("Camp", occurrences(date(2026, 9, 7), date(2026, 9, 11), None), child="Maya")
    other = Slot("Camp", occurrences(date(2026, 9, 7), date(2026, 9, 11), None), child="Leo")
    assert [x.severity for x in find_conflicts(new, [camp, other])] == ["all_day"]


def test_slot_from_family_event_row():
    s = Slot.from_event({"id": "e1", "title": "Pickup", "start_date": "2026-09-01", "end_date": "2026-12-31",
                         "rrule": "FREQ=WEEKLY;BYDAY=MO,WE", "start_time": "15:15:00", "end_time": "15:30:00"},
                        window_start=date(2026, 9, 7), window_end=date(2026, 9, 13))
    assert s.dates == [date(2026, 9, 7), date(2026, 9, 9)] and s.start_time == time(15, 15)
