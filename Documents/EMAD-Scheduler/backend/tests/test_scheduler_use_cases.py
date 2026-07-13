import pytest

from backend.application.scheduler_use_cases import SchedulerUseCases
from backend.repositories.requirement_repository import RequirementRepository
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import SchoolCalendar
from backend.services.requirement_service import RequirementService


def test_scheduler_use_cases_respects_injected_school_calendar() -> None:
    repo = RequirementRepository()
    service = RequirementService(repo)
    requirement = service.create(
        {
            "group_id": "g1",
            "subject_id": "s1",
            "teacher_id": "t1",
            "weekly_hours": 2.0,
            "min_days": 1,
            "max_days": 1,
            "min_block_duration": 1.0,
            "max_consecutive_hours": 2.0,
            "allow_half_hour_blocks": False,
        }
    )
    use_cases = SchedulerUseCases(
        requirement_repo=repo,
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
    )

    with pytest.raises(RuntimeError):
        use_cases.generate_proposals([requirement.id])