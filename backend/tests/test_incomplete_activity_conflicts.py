from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Schedule, Activity


def test_incomplete_activities_do_not_create_conflicts():
    schedule = Schedule()

    schedule.add(
        Activity(
            id=1,
            teacher="Joan",
            subject="Dibuix",
            group="1A",
            room="A1",
            day="",
            start="",
            duration=2,
        )
    )

    schedule.add(
        Activity(
            id=2,
            teacher="Joan",
            subject="Color",
            group="2A",
            room="A1",
            day="",
            start="",
            duration=2,
        )
    )

    engine = SchedulerEngine()
    engine.load(schedule)

    assert engine.get_conflicts() == []
