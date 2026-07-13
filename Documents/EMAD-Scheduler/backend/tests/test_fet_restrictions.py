from pathlib import Path

from backend.application.scheduler_use_cases import SchedulerUseCases
from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_live_schedule_use_cases
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import SchoolCalendar
from backend.services.fet_importer import load_generation_inputs


def test_fet_importer_builds_blocked_activities_for_teacher_and_group_restrictions(tmp_path: Path) -> None:
    fet_file = tmp_path / "sample.fet"
    fet_file.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<FET>
  <Days_List>
    <Number_of_Days>2</Number_of_Days>
    <Day>
      <Name>Dilluns</Name>
    </Day>
    <Day>
      <Name>Dimarts</Name>
    </Day>
  </Days_List>
  <Hours_List>
    <Number_of_Hours>2</Number_of_Hours>
    <Hour>
      <Name>8:00</Name>
    </Hour>
    <Hour>
      <Name>9:00</Name>
    </Hour>
  </Hours_List>
  <ConstraintTeacherNotAvailableTimes>
    <Teacher>Ana</Teacher>
    <Not_Available_Time>
      <Day>Dilluns</Day>
      <Hour>8:00</Hour>
    </Not_Available_Time>
  </ConstraintTeacherNotAvailableTimes>
  <ConstraintStudentsSetNotAvailableTimes>
    <Students>1A</Students>
    <Not_Available_Time>
      <Day>Dimarts</Day>
      <Hour>9:00</Hour>
    </Not_Available_Time>
  </ConstraintStudentsSetNotAvailableTimes>
</FET>
"""
    )

    payload = load_generation_inputs(fet_file)

    assert len(payload["blocked_activities"]) == 2
    assert any(activity.metadata.get("constraint") == "teacher_not_available" for activity in payload["blocked_activities"])
    assert any(activity.metadata.get("constraint") == "group_not_available" for activity in payload["blocked_activities"])


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


def test_load_fet_imports_restrictions_into_academic_repository(tmp_path: Path) -> None:
    reset_dependencies()

    fet_file = tmp_path / "sample.fet"
    fet_file.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<FET>
  <Days_List>
    <Number_of_Days>2</Number_of_Days>
    <Day>
      <Name>Dilluns</Name>
    </Day>
    <Day>
      <Name>Dimarts</Name>
    </Day>
  </Days_List>
  <Hours_List>
    <Number_of_Hours>2</Number_of_Hours>
    <Hour>
      <Name>8:00</Name>
    </Hour>
    <Hour>
      <Name>9:00</Name>
    </Hour>
  </Hours_List>
  <ConstraintTeacherNotAvailableTimes>
    <Teacher>Ana</Teacher>
    <Not_Available_Time>
      <Day>Dilluns</Day>
      <Hour>8:00</Hour>
    </Not_Available_Time>
  </ConstraintTeacherNotAvailableTimes>
  <ConstraintStudentsSetNotAvailableTimes>
    <Students>1A</Students>
    <Not_Available_Time>
      <Day>Dimarts</Day>
      <Hour>9:00</Hour>
    </Not_Available_Time>
  </ConstraintStudentsSetNotAvailableTimes>
</FET>
""")

    content = fet_file.read_bytes()
    get_live_schedule_use_cases().load_fet(content)

    repo = get_academic_data_repo()
    assert any(restriction["teacher"] == "Ana" for restriction in repo.list_teacher_restrictions())
    assert any(restriction["group"] == "1A" for restriction in repo.list_group_restrictions())
