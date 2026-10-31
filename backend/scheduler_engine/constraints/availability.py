"""Franges no disponibles de professors i grups.

Fins ara aquestes restriccions només es respectaven dins el col·locador: el
motor de validació no les coneixia, així que qualsevol pas posterior que
validés amb el motor (compactació, alineació 1Q/2Q, repartiment, moviments
manuals...) podia deixar una classe en una franja bloquejada sense cap avís.
Aquesta comprovació les fa complir a tot arreu.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
    from backend.scheduler_engine.quarter_utils import group_names
    from backend.scheduler_engine.subject_utils import FIXED_MEETING_BLOCKS, FIXED_MEETING_DAY, is_non_class_subject
    from backend.scheduler_engine.teacher_utils import teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict
    from scheduler_engine.quarter_utils import group_names
    from scheduler_engine.subject_utils import FIXED_MEETING_BLOCKS, FIXED_MEETING_DAY, is_non_class_subject
    from scheduler_engine.teacher_utils import teacher_names


def _index_blocked(blocked: Dict[Tuple[str, str], Set[Tuple[int, int]]]) -> Dict[str, Dict[str, Set[Tuple[int, int]]]]:
    indexed: Dict[str, Dict[str, Set[Tuple[int, int]]]] = {"teacher": {}, "group": {}}
    for (kind, name), slots in (blocked or {}).items():
        if kind in indexed and name:
            indexed[kind].setdefault(str(name).strip().casefold(), set()).update(slots)
    return indexed


class AvailabilityConstraint(Constraint):
    """Cap classe pot ocupar una franja no disponible del professor ni del grup."""

    def validate(self, schedule) -> List[Conflict]:
        configuration = getattr(schedule, "configuration", None) or {}
        blocked = configuration.get("blocked_slots") or {}
        day_names = configuration.get("day_names") or []
        hour_names = configuration.get("hour_names") or []
        if not blocked or not day_names or not hour_names:
            return []

        indexed = _index_blocked(blocked)
        day_index = {name: position for position, name in enumerate(day_names)}
        hour_index = {name: position for position, name in enumerate(hour_names)}
        conflicts: List[Conflict] = []

        for activity in schedule.all():
            # Les hores de centre, coordinacions, reunions i tutories no són classe
            # del grup: no ocupen la seva franja, però el professor sí que ha de
            # ser disponible quan les fa. Els descansos (sense professor) no compten.
            is_class = not is_non_class_subject(activity.subject)
            if activity.day not in day_index or activity.start not in hour_index:
                continue
            if (
                activity.day == FIXED_MEETING_DAY
                and any(
                    str(activity.subject or "").strip().casefold() == subject.casefold() and activity.start == start
                    for subject, start in FIXED_MEETING_BLOCKS
                )
            ):
                continue  # reunió/coordinació fixa: el seu bloc ja consta com a no disponible
            day = day_index[activity.day]
            first = hour_index[activity.start]
            length = max(int(activity.duration or 1), 1)
            # L'última etiqueta (21:30) només marca el final de la jornada, no és una franja:
            # una classe ha d'acabar-hi com a molt tard.
            if is_class and first + length > len(hour_names) - 1:
                conflicts.append(
                    Conflict(
                        type="outside_school_day",
                        message=(
                            f"{activity.subject} comença {activity.day} a les {activity.start} "
                            f"i acabaria després de les {hour_names[-1]}."
                        ),
                        day=activity.day,
                        start=activity.start,
                        activities=[activity.id],
                    )
                )
            covered = {(day, first + offset) for offset in range(length)}

            for teacher in teacher_names(activity.teacher):
                if covered & indexed["teacher"].get(str(teacher).strip().casefold(), set()):
                    conflicts.append(
                        Conflict(
                            type="teacher_unavailable",
                            message=(
                                f"El professor '{teacher}' no està disponible {activity.day} "
                                f"a les {activity.start} ({activity.subject})."
                            ),
                            teacher=str(teacher),
                            day=activity.day,
                            start=activity.start,
                            activities=[activity.id],
                        )
                    )
            for group in group_names(activity.group) if is_class else ():
                if covered & indexed["group"].get(group, set()):
                    conflicts.append(
                        Conflict(
                            type="group_unavailable",
                            message=(
                                f"El grup '{group}' no està disponible {activity.day} "
                                f"a les {activity.start} ({activity.subject})."
                            ),
                            day=activity.day,
                            start=activity.start,
                            activities=[activity.id],
                            data={"group": group},
                        )
                    )
        return conflicts
