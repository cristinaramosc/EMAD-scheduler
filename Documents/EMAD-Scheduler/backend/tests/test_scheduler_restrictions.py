from backend.scheduler_engine.generator import SchedulerGenerator
from backend.scheduler_engine.models.generation_context import GenerationContext
from backend.scheduler_engine.placement_strategy import GreedyPlacementStrategy
from backend.models.teaching_block import TeachingBlock
from backend.scheduler_engine.models.scheduled_activity import ScheduledActivity
from backend.scheduler_engine.models.timeslot import TimeSlot
from backend.scheduler_engine.models.school_calendar import SchoolCalendar


def make_block(id="b1", teacher="T1", group="G1", duration_blocks=1):
    return TeachingBlock(
        id=id,
        duration=1.0,
        order=1,
        duration_blocks=duration_blocks,
        preferred_room_id=None,
        preferred_teacher_id=teacher.strip(),
        metadata={"teacher": teacher.strip(), "group": group.strip()},
    )


def make_context_with_blocked_teacher(day=0, period=0, teacher="T1"):
    cal = SchoolCalendar(days=[0, 1], periods_per_day=8)
    blocked_activity = ScheduledActivity(
        teaching_block=TeachingBlock(id="blocked-1", duration=0.5, order=0, duration_blocks=1, preferred_teacher_id=teacher.strip(), metadata={"synthetic": True}),
        day=day,
        start_timeslot=TimeSlot(day=day, period=period),
        duration=1,
        teacher_id=teacher.strip(),
        metadata={"synthetic": True},
    )
    return GenerationContext(school_calendar=cal, existing_scheduled_activities=(blocked_activity,), fixed_activities=(), blocked_time_slots=((day, period),), configuration={})


def test_teacher_unavailable_slot_prevents_placement():
    gen = SchedulerGenerator()
    block = make_block(id="b1", teacher="T1", group="G1")
    ctx = make_context_with_blocked_teacher(day=0, period=0, teacher="T1")
    result = gen.generate([block], ctx)
    assert result.valid
    # ensure no activity is placed at the blocked slot
    for proposal in result.proposals:
        for act in proposal.activities:
            assert not (act.start == f"Period 0" and act.day == f"Day 0")


def test_multiple_proposals_generated_when_alternatives_exist():
    gen = SchedulerGenerator()
    # two blocks that can be ordered differently
    b1 = make_block(id="b1", teacher="T1", group="G1")
    b2 = make_block(id="b2", teacher="T2", group="G2")
    cal = SchoolCalendar(days=[0, 1], periods_per_day=8)
    ctx = GenerationContext(school_calendar=cal, existing_scheduled_activities=(), fixed_activities=(), blocked_time_slots=(), configuration={})
    result = gen.generate([b1, b2], ctx, max_proposals=5)
    assert result.valid
    assert len(result.proposals) >= 2


def test_group_time_window_constraint_allows_only_slots_inside_window():
    strategy = GreedyPlacementStrategy()
    block = make_block(id="b1", teacher="T1", group="GP", duration_blocks=2)
    ctx = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_time_window_constraints": {"GP": (5, 6)}},
    )

    placement = strategy.place(block, ctx, ())

    assert placement is not None
    assert placement.start_timeslot.period == 5
    assert placement.duration == 2


def test_group_time_window_constraint_rejects_activity_extending_beyond_window():
    strategy = GreedyPlacementStrategy()
    block = make_block(id="b1", teacher="T1", group="GP", duration_blocks=3)
    ctx = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_time_window_constraints": {"GP": (5, 6)}},
    )

    placement = strategy.place(block, ctx, ())

    assert placement is None
