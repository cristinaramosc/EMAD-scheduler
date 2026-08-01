import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_academic_data_repo, get_live_schedule_use_cases
from backend.main import app


def test_group_restrictions_can_be_persisted() -> None:
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

    group = repo.list_groups()[0]["name"]

    client = TestClient(app)
    patch_response = client.patch(
        f"/academic-data/groups/{group}/restrictions",
        json={
            "group": group,
            "no_gaps": True,
            "max_hours_per_day": 4,
            "max_consecutive_hours": 2,
            "preferred_availability": ["Dilluns-8:00"],
            "unavailable_slots": ["Dimarts-9:00"],
            "daily_start_time": "8:00",
            "daily_max_end_time": "14:00",
        },
    )
    assert patch_response.status_code == 200

    get_response = client.get(f"/academic-data/groups/{group}/restrictions")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["group"] == group
    assert data["no_gaps"] is True
    assert data["max_hours_per_day"] == 4
    assert data["max_consecutive_hours"] == 2
    assert data["preferred_availability"] == ["Dilluns-8:00"]
    assert "Dimarts-9:00" in data["unavailable_slots"]
    assert data["daily_start_time"] == "8:00"
    assert data["daily_max_end_time"] == "14:00"

    stored = next((item for item in repo.list_group_restrictions() if item["group"] == group), None)
    assert stored is not None
    assert stored["group"] == group
    assert stored["no_gaps"] is True
    assert stored["max_hours_per_day"] == 4
    assert stored["max_consecutive_hours"] == 2
    assert stored["preferred_availability"] == ["Dilluns-8:00"]
    assert stored["unavailable_slots"] == ["Dimarts-9:00"]
    assert stored["daily_start_time"] == "8:00"
    assert stored["daily_max_end_time"] == "14:00"
