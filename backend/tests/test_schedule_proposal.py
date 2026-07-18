from scheduler_engine.models import Activity, Conflict, ScheduleProposal


def test_schedule_proposal_defaults():
    proposal = ScheduleProposal(id="proposal-1")

    assert proposal.id == "proposal-1"
    assert proposal.activities == []
    assert proposal.score == 0.0
    assert proposal.conflicts == []
    assert proposal.warnings == []
    assert proposal.metadata == {}


def test_schedule_proposal_with_values():
    activity = Activity(
        id=1,
        teacher="t1",
        subject="s1",
        group="g1",
        room="r1",
        day="Monday",
        start="09:00",
        duration=2,
    )
    conflict = Conflict(
        type="room_conflict",
        message="Conflict here",
        room="r1",
        day="Monday",
        start="09:00",
        activities=[1, 2],
    )

    proposal = ScheduleProposal(
        id="proposal-2",
        activities=[activity],
        score=42.5,
        conflicts=[conflict],
        warnings=["Overload"],
        metadata={"source": "test"},
    )

    assert proposal.id == "proposal-2"
    assert proposal.activities == [activity]
    assert proposal.score == 42.5
    assert proposal.conflicts == [conflict]
    assert proposal.warnings == ["Overload"]
    assert proposal.metadata == {"source": "test"}
