from __future__ import annotations

from typing import List

from .models import ConstraintReport, ConstraintViolation, GenerationContext, ScheduleProposal


class ConstraintEvaluator:
    """Evaluates soft timetable constraints independently from scoring."""

    def evaluate(self, proposal: ScheduleProposal, context: GenerationContext) -> ConstraintReport:
        soft_violations: List[ConstraintViolation] = []
        warnings: List[str] = []

        if not proposal.activities:
            return ConstraintReport(soft_violations=[], warnings=[], statistics={"activity_count": 0})

        soft_violations.extend(self._evaluate_gaps(proposal))
        soft_violations.extend(self._evaluate_too_many_teaching_days(proposal))
        soft_violations.extend(self._evaluate_fragmented_timetable(proposal))
        soft_violations.extend(self._evaluate_isolated_one_hour_blocks(proposal))

        statistics = {
            "activity_count": len(proposal.activities),
            "soft_violation_count": len(soft_violations),
            "warning_count": len(warnings),
        }
        return ConstraintReport(soft_violations=soft_violations, warnings=warnings, statistics=statistics)

    def _evaluate_gaps(self, proposal: ScheduleProposal) -> List[ConstraintViolation]:
        violations: List[ConstraintViolation] = []
        activities_by_day = {}
        for activity in proposal.activities:
            activities_by_day.setdefault(activity.day, []).append(activity)

        for day, activities in activities_by_day.items():
            sorted_activities = sorted(activities, key=lambda activity: int(activity.start.split()[-1]))
            for index in range(1, len(sorted_activities)):
                previous = sorted_activities[index - 1]
                current = sorted_activities[index]
                gap = int(current.start.split()[-1]) - (int(previous.start.split()[-1]) + previous.duration)
                if gap > 0:
                    violations.append(
                        ConstraintViolation(
                            constraint_name="gaps_inside_day",
                            severity="soft",
                            message="Gap present inside the teaching day",
                            affected_activity_ids=[previous.id, current.id],
                            metadata={"day": day, "gap": gap},
                        )
                    )
        return violations

    def _evaluate_too_many_teaching_days(self, proposal: ScheduleProposal) -> List[ConstraintViolation]:
        activity_days = {activity.day for activity in proposal.activities}
        if len(activity_days) > 2:
            return [
                ConstraintViolation(
                    constraint_name="too_many_teaching_days",
                    severity="soft",
                    message="Proposal uses too many teaching days",
                    affected_activity_ids=[activity.id for activity in proposal.activities],
                    metadata={"day_count": len(activity_days)},
                )
            ]
        return []

    def _evaluate_fragmented_timetable(self, proposal: ScheduleProposal) -> List[ConstraintViolation]:
        if len(proposal.activities) <= 2:
            return []
        return [
            ConstraintViolation(
                constraint_name="fragmented_timetable",
                severity="soft",
                message="Timetable is fragmented",
                affected_activity_ids=[activity.id for activity in proposal.activities],
                metadata={"activity_count": len(proposal.activities)},
            )
        ]

    def _evaluate_isolated_one_hour_blocks(self, proposal: ScheduleProposal) -> List[ConstraintViolation]:
        violations: List[ConstraintViolation] = []
        for activity in proposal.activities:
            if activity.duration == 1:
                violations.append(
                    ConstraintViolation(
                        constraint_name="isolated_one_hour_block",
                        severity="soft",
                        message="One-hour block is isolated",
                        affected_activity_ids=[activity.id],
                        metadata={"duration": activity.duration},
                    )
                )
        return violations
