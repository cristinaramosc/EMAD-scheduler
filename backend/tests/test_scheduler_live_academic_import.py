from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_live_schedule_use_cases, get_scheduler_use_cases


def test_academic_snapshot_populates_repository() -> None:
    reset_dependencies()

    repo = get_academic_data_repo()
    repo.apply_snapshot(
        {
            "teachers": [{"name": "Eli"}],
            "groups": [{"name": "1r APGI"}],
            "subjects": [{"name": "Hª del DG"}],
            "rooms": [{"name": "Aula 1"}],
            "teaching_assignments": [
                {
                    "teacher": "Eli",
                    "subject": "Hª del DG",
                    "group": "1r APGI",
                    "weekly_hours": 2.0,
                }
            ],
        }
    )

    summary = get_academic_data_repo().summary()
    assert summary["teachers"] == 1
    assert summary["groups"] == 1
    assert summary["subjects"] == 1
    assert summary["teaching_assignments"] == 1

    teachers = repo.list_teachers()
    assert teachers[0]["name"] == "Eli"


def test_generate_proposal_keeps_academic_data_unchanged() -> None:
    reset_dependencies()
    repo = get_academic_data_repo()

    repo.apply_snapshot(
        {
            "teachers": [{"name": "Eli"}],
            "groups": [{"name": "1r APGI"}],
            "subjects": [{"name": "Hª del DG"}],
            "teaching_assignments": [
                {
                    "teacher": "Eli",
                    "subject": "Hª del DG",
                    "group": "1r APGI",
                    "weekly_hours": 2.0,
                }
            ],
        }
    )

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
