import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_live_schedule_use_cases
from backend.main import app


def test_teacher_restrictions_can_be_persisted() -> None:
    reset_dependencies()

    repo = get_academic_data_repo()
    repo.apply_snapshot(
        {
            "teachers": [{"name": "Eli"}],
            "groups": [{"name": "1A"}],
            "subjects": [{"name": "Matemàtiques"}],
            "teaching_assignments": [
                {
                    "teacher": "Eli",
                    "subject": "Matemàtiques",
                    "group": "1A",
                    "weekly_hours": 2.0,
                }
            ],
        }
    )

    teacher = repo.list_teachers()[0]["name"]

    client = TestClient(app)
    patch_response = client.patch(
        f"/academic-data/teachers/{teacher}/restrictions",
        json={
            "teacher": teacher,
            "no_gaps": True,
            "max_hours_per_day": 4,
            "max_consecutive_hours": 2,
            "preferred_availability": ["Dilluns-8:00"],
            "unavailable_slots": ["Dimarts-9:00"],
        },
    )
    assert patch_response.status_code == 200

    get_response = client.get(f"/academic-data/teachers/{teacher}/restrictions")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["teacher"] == teacher
    assert data["no_gaps"] is True
    assert data["max_hours_per_day"] == 4
    assert data["max_consecutive_hours"] == 2
    assert data["preferred_availability"] == ["Dilluns-8:00"]
    assert "Dimarts-9:00" in data["unavailable_slots"]

    stored = next((item for item in repo.list_teacher_restrictions() if item["teacher"] == teacher), None)
    assert stored is not None
    assert stored["teacher"] == teacher
    assert stored["no_gaps"] is True
    assert stored["max_hours_per_day"] == 4
    assert stored["max_consecutive_hours"] == 2
    assert stored["preferred_availability"] == ["Dilluns-8:00"]
    assert stored["unavailable_slots"] == ["Dimarts-9:00"]
