from backend.scheduler_engine.placement_strategy import GreedyPlacementStrategy
from backend.models.teaching_block import TeachingBlock
from backend.scheduler_engine.models.generation_context import GenerationContext
from backend.scheduler_engine.models.scheduled_activity import ScheduledActivity
from backend.scheduler_engine.models.timeslot import TimeSlot
from backend.scheduler_engine.models.school_calendar import SchoolCalendar


def make_block(id="b1", teacher="T1", group="GP", duration_blocks=1):
    return TeachingBlock(
        id=id,
        duration=1.0,
        order=1,
        duration_blocks=duration_blocks,
        preferred_room_id=None,
        preferred_teacher_id=teacher,
        metadata={"teacher": teacher, "group": group},
    )


def test_group_max_days_allows_placement_on_already_used_day():
    strategy = GreedyPlacementStrategy()
    block = make_block(id="b1", group="GP")
    existing = ScheduledActivity(
        teaching_block=make_block(id="existing", group="GP"),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        group_id="GP",
        metadata={"group": "GP"},
    )
    ctx = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=8),
        existing_scheduled_activities=(existing,),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_max_days_constraints": {"GP": 1}},
    )

    placement = strategy.place(block, ctx, ())

    assert placement is not None
    assert placement.day == 0


def test_group_max_days_rejects_a_new_day_beyond_the_limit():
    strategy = GreedyPlacementStrategy()
    block = make_block(id="b1", group="GP")
    existing = ScheduledActivity(
        teaching_block=make_block(id="existing", group="GP"),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        group_id="GP",
        metadata={"group": "GP"},
    )
    ctx = GenerationContext(
        school_calendar=SchoolCalendar(days=[1], periods_per_day=8),
        existing_scheduled_activities=(existing,),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_max_days_constraints": {"GP": 1}},
    )

    placement = strategy.place(block, ctx, ())

    assert placement is None


def test_group_max_days_no_limit_configured_places_freely():
    strategy = GreedyPlacementStrategy()
    block = make_block(id="b1", group="GP")
    ctx = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    placement = strategy.place(block, ctx, ())

    assert placement is not None
