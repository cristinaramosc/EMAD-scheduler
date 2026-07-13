from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Activity, Schedule


def test_group_conflict():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix",
            group="1A",
            room="A1",
            day="Monday",
            start="08:00",
            duration=2,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Maria",
            subject="Color",
            group="1A",
            room="A2",
            day="Monday",
            start="08:00",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "group_conflict" for c in conflicts)


def test_group_conflict_allows_same_parent_1q_and_2q_in_same_slot():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix",
            group="1A 1Q",
            room="A1",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Maria",
            subject="Color",
            group="1A 2Q",
            room="A2",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_conflict" for c in conflicts)


def test_group_conflict_allows_same_parent_subject_suffix_1q_and_2q_in_same_slot():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix 1Q",
            group="1A",
            room="A1",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Maria",
            subject="Color 2Q",
            group="1A",
            room="A2",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_conflict" for c in conflicts)


def test_group_conflict_rejects_full_parent_and_subgroup_same_slot():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix",
            group="1A",
            room="A1",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Maria",
            subject="Color",
            group="1A 1Q",
            room="A2",
            day="Monday",
            start="08:00",
            duration=1,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "group_conflict" for c in conflicts)


def test_group_conflict_detects_adjacent_slot_overlap():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix",
            group="1A",
            room="A1",
            day="Monday",
            start="08:00",
            duration=2,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Maria",
            subject="Color",
            group="1A",
            room="A2",
            day="Monday",
            start="08:30",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "group_conflict" for c in conflicts)