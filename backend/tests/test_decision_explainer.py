from backend.services.decision_explainer import DecisionExplainer
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import Activity, Schedule


def _build_schedule() -> Schedule:
    schedule = Schedule()
    schedule.add(
        Activity(
            id=1,
            teacher="t1",
            subject="Dibuix",
            group="1A",
            room="R1",
            day="Day 0",
            start="Period 0",
            duration=2,
        )
    )
    schedule.add(
        Activity(
            id=2,
            teacher="t2",
            subject="Color",
            group="1A",
            room="R2",
            day="Day 0",
            start="Period 2",
            duration=1,
        )
    )
    return schedule


def test_decision_explainer_returns_explanation_for_existing_activity():
    engine = SchedulerEngine()
    engine.load(_build_schedule())
    explainer = DecisionExplainer(engine)

    explanation = explainer.explain_activity(1)

    assert explanation is not None
    assert explanation.activity_id == 1
    assert "teacher_conflict_free" in explanation.satisfied_constraints
    assert isinstance(explanation.human_readable_explanation, str)
    assert explanation.human_readable_explanation


def test_decision_explainer_is_read_only():
    engine = SchedulerEngine()
    engine.load(_build_schedule())
    explainer = DecisionExplainer(engine)

    before = [(a.id, a.day, a.start) for a in engine.state.all()]
    _ = explainer.explain_activity(1)
    after = [(a.id, a.day, a.start) for a in engine.state.all()]

    assert before == after


def test_decision_explainer_returns_none_for_missing_activity():
    engine = SchedulerEngine()
    engine.load(_build_schedule())
    explainer = DecisionExplainer(engine)

    assert explainer.explain_activity(999) is None
