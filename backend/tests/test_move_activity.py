import pytest

from backend.routes.scheduler_live import move as move_route
from backend.scheduler_engine.engine_instance import engine as shared_engine
from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Schedule, Activity


def make_schedule():
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

    return schedule


def test_move_activity_updates_day_and_start():
    engine = SchedulerEngine()
    engine.load(make_schedule())

    activity = engine.move_activity(
        1,
        day="Tuesday",
        start="10:00",
    )

    assert activity is not None
    assert activity.day == "Tuesday"
    assert activity.start == "10:00"


def test_move_activity_returns_none_when_activity_does_not_exist():
    engine = SchedulerEngine()
    engine.load(make_schedule())

    activity = engine.move_activity(
        999,
        day="Tuesday",
        start="10:00",
    )

    assert activity is None


@pytest.fixture(autouse=True)
def reset_engine_state():
    shared_engine.load(Schedule())
    yield
    shared_engine.load(Schedule())


def test_valid_move_succeeds_and_updates_schedule():
    shared_engine.load(make_schedule())

    result = move_route(
        type("MovePayload", (), {"activity_id": 1, "day": "Tuesday", "start": "10:00"})()
    )

    assert result["ok"] is True
    assert shared_engine.state.all()[0].day == "Tuesday"
    assert shared_engine.state.all()[0].start == "10:00"


def test_invalid_move_is_rejected_and_schedule_remains_consistent():
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
            subject="Música",
            group="1B",
            room="A2",
            day="Monday",
            start="10:00",
            duration=2,
        )
    )
    shared_engine.load(schedule)

    result = move_route(
        type("MovePayload", (), {"activity_id": 1, "day": "Monday", "start": "10:00"})()
    )

    assert result["ok"] is False
    assert result["conflicts"]
    assert shared_engine.state.all()[0].day == "Monday"
    assert shared_engine.state.all()[0].start == "08:00"


def test_move_is_accepted_when_schedule_already_has_unrelated_conflicts():
    """Un moviment vàlid no s'ha de rebutjar només perquè l'horari ja tenia
    algun conflicte preexistent en un altre lloc no relacionat."""
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
            subject="Música",
            group="1B",
            room="A2",
            day="Monday",
            start="09:00",
            duration=2,
        )
    )
    schedule.add(
        Activity(
            id=3,
            teacher="Maria",
            subject="Anglès",
            group="1C",
            room="A3",
            day="Monday",
            start="09:00",
            duration=2,
        )
    )
    shared_engine.load(schedule)

    result = move_route(
        type("MovePayload", (), {"activity_id": 1, "day": "Tuesday", "start": "08:00"})()
    )

    assert result["ok"] is True
    moved = next(item for item in shared_engine.state.all() if item.id == 1)
    assert moved.day == "Tuesday"
    assert moved.start == "08:00"
