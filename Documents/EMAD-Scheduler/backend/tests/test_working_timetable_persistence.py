from __future__ import annotations

from pathlib import Path

from backend.bootstrap import get_dependencies, reset_dependencies
from backend.repositories.working_timetable_repository import JsonWorkingTimetableRepository, WorkingTimetableSnapshot
from backend.routes.scheduler import GenerateRequest, generate_proposals
from backend.scheduler_engine.engine_instance import engine as shared_engine
from backend.scheduler_engine.models import Activity, Schedule


def test_json_working_timetable_repository_roundtrip(tmp_path: Path) -> None:
    repo = JsonWorkingTimetableRepository(tmp_path / "working.json")
    snapshot = WorkingTimetableSnapshot(
        active_schedule=[
            {
                "id": 1,
                "teacher": "t1",
                "subject": "s1",
                "group": "g1",
                "room": "r1",
                "day": "Dilluns",
                "start": "8:00",
                "duration": 2,
            }
        ],
        current_proposal={"id": "p1", "activities": [], "score": 0.0, "warnings": [], "conflicts": [], "metadata": {}},
        generation_stats={"blocks_total": 1},
        unscheduled_activities=[{"id": 9, "subject": "Math"}],
        metadata={"last_source": "proposal"},
    )

    repo.save_snapshot(snapshot)

    loaded = repo.load_snapshot()

    assert loaded.active_schedule == snapshot.active_schedule
    assert loaded.current_proposal == snapshot.current_proposal
    assert loaded.generation_stats == snapshot.generation_stats
    assert loaded.unscheduled_activities == snapshot.unscheduled_activities
    assert loaded.metadata["last_source"] == "proposal"


def test_state_is_restored_after_dependency_reset(tmp_path: Path, monkeypatch) -> None:
    persistence_file = tmp_path / "working.json"
    monkeypatch.setenv("EMAD_WORKING_TIMETABLE_FILE", str(persistence_file))

    reset_dependencies()
    shared_engine.load(Schedule())
    deps = get_dependencies()
    schedule = Schedule()
    schedule.add(
        Activity(
            id=1,
            teacher="t1",
            subject="s1",
            group="g1",
            room="r1",
            day="Dilluns",
            start="8:00",
            duration=2,
        )
    )
    shared_engine.load(schedule)
    deps.live_schedule_use_cases._persist_active_schedule(clear_proposal=True)

    reset_dependencies()
    restored = get_dependencies()

    assert len(restored.live_schedule_use_cases.state()["activities"]) == 1
    assert restored.live_schedule_use_cases.state()["activities"][0]["subject"] == "s1"


def test_pending_proposal_is_restored_after_dependency_reset(tmp_path: Path, monkeypatch) -> None:
    persistence_file = tmp_path / "working.json"
    monkeypatch.setenv("EMAD_WORKING_TIMETABLE_FILE", str(persistence_file))

    reset_dependencies()
    shared_engine.load(Schedule())
    body = generate_proposals(GenerateRequest(requirement_ids=[]))
    proposal_id = body["best_proposal"]["id"]

    reset_dependencies()
    restored = get_dependencies()
    state = restored.live_schedule_use_cases.state()

    assert state["proposal"] is not None
    assert state["proposal"]["id"] == proposal_id
    assert state["unscheduled_activities"]