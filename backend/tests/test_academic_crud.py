from __future__ import annotations

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_scheduler_use_cases
from backend.main import app
from fastapi.testclient import TestClient


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


def test_subject_list_includes_names_from_existing_assignments():
    reset_dependencies()
    repo = get_academic_data_repo()
    repo.apply_snapshot({"teachers": [{"name": "T1"}], "groups": [{"name": "G1"}]})
    repo.create_or_update_canonical_assignment({
        "teacher": "T1",
        "subject": "Assignatura existent",
        "group": "G1",
        "weekly_hours": 2.0,
    })

    response = TestClient(app).get("/academic-data/subjects")

    assert response.status_code == 200
    assert any(item["name"] == "Assignatura existent" for item in response.json())


def test_create_assignment_registers_missing_subject_catalog_entry():
    reset_dependencies()
    repo = get_academic_data_repo()
    repo.apply_snapshot({"teachers": [{"name": "T1"}], "groups": [{"name": "G1"}]})

    response = TestClient(app).post(
        "/academic-data/assignments",
        json={"teacher": "T1", "subject": "Nova assignatura", "group": "G1", "weekly_hours": 2},
    )

    assert response.status_code == 200
    assert any(item["name"] == "Nova assignatura" for item in repo.list_subjects())


def test_teachers_list_reports_the_groups_each_teacher_tutors():
    """A la fitxa del professor hi ha de constar de quins grups és tutor/a
    (la dada viu al grup; això només la resumeix)."""
    reset_dependencies()
    repo = get_academic_data_repo()
    repo.apply_snapshot({
        "teachers": [{"name": "Jordi"}, {"name": "Eli"}],
        "groups": [{"name": "2n COM", "tutor": "Jordi"}, {"name": "1r COM", "tutor": "Eli"}],
    })

    teachers = {item["name"]: item for item in TestClient(app).get("/academic-data/teachers").json()}

    assert teachers["Jordi"]["tutor_of"] == "2n COM"
    assert teachers["Eli"]["tutor_of"] == "1r COM"


def test_teachers_max_days_is_saved_in_the_teacher_restriction():
    """El "Màxim de dies de classe per setmana" del professor s'ha de poder
    desar des de la fitxa del professor i quedar guardat com a restricció."""
    reset_dependencies()
    repo = get_academic_data_repo()
    repo.apply_snapshot({"teachers": [{"name": "Jordi"}], "groups": [{"name": "2n COM"}]})
    client = TestClient(app)

    response = client.patch("/academic-data/teachers/Jordi", json={"max_days": 4})

    assert response.status_code == 200
    restriction = next(r for r in repo.list_teacher_restrictions() if r["teacher"] == "Jordi")
    assert restriction["max_days"] == 4
    listed = {item["name"]: item for item in client.get("/academic-data/teachers").json()}
    assert listed["Jordi"]["max_days"] == 4


def test_clearing_teacher_max_days_keeps_the_other_restrictions():
    """Buidar el màxim de dies (0) l'ha de treure sense esborrar la resta de
    restriccions del professor (franges, sense buits...)."""
    reset_dependencies()
    repo = get_academic_data_repo()
    repo.apply_snapshot({"teachers": [{"name": "Jordi"}], "groups": [{"name": "2n COM"}]})
    repo.upsert_teacher_restriction({
        "teacher": "Jordi",
        "max_days": 4,
        "no_gaps": True,
        "unavailable_slots": ["Dilluns 8:00"],
    })

    response = TestClient(app).patch("/academic-data/teachers/Jordi", json={"max_days": 0})

    assert response.status_code == 200
    restriction = next(r for r in repo.list_teacher_restrictions() if r["teacher"] == "Jordi")
    assert not restriction.get("max_days")
    assert restriction["no_gaps"] is True
    assert restriction["unavailable_slots"] == ["Dilluns 8:00"]
