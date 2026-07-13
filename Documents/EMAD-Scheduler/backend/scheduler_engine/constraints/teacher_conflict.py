from __future__ import annotations

import re

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict


class TeacherConflictConstraint(Constraint):
    """Detecta si un professor té més d'una activitat al mateix temps."""

    def validate(self, schedule):
        conflicts = []
        occupied = {}

        for activity in schedule.all():
            if not activity.teacher or not activity.day or not activity.start:
                continue

            for slot in self._iter_slots(activity):
                key = (activity.teacher, activity.day, slot)
                previous = occupied.get(key)
                if previous is None:
                    occupied[key] = activity
                    continue

                activities = [previous.id, activity.id]
                conflicts.append(
                    Conflict(
                        type="teacher_conflict",
                        message=(
                            f"El professor '{activity.teacher}' té més d'una activitat "
                            f"{activity.day} a les {activity.start}."
                        ),
                        teacher=activity.teacher,
                        day=activity.day,
                        start=activity.start,
                        activities=activities,
                        data={
                            "teacher": activity.teacher,
                            "day": activity.day,
                            "start": activity.start,
                            "activities": activities,
                        },
                    )
                )

        return conflicts

    def _iter_slots(self, activity):
        duration = max(int(getattr(activity, "duration", 1) or 1), 1)
        start_slot = self._parse_slot_index(activity.start)
        for offset in range(duration):
            yield start_slot + offset

    def _parse_slot_index(self, value):
        text_value = str(value or "")
        match = re.match(r"\s*(\d+):(\d+)", text_value)
        if match is None:
            digits = re.search(r"(\d+)", text_value)
            return int(digits.group(1)) * 2 if digits else 0
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return (hours * 60 + minutes) // 30
