from __future__ import annotations

from typing import Dict

from .constraint_evaluator import ConstraintEvaluator
from .models import ConstraintReport, GenerationContext, ScheduleProposal, ScoreBreakdown

try:
    from backend.scheduler_engine.quarter_utils import quarter_suffix
    from backend.scheduler_engine.teacher_utils import teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.quarter_utils import quarter_suffix
    from scheduler_engine.teacher_utils import teacher_names


class ProposalScorer:
    """A lightweight, domain-only scorer for ScheduleProposal objects."""

    def __init__(self, constraint_evaluator: ConstraintEvaluator | None = None) -> None:
        self._constraint_evaluator = constraint_evaluator or ConstraintEvaluator()

    def calculate(self, proposal: ScheduleProposal, context: GenerationContext) -> ScoreBreakdown:
        report = self._constraint_evaluator.evaluate(proposal, context)
        report.warnings.extend(proposal.warnings)
        compactness_score = self._compactness_score(report)
        distribution_score = self._distribution_score(proposal, context)
        teacher_affinity_score = self._teacher_affinity_score(proposal)
        gap_penalty = self._gap_penalty(report)
        warning_penalty = self._warning_penalty(report)

        total_score = compactness_score + distribution_score + teacher_affinity_score - gap_penalty - warning_penalty
        metadata = {
            "activity_count": len(proposal.activities),
            "warning_count": len(proposal.warnings),
            "soft_violation_count": len(report.soft_violations),
            "teacher_affinity_score": round(teacher_affinity_score, 3),
        }
        return ScoreBreakdown(
            total_score=round(total_score, 3),
            compactness_score=round(compactness_score, 3),
            distribution_score=round(distribution_score, 3),
            gap_penalty=round(gap_penalty, 3),
            warning_penalty=round(warning_penalty, 3),
            metadata=metadata,
        )

    def _compactness_score(self, report: ConstraintReport) -> float:
        if not report.statistics.get("activity_count", 0):
            return 0.0

        return 8.0 + report.statistics["activity_count"] - report.statistics["soft_violation_count"] * 1.5

    def _distribution_score(self, proposal: ScheduleProposal, context: GenerationContext) -> float:
        if not proposal.activities:
            return 0.0

        allowed_days = set(context.school_calendar.days)
        day_counts: Dict[str, int] = {str(day): 0 for day in allowed_days}
        for activity in proposal.activities:
            day_key = activity.day
            if day_key in day_counts:
                day_counts[day_key] += 1

        counts = [count for count in day_counts.values() if count > 0]
        if not counts:
            return 0.0

        return max(0.0, 10.0 - (max(counts) - min(counts)) * 2.0)

    def _teacher_affinity_score(self, proposal: ScheduleProposal) -> float:
        if len(proposal.activities) < 2:
            return 0.0

        bonus = 0.0
        activities = proposal.activities

        for index, first in enumerate(activities):
            first_teachers = set(teacher_names(first.teacher))
            if not first_teachers:
                continue

            first_quarter = quarter_suffix(first.subject) or quarter_suffix(first.group)

            for second in activities[index + 1 :]:
                second_teachers = set(teacher_names(second.teacher))
                if not second_teachers or first_teachers.isdisjoint(second_teachers):
                    continue

                pair_bonus = 0.1
                if first.day == second.day:
                    pair_bonus += 0.15

                second_quarter = quarter_suffix(second.subject) or quarter_suffix(second.group)
                if first_quarter and second_quarter:
                    pair_bonus += 0.25
                    if first_quarter != second_quarter:
                        pair_bonus += 0.1

                bonus += pair_bonus

        return bonus

    def _gap_penalty(self, report: ConstraintReport) -> float:
        return len(report.soft_violations) * 0.5

    def _warning_penalty(self, report: ConstraintReport) -> float:
        return len(report.warnings) * 2.0
