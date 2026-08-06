from application.live_schedule_use_cases import LiveScheduleUseCases
from repositories.academic_data_repository import AcademicDataRepository
from repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
from scheduler_engine.engine import SchedulerEngine


class InMemoryWorkingTimetableRepository(WorkingTimetableRepository):
    def __init__(self) -> None:
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        return self._snapshot

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._snapshot = snapshot


def _build_use_cases() -> LiveScheduleUseCases:
    return LiveScheduleUseCases(
        engine=SchedulerEngine(),
        working_timetable_repo=InMemoryWorkingTimetableRepository(),
        academic_data_repo=AcademicDataRepository(),
    )


def test_toggle_group_break_persists_restriction_without_creating_break_activity():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Monday",
                "start": "8:00",
                "duration": 2,
            },
            {
                "id": 2,
                "teacher": "B",
                "subject": "Hist",
                "group": "1A",
                "room": "R2",
                "day": "Monday",
                "start": "10:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Monday")
    assert activated.get("ok") is True
    assert activated.get("active") is True

    activities = activated.get("activities") or []
    assert not any((item.get("subject") or "").strip().lower() == "descans" for item in activities)

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Monday" in (restriction.get("break_days") or [])

    deactivated = use_cases.toggle_group_break("1A", "Monday")
    assert deactivated.get("ok") is True
    assert deactivated.get("active") is False

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Monday" not in (restriction.get("break_days") or [])


def test_toggle_group_break_accepts_catalan_day_with_english_schedule_days():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Wednesday",
                "start": "8:00",
                "duration": 2,
            },
            {
                "id": 2,
                "teacher": "B",
                "subject": "Hist",
                "group": "1A",
                "room": "R2",
                "day": "Wednesday",
                "start": "10:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dimecres")
    assert activated.get("ok") is True
    assert activated.get("active") is True

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Dimecres" in (restriction.get("break_days") or [])


def test_toggle_group_break_fails_cleanly_when_no_gap_window():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Dilluns",
                "start": "8:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dilluns")
    assert activated.get("ok") is False
    assert activated.get("error") == "no_free_slot"
    assert activated.get("active") is False

    restriction = next(
        (item for item in use_cases._academic_data_repo.list_group_restrictions() if item.get("group") == "1A"),
        None,
    )
    assert restriction is None or "Dilluns" not in (restriction.get("break_days") or [])
