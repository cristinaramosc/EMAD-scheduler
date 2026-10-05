from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .constraint_evaluator import ConstraintEvaluator
from .models import ConstraintReport, GenerationContext, ScheduleProposal, ScoreBreakdown

try:
    from backend.scheduler_engine.quarter_utils import is_valid_quarter_pair, parent_and_quarter
    from backend.scheduler_engine.teacher_utils import teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.quarter_utils import is_valid_quarter_pair, parent_and_quarter
    from scheduler_engine.teacher_utils import teacher_names


class ProposalScorer:
    """Scorer jeràrquic per compactar grups i professorat."""

    _PLACED_WEIGHT = 100000.0
    _ASSIGNED_ROOM_TEACHER_WEIGHT = 5000.0
    _GROUP_BALANCE_WEIGHT = 500.0
    _GROUP_GAP_WEIGHT = 350.0
    _TEACHER_GAP_WEIGHT = 80.0
    _TEACHER_DAY_WEIGHT = 30.0
    _QUARTER_PAIR_TEACHER_MATCH_WEIGHT = 1000.0

    def __init__(self, constraint_evaluator: ConstraintEvaluator | None = None) -> None:
        self._constraint_evaluator = constraint_evaluator or ConstraintEvaluator()

    def calculate(self, proposal: ScheduleProposal, context: GenerationContext) -> ScoreBreakdown:
        report = self._constraint_evaluator.evaluate(proposal, context)
        placed = len(proposal.activities)
        warnings = len(proposal.warnings)

        assigned_room_teacher = sum(
            1 for activity in proposal.activities
            if activity.teacher and activity.room
        )

        group_balance = self._group_balance_penalty(proposal)
        group_gaps = self._group_gap_penalty(proposal)
        teacher_gaps = self._teacher_gap_penalty(proposal, context)
        teacher_days = self._teacher_day_penalty(proposal)
        quarter_score = self._quarter_pair_teacher_priority_score(proposal)

        distribution_score = max(
            0.0,
            100.0
            - group_balance * self._GROUP_BALANCE_WEIGHT
            - group_gaps * self._GROUP_GAP_WEIGHT,
        )

        total_score = (
            placed * self._PLACED_WEIGHT
            + assigned_room_teacher * self._ASSIGNED_ROOM_TEACHER_WEIGHT
            + distribution_score
            + quarter_score
            - teacher_gaps * self._TEACHER_GAP_WEIGHT
            - teacher_days * self._TEACHER_DAY_WEIGHT
            - warnings * 10000.0
            - len(report.soft_violations) * 25.0
        )

        metadata = {
            "activity_count": placed,
            "warning_count": warnings,
            "assigned_room_teacher_count": assigned_room_teacher,
            "group_balance_penalty": round(group_balance, 3),
            "group_gap_penalty": round(group_gaps, 3),
            "teacher_gap_penalty": round(teacher_gaps, 3),
            "teacher_day_penalty": round(teacher_days, 3),
            "quarter_pair_teacher_score": round(quarter_score, 3),
            "teacher_gap_rule": "fins a 1h de migdia no compta com a forat",
            "group_gap_rule": "1 únic bloc de 30 min per dia i grup és admissible",
        }

        return ScoreBreakdown(
            total_score=round(total_score, 3),
            compactness_score=round(placed, 3),
            distribution_score=round(distribution_score, 3),
            gap_penalty=round(group_gaps * self._GROUP_GAP_WEIGHT + teacher_gaps * self._TEACHER_GAP_WEIGHT, 3),
            warning_penalty=round(warnings * 10000.0 + teacher_days * self._TEACHER_DAY_WEIGHT, 3),
            metadata=metadata,
        )

    def _group_balance_penalty(self, proposal: ScheduleProposal) -> float:
        by_group: Dict[str, Dict[str, int]] = {}
        for activity in proposal.activities:
            if not activity.group:
                continue
            by_group.setdefault(activity.group, {})
            by_group[activity.group][activity.day] = (
                by_group[activity.group].get(activity.day, 0) + (activity.duration or 1)
            )

        penalty = 0.0
        for loads_by_day in by_group.values():
            loads = [load for load in loads_by_day.values() if load > 0]
            if len(loads) > 1:
                spread = max(loads) - min(loads)
                penalty += float(spread * spread)
        return penalty

    def _group_gap_penalty(self, proposal: ScheduleProposal) -> float:
        by_group_day: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
        for activity in proposal.activities:
            if not activity.group:
                continue
            start = self._period(activity.start)
            by_group_day.setdefault((activity.group, activity.day), []).append(
                (start, start + (activity.duration or 1))
            )

        penalty = 0.0
        for intervals in by_group_day.values():
            gaps = self._gaps(intervals)
            # El calendari treballa en blocs de 30 minuts:
            # un únic buit d'1 bloc (30 min) és admissible.
            # Un buit de 2 blocs (1 h) ja és penalitzat.
            if len(gaps) > 1:
                penalty += (len(gaps) - 1) * 2
            for start, end in gaps:
                gap_blocks = end - start
                if gap_blocks > 1:
                    penalty += (gap_blocks - 1) * 2
        return penalty

    def _teacher_gap_penalty(self, proposal: ScheduleProposal, context: GenerationContext) -> float:
        by_teacher_day: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
        for activity in proposal.activities:
            for teacher in teacher_names(activity.teacher):
                start = self._period(activity.start)
                by_teacher_day.setdefault((teacher, activity.day), []).append(
                    (start, start + (activity.duration or 1))
                )

        penalty = 0.0
        for intervals in by_teacher_day.values():
            gaps = self._gaps(intervals)
            lunch_used = False
            for start, end in gaps:
                if not lunch_used and self._is_lunch_gap(start, end, context):
                    lunch_used = True
                    continue
                penalty += 1.0 + max(0, end - start - 1) * 0.5
        return penalty

    def _teacher_day_penalty(self, proposal: ScheduleProposal) -> float:
        by_teacher: Dict[str, set] = {}
        for activity in proposal.activities:
            for teacher in teacher_names(activity.teacher):
                by_teacher.setdefault(teacher, set()).add(activity.day)
        return float(sum(max(0, len(days) - 1) for days in by_teacher.values()))

    def _gaps(self, intervals: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
        ordered = sorted(intervals)
        return [
            (previous_end, current_start)
            for (_, previous_end), (current_start, _) in zip(ordered, ordered[1:])
            if current_start > previous_end
        ]

    def _period(self, start: str) -> int:
        try:
            return int(str(start).split()[-1])
        except (ValueError, IndexError):
            return 0

    def _is_lunch_gap(self, start_period: int, end_period: int, context: GenerationContext) -> bool:
        if end_period - start_period > 2:
            return False
        hour_names = context.configuration.get("hour_names") or []
        if not hour_names:
            middle = context.school_calendar.periods_per_day // 2
            return middle - 2 <= start_period <= middle + 2

        def minutes(period: int):
            if period >= len(hour_names):
                return None
            token = str(hour_names[period])
            if ":" not in token:
                return None
            try:
                hour, minute = token.split(":", 1)
                return int(hour) * 60 + int(minute)
            except ValueError:
                return None

        start = minutes(start_period)
        end = minutes(end_period)
        return (
            start is not None and end is not None
            and 12 * 60 <= start <= 14 * 60
            and end <= 15 * 60
            and end - start <= 60
        )

    def _quarter_pair_teacher_priority_score(self, proposal: ScheduleProposal) -> float:
        if len(proposal.activities) < 2:
            return 0.0
        slot_buckets: Dict[tuple, list] = {}
        for activity in proposal.activities:
            if not activity.group or not activity.day or not activity.start:
                continue
            parent, quarter = parent_and_quarter(activity.group, activity.subject)
            if quarter is None:
                continue
            slot_buckets.setdefault((parent, activity.day, activity.start), []).append(activity)

        score = 0.0
        for bucket in slot_buckets.values():
            if len(bucket) != 2:
                continue
            first, second = bucket
            if not is_valid_quarter_pair(first.group, first.subject, second.group, second.subject):
                continue
            first_teachers = set(teacher_names(first.teacher))
            second_teachers = set(teacher_names(second.teacher))
            if first_teachers and second_teachers and not first_teachers.isdisjoint(second_teachers):
                score += self._QUARTER_PAIR_TEACHER_MATCH_WEIGHT
        return score
