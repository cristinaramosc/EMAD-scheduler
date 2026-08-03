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
            "break_days": ["Monday"],
            "break_slots": ["Monday 10:00"],
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
    assert data["break_days"] == ["Monday"]
    assert data["break_slots"] == ["Monday 10:00"]

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
    assert stored["break_days"] == ["Monday"]
    assert stored["break_slots"] == ["Monday 10:00"]


def test_toggle_break_endpoint_persists_group_break_days() -> None:
    reset_dependencies()

    repo = get_academic_data_repo()
    repo.apply_snapshot(
        {
            "teachers": [{"name": "A"}, {"name": "B"}],
            "groups": [{"name": "1A"}],
            "subjects": [{"name": "Mat"}, {"name": "Hist"}],
            "teaching_assignments": [
                {
                    "teacher": "A",
                    "subject": "Mat",
                    "group": "1A",
                    "weekly_hours": 2.0,
                },
                {
                    "teacher": "B",
                    "subject": "Hist",
                    "group": "1A",
                    "weekly_hours": 2.0,
                },
            ],
        }
    )

    # Horari mínim per permetre obertura de forat de descans.
    get_live_schedule_use_cases().load(
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

    client = TestClient(app)
    response = client.post("/scheduler/breaks/toggle", json={"group": "1A", "day": "Monday"})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert payload.get("active") is True

    stored = next((item for item in repo.list_group_restrictions() if item.get("group") == "1A"), None)
    assert stored is not None
    assert "Monday" in (stored.get("break_days") or [])
    assert any(str(slot).startswith("Monday ") for slot in (stored.get("break_slots") or []))
