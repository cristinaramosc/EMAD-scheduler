from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Schedule, Activity


def test_room_conflict():
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
            group="2A",
            room="A1",
            day="Monday",
            start="08:00",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "room_conflict" for c in conflicts)


def test_room_conflict_detects_adjacent_slot_overlap():
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
            group="2A",
            room="A1",
            day="Monday",
            start="08:30",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    conflicts = engine.get_conflicts()

    assert any(c.type == "room_conflict" for c in conflicts)

def test_room_conflict_allows_same_room_for_simultaneous_co_teaching():
    schedule = Schedule()
    tag = "TALLER|COM|Joan|Marc"
    schedule.add(Activity(id=1, teacher="Joan", subject="TALLER", group="COM", room="A1", day="Monday", start="08:00", duration=2, simultaneous_group=tag))
    schedule.add(Activity(id=2, teacher="Marc", subject="TALLER", group="COM", room="A1", day="Monday", start="08:00", duration=2, simultaneous_group=tag))
    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()
    assert not any(c.type == "room_conflict" for c in conflicts)
