from __future__ import annotations

from typing import Dict

from .constraint_evaluator import ConstraintEvaluator
from .models import ConstraintReport, GenerationContext, ScheduleProposal, ScoreBreakdown


class ProposalScorer:
    """A lightweight, domain-only scorer for ScheduleProposal objects."""

    def __init__(self, constraint_evaluator: ConstraintEvaluator | None = None) -> None:
        self._constraint_evaluator = constraint_evaluator or ConstraintEvaluator()

    def calculate(self, proposal: ScheduleProposal, context: GenerationContext) -> ScoreBreakdown:
        report = self._constraint_evaluator.evaluate(proposal, context)
        report.warnings.extend(proposal.warnings)
        compactness_score = self._compactness_score(report)
        distribution_score = self._distribution_score(proposal, context)
        gap_penalty = self._gap_penalty(report)
        warning_penalty = self._warning_penalty(report)

        total_score = compactness_score + distribution_score - gap_penalty - warning_penalty
        metadata = {
            "activity_count": len(proposal.activities),
            "warning_count": len(proposal.warnings),
            "soft_violation_count": len(report.soft_violations),
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

    def _gap_penalty(self, report: ConstraintReport) -> float:
        return len(report.soft_violations) * 0.5

    def _warning_penalty(self, report: ConstraintReport) -> float:
        return len(report.warnings) * 2.0
