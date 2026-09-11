import pytest

from backend.application.scheduler_use_cases import SchedulerUseCases
from backend.repositories.academic_data_repository import AcademicDataRepository
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


def test_academic_assignment_priority_is_elevated_when_any_teacher_is_restricted() -> None:
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
    )

    requirement = use_cases._build_requirement_from_assignment(
        1,
        {
            "teacher": "Ana, Biel",
            "subject": "Dibuix",
            "group": "1A",
            "weekly_hours": 2.0,
            "min_block_duration": 0.5,
            "max_consecutive_hours": 2.0,
        },
        {"Biel"},
        set(),
    )

    assert requirement.priority == 1
    assert requirement.fixed_teacher is True


def test_academic_assignment_priority_is_elevated_when_group_is_restricted() -> None:
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
    )

    requirement = use_cases._build_requirement_from_assignment(
        1,
        {
            "teacher": "Ana",
            "subject": "Dibuix",
            "group": "1A",
            "weekly_hours": 2.0,
            "min_block_duration": 0.5,
            "max_consecutive_hours": 2.0,
        },
        set(),
        {"1A"},
    )

    assert requirement.priority == 1
    assert requirement.fixed_teacher is False


def test_max_session_days_from_academic_data_limits_block_splitting() -> None:
    """Una assignatura de 2h amb max_session_days=1 a les dades acadèmiques
    ha de generar un requirement amb max_days=1 (un sol bloc de 2h), no
    caure en el 5 per defecte i acabar partida en dies diferents."""
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
    )

    requirement = use_cases._build_requirement_from_assignment(
        1,
        {
            "teacher": "Ana",
            "subject": "Dibuix",
            "group": "1A",
            "weekly_hours": 2.0,
            "min_block_duration": 0.5,
            "max_consecutive_hours": 2.0,
            "max_session_days": "1",
        },
        set(),
        set(),
    )

    assert requirement.max_days == 1


def test_max_session_days_field_is_used_when_present() -> None:
    """Si les dades acadèmiques venen amb `max_session_days`, aquest valor
    és el que ha de decidir com es reparteix el bloc i no el default de 1."""
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
    )

    requirement = use_cases._build_requirement_from_assignment(
        1,
        {
            "teacher": "Ana",
            "subject": "Dibuix",
            "group": "1A",
            "weekly_hours": 3.0,
            "min_block_duration": 0.5,
            "max_consecutive_hours": 2.0,
            "max_session_days": "2",
        },
        set(),
        set(),
    )

    assert requirement.max_days == 2


def test_max_session_days_missing_falls_back_to_default() -> None:
    """Sense max_session_days configurat, per defecte no es reparteix
    (max_days=1): una casella buida vol dir "va tot en un sol bloc"."""
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
    )

    requirement = use_cases._build_requirement_from_assignment(
        1,
        {
            "teacher": "Ana",
            "subject": "Dibuix",
            "group": "1A",
            "weekly_hours": 2.0,
            "min_block_duration": 0.5,
            "max_consecutive_hours": 2.0,
        },
        set(),
        set(),
    )

    assert requirement.max_days == 1


def test_preferred_teacher_availability_accepts_excel_slot_format() -> None:
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
        time_labels={
            "day_names": ["Dilluns", "Dimarts"],
            "hour_names": ["8:00", "8:30"],
        },
    )

    blocked_slots = use_cases._expand_preferred_availability_to_blocked_slots(
        ["Dilluns 8:00", "Dilluns 8:30"],
        ["Dilluns", "Dimarts"],
        ["8:00", "8:30"],
    )

    assert "Dilluns 8:00" not in blocked_slots
    assert "Dilluns 8:30" not in blocked_slots
    assert "Dimarts 8:00" in blocked_slots
    assert "Dimarts 8:30" in blocked_slots


def test_unavailable_teacher_slots_accept_hyphenated_format() -> None:
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0], periods_per_day=1),
        academic_data_repo=AcademicDataRepository(),
        time_labels={"day_names": ["Dilluns"], "hour_names": ["8:00"]},
    )

    blocked = use_cases._build_blocked_activities_from_restrictions(
        [{"teacher": "Carme", "unavailable_slots": ["Dilluns-8:00"]}],
        [],
    )

    assert len(blocked) == 1
    assert blocked[0].teacher_id == "Carme"
    assert blocked[0].day == 0
    assert blocked[0].start_timeslot.period == 0