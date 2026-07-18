import pytest
from fastapi import HTTPException

from backend.routes.schedule_explanations import explain_activity
from backend.scheduler_engine.engine_instance import engine as shared_engine
from backend.scheduler_engine.models import Activity, Schedule


@pytest.fixture(autouse=True)
def reset_engine_state():
    shared_engine.load(Schedule())
    yield
    shared_engine.load(Schedule())


def _load_active_schedule():
    schedule = Schedule()
    schedule.add(
        Activity(
            id=10,
            teacher="t1",
            subject="Hist",
            group="2A",
            room="R1",
            day="Day 0",
            start="Period 0",
            duration=2,
        )
    )
    shared_engine.load(schedule)


def test_explanation_endpoint_returns_payload_for_existing_activity():
    _load_active_schedule()

    payload = explain_activity(10)

    assert payload["activity_id"] == 10
    assert "satisfied_constraints" in payload
    assert "violated_preferences" in payload
    assert "score_contribution" in payload
    assert "human_readable_explanation" in payload


def test_explanation_endpoint_returns_404_for_missing_activity():
    _load_active_schedule()

    with pytest.raises(HTTPException) as excinfo:
        explain_activity(999)

    assert excinfo.value.status_code == 404
