from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.teacher_utils import teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.teacher_utils import teacher_names


def get_teacher_max_days(
    teacher_name: Optional[str], constraints: Optional[Dict[str, Any]] = None
) -> Optional[int]:
    if not teacher_name or not constraints:
        return None

    raw_value = constraints.get(str(teacher_name).strip().casefold())
    if raw_value is None:
        return None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


class TeacherMaxDaysConstraint(Constraint):
    """Ensure each teacher is scheduled on no more than the configured days."""

    def validate(self, schedule):
        constraints = (
            getattr(schedule, "configuration", {}).get("teacher_max_days_constraints", {})
            if hasattr(schedule, "configuration")
            else {}
        )
        day_order = (
            getattr(schedule, "configuration", {}).get("day_names", [])
            if hasattr(schedule, "configuration")
            else []
        )
        conflicts: list[Conflict] = []
        if not constraints:
            return conflicts

        activities_by_teacher: Dict[str, List[Any]] = {}
        for activity in schedule.all():
            if not activity.teacher or not activity.day:
                continue
            for teacher_name in teacher_names(activity.teacher):
                activities_by_teacher.setdefault(teacher_name.casefold(), []).append(activity)

        for teacher_name, activities in activities_by_teacher.items():
            max_days = get_teacher_max_days(teacher_name, constraints)
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
                        type="teacher_max_days",
                        message=(
                            f"El professor '{activity.teacher}' té classe en més de {max_days} dies."
                        ),
                        teacher=activity.teacher,
                        day=activity.day,
                        start=activity.start,
                        activities=[activity.id],
                        data={"teacher": activity.teacher, "max_days": max_days},
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