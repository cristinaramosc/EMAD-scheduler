from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.constraints.group_conflict import _parent_and_quarter
    from backend.scheduler_engine.models import Conflict
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.constraints.group_conflict import _parent_and_quarter
    from scheduler_engine.models import Conflict


def _normalize_constraint_key(group_name: Optional[str]) -> Optional[str]:
    if not group_name:
        return None
    return str(group_name).strip().upper()


def get_group_max_days(group_name: Optional[str], constraints: Optional[Dict[str, Any]] = None) -> Optional[int]:
    normalized_group = _normalize_constraint_key(group_name)
    if not normalized_group or not constraints:
        return None

    raw_value = constraints.get(normalized_group)
    if raw_value is None:
        return None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


class GroupMaxDaysConstraint(Constraint):
    """Ensure a group (its parent group) isn't scheduled on more distinct
    days per week than configured."""

    def validate(self, schedule):
        constraints = getattr(schedule, "configuration", {}).get("group_max_days_constraints", {}) if hasattr(schedule, "configuration") else {}
        day_order = getattr(schedule, "configuration", {}).get("day_names", []) if hasattr(schedule, "configuration") else []
        conflicts: list[Conflict] = []
        if not constraints:
            return conflicts

        activities_by_parent: Dict[str, List[Any]] = {}
        for activity in schedule.all():
            if not activity.group or not activity.day:
                continue
            parent_group, _ = _parent_and_quarter(activity.group, getattr(activity, "subject", None))
            activities_by_parent.setdefault(parent_group, []).append(activity)

        for parent_group, activities in activities_by_parent.items():
            sample_group_name = activities[0].group
            max_days = get_group_max_days(sample_group_name, constraints)
            if max_days is None:
                continue

            days_used = self._ordered_distinct_days(activities, day_order)
            if len(days_used) <= max_days:
                continue

            allowed_days = set(days_used[:max_days])
            for activity in activities:
                if activity.day in allowed_days:
                    continue
                conflicts.append(
                    Conflict(
                        type="group_max_days",
                        message=(
                            f"El grup '{activity.group}' té classe en més de {max_days} dies."
                        ),
                        day=activity.day,
                        start=activity.start,
                        activities=[activity.id],
                        data={"group": activity.group, "max_days": max_days},
                    )
                )

        return conflicts

    def _ordered_distinct_days(self, activities: List[Any], day_order: List[str]) -> List[str]:
        distinct_days = []
        for day in day_order:
            if day in distinct_days:
                continue
            if any(activity.day == day for activity in activities):
                distinct_days.append(day)

        for activity in activities:
            if activity.day not in distinct_days:
                distinct_days.append(activity.day)

        return distinct_days
