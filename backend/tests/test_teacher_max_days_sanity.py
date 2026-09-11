from backend.models.teaching_block import TeachingBlock
from backend.scheduler_engine.constraints.teacher_max_days import TeacherMaxDaysConstraint
from backend.scheduler_engine.models import Activity, Schedule
from backend.scheduler_engine.models.generation_context import GenerationContext
from backend.scheduler_engine.models.scheduled_activity import ScheduledActivity
from backend.scheduler_engine.models.school_calendar import SchoolCalendar
from backend.scheduler_engine.models.timeslot import TimeSlot
from backend.scheduler_engine.placement_strategy import GreedyPlacementStrategy


def _block(block_id="b1", teacher="Ana"):
    return TeachingBlock(
        id=block_id,
        duration=1.0,
        order=1,
        duration_blocks=1,
        preferred_room_id=None,
        preferred_teacher_id=teacher,
        metadata={"teacher": teacher, "group": "GP"},
    )


def test_teacher_max_days_reports_activity_on_day_beyond_limit():
    schedule = Schedule(
        lessons=[
            Activity(1, "Ana", "Dibuix", "GP", "", "dilluns", "08:00", 1),
            Activity(2, "Ana", "Pintura", "GP", "", "dimarts", "08:00", 1),
        ]
    )
    schedule.configuration = {
        "day_names": ["dilluns", "dimarts"],
        "teacher_max_days_constraints": {"ana": 1},
    }

    conflicts = TeacherMaxDaysConstraint().validate(schedule)

    assert len(conflicts) == 1
    assert conflicts[0].type == "teacher_max_days"
    assert conflicts[0].day == "dimarts"


def test_teacher_max_days_rejects_new_day_but_allows_used_day():
    strategy = GreedyPlacementStrategy()
    existing = ScheduledActivity(
        teaching_block=_block("existing"),
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        teacher_id="Ana",
        group_id="GP",
    )

    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=8),
        existing_scheduled_activities=(existing,),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"teacher_max_days_constraints": {"ana": 1}},
    )

    placement = strategy.place(_block(), context, ())

    assert placement is not None
    assert placement.day == 0