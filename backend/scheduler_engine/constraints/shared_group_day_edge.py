from __future__ import annotations

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.shared_group_rules import (
        GroupDayInterval,
        is_shared_gi_gp_day_edge,
        is_shared_gi_gp_group,
    )
    from backend.scheduler_engine.subject_utils import is_non_class_subject, is_non_lective_tutoria
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.shared_group_rules import (
        GroupDayInterval,
        is_shared_gi_gp_day_edge,
        is_shared_gi_gp_group,
    )
    from scheduler_engine.subject_utils import is_non_class_subject, is_non_lective_tutoria


class SharedGroupDayEdgeConstraint(Constraint):
    """Keep every shared GI/GP assignment at the start or end of both group days."""

    def validate(self, schedule):
        intervals: list[GroupDayInterval] = []
        periods_by_id = {}
        for activity in schedule.all():
            if (
                not activity.group
                or not activity.day
                or not activity.start
                or is_non_class_subject(activity.subject)
                or is_non_lective_tutoria(activity.subject, activity.group)
            ):
                continue
            period = self._period_index(activity.start)
            if period is None:
                continue
            duration = max(int(activity.duration or 1), 1)
            intervals.append((activity.group, activity.day, period, duration))
            periods_by_id[activity.id] = period

        conflicts = []
        for activity in schedule.all():
            if not is_shared_gi_gp_group(activity.group):
                continue
            period = periods_by_id.get(activity.id)
            if period is None:
                continue
            if is_shared_gi_gp_day_edge(
                activity.group,
                activity.day,
                period,
                max(int(activity.duration or 1), 1),
                intervals,
            ):
                continue
            conflicts.append(
                Conflict(
                    type="shared_group_day_edge",
                    message=(
                        f"L'assignatura compartida '{activity.subject}' ha d'anar "
                        "a l'inici o al final de la jornada de GI i GP."
                    ),
                    day=activity.day,
                    start=activity.start,
                    activities=[activity.id],
                    data={"groups": ["GI", "GP"]},
                )
            )
        return conflicts

    @staticmethod
    def _period_index(start: str) -> int | None:
        try:
            hour, minute = (int(part) for part in start.split(":"))
        except (AttributeError, TypeError, ValueError):
            return None
        if minute not in {0, 30}:
            return None
        return hour * 2 + minute // 30
