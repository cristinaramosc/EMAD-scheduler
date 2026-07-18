from scheduler_engine.models import SchoolCalendar, TimeSlot


def test_periods_for_day_default():
    cal = SchoolCalendar(periods_per_day=8)
    slots = cal.periods_for_day(0)
    assert len(slots) == 8
    assert all(isinstance(s, TimeSlot) for s in slots)


def test_breaks_excluded():
    cal = SchoolCalendar(periods_per_day=6, breaks={0: [2, 3]})
    slots = cal.periods_for_day(0)
    periods = [s.period for s in slots]
    assert 2 not in periods
    assert 3 not in periods


def test_is_period_lective():
    cal = SchoolCalendar(periods_per_day=5, breaks={1: [1]})
    assert cal.is_period_lective(TimeSlot(day=0, period=0))
    assert not cal.is_period_lective(TimeSlot(day=1, period=1))
    assert not cal.is_period_lective(TimeSlot(day=6, period=0))
