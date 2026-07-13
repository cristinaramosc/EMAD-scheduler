from pathlib import Path

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_live_schedule_use_cases, get_scheduler_use_cases


def test_load_fet_populates_academic_data_repository() -> None:
    reset_dependencies()
    fet_file_path = Path(__file__).resolve().parents[2] / "EMAD_2627_.fet"
    content = fet_file_path.read_bytes()

    result = get_live_schedule_use_cases().load_fet(content)

    assert result["ok"] is True
    assert result["loaded"] > 0

    summary = get_academic_data_repo().summary()
    assert summary["teachers"] > 0
    assert summary["groups"] > 0
    assert summary["subjects"] > 0
    assert summary["teaching_assignments"] > 0

    teachers = get_academic_data_repo().list_teachers()
    assert any("Eli" in teacher["name"] for teacher in teachers)


def test_generate_proposal_keeps_academic_data_unchanged() -> None:
    reset_dependencies()
    fet_file_path = Path(__file__).resolve().parents[2] / "EMAD_2627_.fet"
    content = fet_file_path.read_bytes()

    get_live_schedule_use_cases().load_fet(content)
    repo = get_academic_data_repo()

    before_summary = repo.summary()
    before_assignments = repo.active_canonical_assignments()
    before_teachers = repo.list_teachers()

    get_scheduler_use_cases().generate_proposals([])

    after_summary = repo.summary()
    after_assignments = repo.active_canonical_assignments()
    after_teachers = repo.list_teachers()

    assert after_summary == before_summary
    assert after_assignments == before_assignments
    assert after_teachers == before_teachers
