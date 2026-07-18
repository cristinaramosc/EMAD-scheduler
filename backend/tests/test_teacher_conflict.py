from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Schedule, Activity


def test_teacher_conflict():
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
            teacher="Joan",
            subject="Color",
            group="2A",
            room="A2",
            day="Monday",
            start="08:00",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "teacher_conflict" for c in conflicts)


def test_teacher_conflict_detects_adjacent_slot_overlap():
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
            teacher="Joan",
            subject="Color",
            group="2A",
            room="A2",
            day="Monday",
            start="08:30",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "teacher_conflict" for c in conflicts)