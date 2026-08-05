from __future__ import annotations

import re

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.quarter_utils import (
        is_valid_quarter_pair,
        normalize_group_name,
        parent_and_quarter as _parent_and_quarter,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.quarter_utils import (
        is_valid_quarter_pair,
        normalize_group_name,
        parent_and_quarter as _parent_and_quarter,
    )

# Nota: `normalize_group_name`, `_parent_and_quarter` (alias de
# `parent_and_quarter`) i `is_valid_quarter_pair` vivien abans com a còpies
# locals en aquest mòdul. Ara la implementació única viu a
# `backend/scheduler_engine/quarter_utils.py`; aquest fitxer només
# re-exporta/usa aquell mòdul perquè la resta del codi no ha de canviar el
# seu comportament.


class GroupConflictConstraint(Constraint):
    """Detecta si un grup (o el seu grup pare) té més d'una activitat que se
    superposa en el temps.

    Excepció: dues activitats del mateix grup pare poden coincidir si una
    correspon al 1Q i l'altra al 2Q (al nom del grup o de l'assignatura).
    """

    def validate(self, schedule):
        conflicts = []
        occupied = {}
        raw_split_groups = getattr(schedule, "configuration", {}).get("split_groups", set()) if hasattr(schedule, "configuration") else set()
        split_groups = {normalize_group_name(name) for name in raw_split_groups}

        for activity in schedule.all():
            if not activity.group or not activity.day or not activity.start:
                continue

            parent_group, _ = _parent_and_quarter(activity.group, activity.subject)

            for slot in self._iter_slots(activity):
                key = (parent_group, activity.day, slot)
                bucket = occupied.setdefault(key, [])

                if not bucket:
                    bucket.append(activity)
                    continue

                if len(bucket) == 1 and is_valid_quarter_pair(
                    bucket[0].group, bucket[0].subject, activity.group, activity.subject
                ):
                    bucket.append(activity)
                    continue

                previous = bucket[-1]

                # Excepció: si el grup està marcat com a desdoblat, dues
                # activitats simultànies són vàlides quan tenen professor i
                # aula diferents (cada subgrup va per lliure).
                group_is_split = parent_group in split_groups or normalize_group_name(activity.group) in split_groups
                if group_is_split:
                    different_teacher = (
                        previous.teacher and activity.teacher and previous.teacher != activity.teacher
                    )
                    different_room = previous.room and activity.room and previous.room != activity.room
                    if different_teacher and different_room:
                        bucket.append(activity)
                        continue

                activities = [previous.id, activity.id]
                conflicts.append(
                    Conflict(
                        type="group_conflict",
                        message=(
                            f"El grup '{activity.group}' té més d'una activitat "
                            f"{activity.day} a les {activity.start}."
                        ),
                        day=activity.day,
                        start=activity.start,
                        activities=activities,
                        data={"group": activity.group},
                    )
                )
                bucket.append(activity)

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
