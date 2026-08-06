from __future__ import annotations

import re

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.teacher_utils import teacher_label, teacher_names
    from backend.scheduler_engine.quarter_utils import quarter_suffix
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.teacher_utils import teacher_label, teacher_names
    from scheduler_engine.quarter_utils import quarter_suffix


class TeacherConflictConstraint(Constraint):
    """Detecta si un professor té més d'una activitat al mateix temps."""

    def validate(self, schedule):
        conflicts = []
        occupied = {}

        for activity in schedule.all():
            activity_teachers = teacher_names(activity.teacher)
            if not activity_teachers or not activity.day or not activity.start:
                continue

            for slot in self._iter_slots(activity):
                conflict_found = None
                for teacher in activity_teachers:
                    key = (teacher, activity.day, slot)
                    previous = occupied.get(key)
                    if previous is None:
                        continue
                    if previous.id != activity.id:
                        # Excepció: un professor pot fer una activitat de 1Q
                        # i una altra de 2Q a la mateixa franja horària, ja
                        # que mai coincideixen en el temps real (són
                        # trimestres/quadrimestres diferents del mateix curs).
                        activity_quarter = quarter_suffix(getattr(activity, "subject", None)) or quarter_suffix(
                            getattr(activity, "group", None)
                        )
                        previous_quarter = quarter_suffix(getattr(previous, "subject", None)) or quarter_suffix(
                            getattr(previous, "group", None)
                        )
                        if (
                            activity_quarter is not None
                            and previous_quarter is not None
                            and activity_quarter != previous_quarter
                        ):
                            continue
                        conflict_found = previous
                        break

                if conflict_found is not None:
                    activities = [conflict_found.id, activity.id]
                    conflicts.append(
                        Conflict(
                            type="teacher_conflict",
                            message=(
                                f"El professor '{teacher_label(activity.teacher)}' té més d'una activitat "
                                f"{activity.day} a les {activity.start}."
                            ),
                            teacher=teacher_label(activity.teacher),
                            day=activity.day,
                            start=activity.start,
                            activities=activities,
                            data={
                                "teacher": teacher_label(activity.teacher),
                                "day": activity.day,
                                "start": activity.start,
                                "activities": activities,
                            },
                        )
                    )
                    continue

                for teacher in activity_teachers:
                    occupied[(teacher, activity.day, slot)] = activity

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
