import pytest

from scheduler_engine.models import Activity, GenerationContext, GenerationResult, ScheduleProposal, SchoolCalendar
from scheduler_engine.search_engine import SearchEngine


@pytest.fixture
def sample_context() -> GenerationContext:
    return GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )


def make_proposal(proposal_id: str, *, warnings=None, day: str = "Day 0", start: str = "Period 0") -> ScheduleProposal:
    return ScheduleProposal(
        id=proposal_id,
        activities=[
            Activity(id=1, teacher="t", subject="s", group="g", room="r", day=day, start=start, duration=1)
        ],
        warnings=list(warnings or []),
    )


def test_search_engine_orders_proposals_from_best_to_worst(sample_context: GenerationContext) -> None:
    engine = SearchEngine()
    generation_result = GenerationResult(
        generated_scheduled_activities=[],
        proposals=[
            make_proposal("proposal-bad", warnings=["warning"]),
            make_proposal("proposal-good"),
        ],
        valid=True,
    )

    result = engine.search(generation_result, sample_context)

    assert result.best_proposal is not None
    assert result.best_proposal.id == "proposal-good"
    assert [proposal.id for proposal in result.proposals] == ["proposal-good", "proposal-bad"]


def test_search_engine_removes_duplicate_proposals(sample_context: GenerationContext) -> None:
    engine = SearchEngine()
    duplicate = make_proposal("proposal-duplicate")
    generation_result = GenerationResult(
        generated_scheduled_activities=[],
        proposals=[duplicate, make_proposal("proposal-duplicate"), make_proposal("proposal-other")],
        valid=True,
    )

    result = engine.search(generation_result, sample_context)

    assert [proposal.id for proposal in result.proposals] == ["proposal-duplicate", "proposal-other"]


def test_search_engine_is_deterministic(sample_context: GenerationContext) -> None:
    engine = SearchEngine()
    generation_result = GenerationResult(
        generated_scheduled_activities=[],
        proposals=[make_proposal("proposal-b"), make_proposal("proposal-a")],
        valid=True,
    )

    first = engine.search(generation_result, sample_context)
    second = engine.search(generation_result, sample_context)

    assert [proposal.id for proposal in first.proposals] == [proposal.id for proposal in second.proposals]
    assert first.best_proposal.id == second.best_proposal.id


def test_search_engine_handles_an_empty_proposal_list(sample_context: GenerationContext) -> None:
    engine = SearchEngine()
    generation_result = GenerationResult(generated_scheduled_activities=[], proposals=[], valid=True)

    result = engine.search(generation_result, sample_context)

    assert result.best_proposal is None
    assert result.proposals == []
    assert result.statistics["proposals_generated"] == 0


def test_search_engine_handles_a_single_proposal(sample_context: GenerationContext) -> None:
    engine = SearchEngine()
    generation_result = GenerationResult(
        generated_scheduled_activities=[],
        proposals=[make_proposal("proposal-only")],
        valid=True,
    )

    result = engine.search(generation_result, sample_context)

    assert result.best_proposal is not None
    assert result.best_proposal.id == "proposal-only"
    assert len(result.proposals) == 1
