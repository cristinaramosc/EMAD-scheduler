"""Unit tests for detailed placement-failure explanations.

These tests exercise GreedyPlacementStrategy.explain_failure() and the
structured warning dict produced by SchedulerGenerator directly, without
going through FastAPI or the bootstrap singleton, since they only depend on
the scheduler engine's domain objects.
"""

from backend.models.teaching_block import TeachingBlock
from backend.scheduler_engine.generator import SchedulerGenerator
from backend.scheduler_engine.models import (
    GenerationContext,
    ScheduledActivity,
    SchoolCalendar,
    TimeSlot,
)
from backend.scheduler_engine.placement_strategy import GreedyPlacementStrategy


def _single_slot_calendar() -> SchoolCalendar:
    """A calendar with exactly one lective slot (Monday, period 0)."""
    return SchoolCalendar(days=[0], periods_per_day=1)


def _teaching_block(**overrides) -> TeachingBlock:
    defaults = dict(
        id="block-1",
        duration=1,
        order=1,
        duration_blocks=1,
        preferred_room_id=None,
        preferred_teacher_id=None,
        fixed=False,
        metadata={},
    )
    defaults.update(overrides)
    return TeachingBlock(**defaults)


def test_teacher_not_available_reason_is_explicit():
    calendar = _single_slot_calendar()
    existing = ScheduledActivity(
        teaching_block=_teaching_block(metadata={"subject": "Altres", "teacher": "Anna", "group": "1A"}),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        room_id=None,
        teacher_id="anna",
        group_id="1A",
        metadata={"subject": "Altres"},
    )
    context = GenerationContext(
        school_calendar=calendar,
        existing_scheduled_activities=(existing,),
    )
    candidate = _teaching_block(
        preferred_teacher_id="anna",
        metadata={"subject": "Disseny", "teacher": "Anna", "group": "2B"},
    )

    strategy = GreedyPlacementStrategy()
    assert strategy.place(candidate, context, []) is None

    reasons = strategy.explain_failure(candidate, context, [])
    assert len(reasons) == 1
    assert "Anna" in reasons[0]
    assert "no està disponible" in reasons[0]
    assert "dilluns" in reasons[0]


def test_room_occupied_reason_is_explicit():
    calendar = _single_slot_calendar()
    existing = ScheduledActivity(
        teaching_block=_teaching_block(metadata={"subject": "Altres", "teacher": "Marc", "group": "1B"}),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        room_id="Fusta",
        teacher_id="marc",
        group_id="1B",
        metadata={"subject": "Altres"},
    )
    context = GenerationContext(
        school_calendar=calendar,
        existing_scheduled_activities=(existing,),
        configuration={"room_constraints_enabled": True},
    )
    candidate = _teaching_block(
        preferred_room_id="Fusta",
        preferred_teacher_id="laia",
        metadata={"subject": "Taller", "teacher": "Laia", "group": "2C"},
    )

    strategy = GreedyPlacementStrategy()
    assert strategy.place(candidate, context, []) is None

    reasons = strategy.explain_failure(candidate, context, [])
    assert len(reasons) == 1
    assert "Fusta" in reasons[0]
    assert "ocupada" in reasons[0]


def test_group_conflict_reason_is_explicit():
    calendar = _single_slot_calendar()
    existing = ScheduledActivity(
        teaching_block=_teaching_block(metadata={"subject": "Altra assignatura", "teacher": "Pere", "group": "2A"}),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        room_id=None,
        teacher_id="pere",
        group_id="2A",
        metadata={"subject": "Altra assignatura"},
    )
    context = GenerationContext(
        school_calendar=calendar,
        existing_scheduled_activities=(existing,),
    )
    candidate = _teaching_block(
        preferred_teacher_id="un_altre",
        metadata={"subject": "Taller Fusta", "teacher": "Un altre", "group": "2A"},
    )

    strategy = GreedyPlacementStrategy()
    assert strategy.place(candidate, context, []) is None

    reasons = strategy.explain_failure(candidate, context, [])
    assert len(reasons) == 1
    assert "2A" in reasons[0]
    assert "ja té una altra activitat" in reasons[0]


def test_multiple_simultaneous_causes_are_all_reported():
    calendar = _single_slot_calendar()
    existing = ScheduledActivity(
        teaching_block=_teaching_block(metadata={"subject": "Altres", "teacher": "Anna", "group": "1A"}),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        room_id="Fusta",
        teacher_id="anna",
        group_id="1A",
        metadata={"subject": "Altres"},
    )
    context = GenerationContext(
        school_calendar=calendar,
        existing_scheduled_activities=(existing,),
        configuration={"room_constraints_enabled": True},
    )
    # Same teacher AND same room as the existing activity, different group.
    candidate = _teaching_block(
        preferred_teacher_id="anna",
        preferred_room_id="Fusta",
        metadata={"subject": "Disseny", "teacher": "Anna", "group": "2B"},
    )

    strategy = GreedyPlacementStrategy()
    assert strategy.place(candidate, context, []) is None

    reasons = strategy.explain_failure(candidate, context, [])
    assert len(reasons) >= 2
    joined = " | ".join(reasons)
    assert "no està disponible" in joined
    assert "ocupada" in joined


def test_generator_reports_structured_incidence_dict():
    """End-to-end: SchedulerGenerator must surface a structured incidence
    (dict with reason + constraints), not a generic string."""
    calendar = _single_slot_calendar()
    existing = ScheduledActivity(
        teaching_block=_teaching_block(metadata={"subject": "Altres", "teacher": "Anna", "group": "1A"}),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        room_id=None,
        teacher_id="anna",
        group_id="1A",
        metadata={"subject": "Altres"},
    )
    context = GenerationContext(
        school_calendar=calendar,
        existing_scheduled_activities=(existing,),
    )
    candidate = _teaching_block(
        preferred_teacher_id="anna",
        metadata={"subject": "Disseny", "teacher": "Anna", "group": "2B"},
    )

    result = SchedulerGenerator().generate([candidate], context)

    assert result.valid is False
    assert len(result.warnings) == 1
    incidence = result.warnings[0]
    assert isinstance(incidence, dict)
    assert incidence["subject"] == "Disseny"
    assert incidence["teacher"] == "Anna"
    assert incidence["group"] == "2B"
    assert incidence["reason"] == "No s'ha pogut col·locar."
    assert isinstance(incidence["constraints"], list) and len(incidence["constraints"]) >= 1
    assert any("no està disponible" in c for c in incidence["constraints"])
