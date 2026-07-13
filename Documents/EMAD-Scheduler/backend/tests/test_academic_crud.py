from __future__ import annotations

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_scheduler_use_cases


def test_create_assignment_and_sessions_and_generate():
    reset_dependencies()
    repo = get_academic_data_repo()

    # create entities
    repo.apply_snapshot({
        "teachers": [{"name": "T1"}],
        "groups": [{"name": "G1"}],
        "subjects": [{"name": "S1"}],
    })

    # create canonical assignment 5h per week allowed 2.5 -> should produce 2 sessions
    repo.create_or_update_canonical_assignment({
        "teacher": "T1",
        "subject": "S1",
        "group": "G1",
        "weekly_hours": 5.0,
        "allowed_session_lengths": [2.5],
    })

    sessions = repo.active_teaching_assignments()
    assert len(sessions) == 2
    assert sum(s.get("weekly_hours", 0) for s in sessions) == 5.0

    # ensure scheduler picks academic data
    use_cases = get_scheduler_use_cases()
    body = use_cases.generate_proposals([])
    assert body["statistics"]["source"] == "academic_workbook"


def test_change_assignment_teacher_updates_sessions():
    reset_dependencies()
    repo = get_academic_data_repo()

    repo.apply_snapshot({
        "teachers": [{"name": "Old"}, {"name": "New"}],
        "groups": [{"name": "G1"}],
        "subjects": [{"name": "S1"}],
    })

    repo.create_or_update_canonical_assignment({
        "teacher": "Old",
        "subject": "S1",
        "group": "G1",
        "weekly_hours": 6.0,
        "allowed_session_lengths": [3.0],
    })

    # change teacher by updating canonical assignment
    repo.create_or_update_canonical_assignment({
        "teacher": "New",
        "subject": "S1",
        "group": "G1",
        "weekly_hours": 6.0,
        "allowed_session_lengths": [3.0],
    })

    sessions = repo.active_teaching_assignments()
    assert all(s["teacher"] == "New" for s in sessions)
