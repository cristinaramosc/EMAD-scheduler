from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import Activity, Schedule


def _activity(activity_id, group, subject, start, duration=2):
    return Activity(
        id=activity_id,
        teacher=f"Teacher {activity_id}",
        subject=subject,
        group=group,
        room=f"Room {activity_id}",
        day="Dilluns",
        start=start,
        duration=duration,
    )


def test_shared_assignment_between_day_activities_is_a_preference_not_a_hard_conflict():
    schedule = Schedule()
    schedule.add(_activity(1, "GI", "Dibuix", "15:00"))
    schedule.add(_activity(2, "GI, GP", "Llenguatge audiovisual", "16:00"))
    schedule.add(_activity(3, "GI", "Projectes", "17:00"))
    schedule.add(_activity(4, "GP", "Foto", "15:00"))
    schedule.add(_activity(5, "GP", "Edició", "17:00"))

    conflicts = SchedulerEngine().validate(schedule)

    assert conflicts == []


def test_shared_assignment_can_be_last_for_one_group_and_first_for_the_other():
    schedule = Schedule()
    schedule.add(_activity(1, "GI", "Dibuix", "15:00"))
    schedule.add(_activity(2, "GI, GP", "Llenguatge audiovisual", "16:00"))
    schedule.add(_activity(3, "GP", "Foto", "17:00"))

    assert SchedulerEngine().validate(schedule) == []
