from pathlib import Path

from backend.application.scheduler_use_cases import SchedulerUseCases
from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import SchoolCalendar


def test_scheduler_use_cases_builds_blocked_activities_from_academic_restrictions() -> None:
    use_cases = SchedulerUseCases(
        requirement_repo=None,
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=2),
        time_labels={"day_names": ["Dilluns", "Dimarts"], "hour_names": ["8:00", "9:00"]},
        academic_data_repo=AcademicDataRepository(),
    )

    blocked = use_cases._build_blocked_activities_from_restrictions(
        [
            {"teacher": "Ana", "unavailable_slots": ["Dilluns 8:00"]},
        ],
        [
            {"group": "1A", "unavailable_slots": ["Dimarts 9:00"]},
        ],
    )

    assert len(blocked) == 2
    assert all(activity.metadata.get("synthetic") is True for activity in blocked)


def test_academic_snapshot_persists_restrictions_into_repository() -> None:
    reset_dependencies()

    repo = get_academic_data_repo()
    repo.apply_snapshot(
        {
            "teachers": [{"name": "Ana"}],
            "groups": [{"name": "1A"}],
            "subjects": [{"name": "Matemàtiques"}],
            "teaching_assignments": [
                {
                    "teacher": "Ana",
                    "subject": "Matemàtiques",
                    "group": "1A",
                    "weekly_hours": 2.0,
                }
            ],
            "teacher_restrictions": [
                {
                    "teacher": "Ana",
                    "unavailable_slots": ["Dilluns 8:00"],
                }
            ],
            "group_restrictions": [
                {
                    "group": "1A",
                    "unavailable_slots": ["Dimarts 9:00"],
                }
            ],
        }
    )
    assert any(restriction["teacher"] == "Ana" for restriction in repo.list_teacher_restrictions())
    assert any(restriction["group"] == "1A" for restriction in repo.list_group_restrictions())
