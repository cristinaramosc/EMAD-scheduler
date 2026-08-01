from backend.bootstrap import reset_dependencies
from backend.dependencies import get_live_schedule_use_cases


def test_load_accepts_activity_payload() -> None:
    reset_dependencies()
    result = get_live_schedule_use_cases().load(
        [
            {
                "id": 1,
                "teacher": "Eli",
                "subject": "Hª del DG",
                "group": "1r APGI",
                "room": "Aula 1",
                "day": "Dilluns",
                "start": "8:00",
                "duration": 2,
            }
        ]
    )

    assert result["status"] == "ok"
    assert result["loaded"] == 1

    state = get_live_schedule_use_cases().state()
    assert isinstance(state.get("activities"), list)
    assert isinstance(state.get("conflicts"), list)
    assert len(state["activities"]) == 1
