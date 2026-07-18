from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

try:
    from backend.scheduler_engine.constraint_evaluator import ConstraintEvaluator
    from backend.scheduler_engine.engine import SchedulerEngine
    from backend.scheduler_engine.models import Activity, GenerationContext, ScheduleProposal, SchoolCalendar
    from backend.scheduler_engine.proposal_scorer import ProposalScorer
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraint_evaluator import ConstraintEvaluator
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import Activity, GenerationContext, ScheduleProposal, SchoolCalendar
    from scheduler_engine.proposal_scorer import ProposalScorer


@dataclass
class ActivityExplanation:
    activity_id: int
    satisfied_constraints: List[str]
    violated_preferences: List[str]
    positive_preferences: List[str]
    score_contribution: Optional[float]
    score_details: Dict[str, Any]
    human_readable_explanation: str


class DecisionExplainer:
    """Read-only explanation service for already-placed activities."""

    def __init__(
        self,
        engine: SchedulerEngine,
        constraint_evaluator: ConstraintEvaluator | None = None,
        scorer: ProposalScorer | None = None,
    ) -> None:
        self._engine = engine
        self._constraint_evaluator = constraint_evaluator or ConstraintEvaluator()
        self._scorer = scorer or ProposalScorer(self._constraint_evaluator)

    def explain_activity(self, activity_id: int) -> Optional[ActivityExplanation]:
        activities = list(self._engine.state.all())
        activity = next((item for item in activities if item.id == activity_id), None)
        if activity is None:
            return None

        proposal = ScheduleProposal(id="active-schedule", activities=[self._copy_activity(a) for a in activities])
        context = GenerationContext(
            school_calendar=SchoolCalendar(),
            existing_scheduled_activities=(),
            fixed_activities=(),
            blocked_time_slots=(),
            configuration={"room_constraints_enabled": True},
        )

        report = self._constraint_evaluator.evaluate(proposal, context)
        score = self._scorer.calculate(proposal, context)
        conflicts = self._engine.validate(self._engine.state)

        related_conflicts = [
            conflict
            for conflict in conflicts
            if activity_id in (getattr(conflict, "activities", None) or [])
        ]

        satisfied_constraints = self._build_satisfied_constraints(activity, related_conflicts)
        violated_preferences = self._build_violated_preferences(activity_id, report)
        positive_preferences = self._build_positive_preferences(activity_id, report)
        contribution = self._estimate_local_score_contribution(activity_id, proposal, report, score.total_score)

        explanation = self._human_readable_text(activity, satisfied_constraints, violated_preferences, contribution)

        return ActivityExplanation(
            activity_id=activity_id,
            satisfied_constraints=satisfied_constraints,
            violated_preferences=violated_preferences,
            positive_preferences=positive_preferences,
            score_contribution=contribution,
            score_details={
                "proposal_total_score": score.total_score,
                "compactness_score": score.compactness_score,
                "distribution_score": score.distribution_score,
                "gap_penalty": score.gap_penalty,
                "warning_penalty": score.warning_penalty,
            },
            human_readable_explanation=explanation,
        )

    def to_dict(self, explanation: ActivityExplanation) -> Dict[str, Any]:
        return asdict(explanation)

    def _copy_activity(self, activity: Activity) -> Activity:
        return Activity(
            id=activity.id,
            teacher=activity.teacher,
            subject=activity.subject,
            group=activity.group,
            room=activity.room,
            day=activity.day,
            start=activity.start,
            duration=activity.duration,
        )

    def _build_satisfied_constraints(self, activity: Activity, related_conflicts: List[Any]) -> List[str]:
        if not related_conflicts:
            return [
                "teacher_conflict_free",
                "room_conflict_free",
            ]

        satisfied: List[str] = []
        conflict_types = {getattr(conflict, "type", "") for conflict in related_conflicts}
        if "teacher_conflict" not in conflict_types:
            satisfied.append("teacher_conflict_free")
        if "room_conflict" not in conflict_types:
            satisfied.append("room_conflict_free")
        return satisfied

    def _build_violated_preferences(self, activity_id: int, report) -> List[str]:
        return [
            violation.constraint_name
            for violation in report.soft_violations
            if activity_id in violation.affected_activity_ids
        ]

    def _build_positive_preferences(self, activity_id: int, report) -> List[str]:
        related = [
            violation
            for violation in report.soft_violations
            if activity_id in violation.affected_activity_ids
        ]
        if not related:
            return ["no_soft_preference_violation_for_activity"]

        present = {violation.constraint_name for violation in related}
        positives: List[str] = []
        if "gaps_inside_day" not in present:
            positives.append("no_gap_around_activity")
        if "isolated_one_hour_block" not in present:
            positives.append("not_isolated_block")
        return positives

    def _estimate_local_score_contribution(
        self,
        activity_id: int,
        proposal: ScheduleProposal,
        report,
        total_score: float,
    ) -> Optional[float]:
        if not proposal.activities:
            return None

        base_share = total_score / len(proposal.activities)
        local_violations = sum(
            1 for violation in report.soft_violations if activity_id in violation.affected_activity_ids
        )
        local_penalty = local_violations * 0.5
        return round(base_share - local_penalty, 3)

    def _human_readable_text(
        self,
        activity: Activity,
        satisfied_constraints: List[str],
        violated_preferences: List[str],
        score_contribution: Optional[float],
    ) -> str:
        constraint_text = (
            "teacher and room hard constraints were satisfied"
            if len(satisfied_constraints) == 2
            else "some hard constraints are still in conflict"
        )

        if violated_preferences:
            preference_text = (
                "soft preferences with local impact: "
                + ", ".join(violated_preferences)
            )
        else:
            preference_text = "no soft preferences were violated for this activity"

        if score_contribution is None:
            score_text = "no local score estimate is available"
        else:
            score_text = f"estimated local score contribution: {score_contribution}"

        return (
            f"Activity {activity.id} ({activity.subject}) is placed on {activity.day} at {activity.start}; "
            f"{constraint_text}; {preference_text}; {score_text}."
        )
