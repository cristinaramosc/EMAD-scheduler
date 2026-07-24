from pathlib import Path

from backend.application.live_schedule_use_cases import LiveScheduleUseCases
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.repositories.working_timetable_repository import JsonWorkingTimetableRepository
from backend.scheduler_engine.engine_instance import engine as scheduler_engine
from backend.services.fet_importer import load_activities, load_scheduler_activities


def test_load_fet_stores_weekly_hours_not_raw_blocks(tmp_path) -> None:
    """Reproduces the reported bug: 'Hª del DG' at '1r APGI' is split across
    two FET activities of 2 blocks (1h) each -> 2h total. Before the fix, the
    raw block count (4) was stored directly as weekly_hours, showing 4h
    instead of the correct 2h."""
    fet_file_path = Path(__file__).resolve().parents[2] / "EMAD_2627_.fet"

    working_timetable_repo = JsonWorkingTimetableRepository(tmp_path / "working_timetable.json")
    academic_data_repo = AcademicDataRepository()

    use_cases = LiveScheduleUseCases(
        engine=scheduler_engine,
        load_activities_fn=load_activities,
        load_scheduler_activities_fn=load_scheduler_activities,
        fet_file=fet_file_path,
        working_timetable_repo=working_timetable_repo,
        academic_data_repo=academic_data_repo,
    )

    result = use_cases.load_fet()
    assert result["ok"] is True

    assignments = academic_data_repo.active_canonical_assignments()
    dg_assignment = next(
        (
            a for a in assignments
            if a.get("subject") == "Hª del DG" and a.get("group") == "1r APGI"
        ),
        None,
    )

    assert dg_assignment is not None, "hauria d'existir l'assignació 'Hª del DG' / '1r APGI'"
    assert dg_assignment["weekly_hours"] == 2.0
