from __future__ import annotations

import re

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.quarter_utils import (
        group_names,
        is_valid_quarter_pair,
        normalize_group_name,
        parent_and_quarter as _parent_and_quarter,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.quarter_utils import (
        group_names,
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

    Els grups es comparen individualment (una activitat de 'GI, GP' compta
    per a GI i per a GP per separat), perquè dues activitats que comparteixin
    NOMÉS un dels grups (p.ex. 'GI' sola i 'GI, GP' combinada) també han de
    detectar-se com a possible conflicte (o excepció 1Q/2Q) per a GI.
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
            individual_names = group_names(parent_group) or (parent_group,)

            for slot in self._iter_slots(activity):
                conflict_found = None

                for name in individual_names:
                    key = (name, activity.day, slot)
                    bucket = occupied.get(key)
                    if not bucket:
                        continue

                    for previous in bucket:
                        if previous.id == activity.id:
                            continue

                        if is_valid_quarter_pair(
                            previous.group, previous.subject, activity.group, activity.subject
                        ):
                            continue

                        # Excepció: si el grup està marcat com a desdoblat, dues
                        # activitats simultànies són vàlides quan tenen
                        # professor i aula diferents (cada subgrup va per
                        # lliure).
                        group_is_split = name in split_groups
                        if group_is_split:
                            different_teacher = (
                                previous.teacher and activity.teacher and previous.teacher != activity.teacher
                            )
                            different_room = previous.room and activity.room and previous.room != activity.room
                            if different_teacher and different_room:
                                continue

                        conflict_found = previous
                        break

                    if conflict_found is not None:
                        break

                if conflict_found is not None:
                    conflicts.append(
                        Conflict(
                            type="group_conflict",
                            message=(
                                f"El grup '{activity.group}' té més d'una activitat "
                                f"{activity.day} a les {activity.start}."
                            ),
                            day=activity.day,
                            start=activity.start,
                            activities=[conflict_found.id, activity.id],
                            data={"group": activity.group},
                        )
                    )

                for name in individual_names:
                    key = (name, activity.day, slot)
                    occupied.setdefault(key, []).append(activity)

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
