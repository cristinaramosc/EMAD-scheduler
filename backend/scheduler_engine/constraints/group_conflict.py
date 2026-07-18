from __future__ import annotations

import re

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict


def _quarter_suffix(text):
    """Retorna '1q' o '2q' si el text acaba amb aquest sufix (independent de
    majúscules/minúscules i espais), o None en cas contrari."""
    value = (text or "").strip().lower()
    if value.endswith("1q"):
        return "1q"
    if value.endswith("2q"):
        return "2q"
    return None


def _parent_and_quarter(group, subject):
    """Retorna (grup_pare, marcador_de_quadrimestre) per a una combinació de
    grup + assignatura. El marcador es dedueix primer del nom del grup
    (p.ex. '1A 1Q' -> pare '1A', marcador '1q'); si el grup no en té, es
    dedueix del nom de l'assignatura (p.ex. grup '1A', assignatura
    'Dibuix 1Q' -> pare '1A', marcador '1q')."""
    group_text = (group or "").strip()
    group_quarter = _quarter_suffix(group_text)
    if group_quarter is not None:
        parent = group_text[: -len(group_quarter)].strip()
        return parent, group_quarter

    return group_text, _quarter_suffix(subject)


def is_valid_quarter_pair(first_group, first_subject, second_group, second_subject):
    """Dues activitats del mateix grup pare només poden coexistir a la
    mateixa franja horària si una correspon al 1r quadrimestre i l'altra
    al 2n (marcat al nom del grup o, si no, al de l'assignatura)."""
    parent_a, quarter_a = _parent_and_quarter(first_group, first_subject)
    parent_b, quarter_b = _parent_and_quarter(second_group, second_subject)
    if parent_a != parent_b:
        return False
    return quarter_a is not None and quarter_b is not None and quarter_a != quarter_b


class GroupConflictConstraint(Constraint):
    """Detecta si un grup (o el seu grup pare) té més d'una activitat que se
    superposa en el temps.

    Excepció: dues activitats del mateix grup pare poden coincidir si una
    correspon al 1Q i l'altra al 2Q (al nom del grup o de l'assignatura).
    """

    def validate(self, schedule):
        conflicts = []
        occupied = {}

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
