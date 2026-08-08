from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

try:
    from backend.scheduler_engine.constraints.base import Constraint
    from backend.scheduler_engine.models import Conflict
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.constraints.base import Constraint
    from scheduler_engine.models import Conflict


def normalize_group_name(group_name: Optional[str]) -> Optional[str]:
    if not group_name:
        return None
    return str(group_name).strip().upper()


def get_group_time_window(
    group_name: Optional[str],
    constraints: Optional[Dict[str, Any]] = None,
    day: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """Retorna la finestra horària (start, end) permesa per a un grup.

    `constraints[group]` pot ser:
    - Una tupla/llista (start, end): s'aplica a tots els dies (format antic).
    - Un diccionari {"default": (start, end) | None, "by_day": {dia: (start, end)}}:
      si `day` té una entrada pròpia a "by_day", s'usa aquesta; si no,
      s'usa "default" (si n'hi ha).
    """
    normalized_group = normalize_group_name(group_name)
    if not normalized_group:
        return None

    if not constraints:
        return None

    entry = constraints.get(normalized_group)
    if entry is None:
        return None

    def _as_window(raw) -> Optional[Tuple[int, int]]:
        if isinstance(raw, (tuple, list)) and len(raw) == 2:
            start, end = raw
            return int(start), int(end)
        return None

    window = _as_window(entry)
    if window is not None:
        return window

    if isinstance(entry, dict):
        by_day = entry.get("by_day") or {}
        if day:
            day_window = _as_window(by_day.get(day))
            if day_window is not None:
                return day_window
        return _as_window(entry.get("default"))

    return None


class GroupTimeWindowConstraint(Constraint):
    """Ensure a group is only scheduled within its configured daily window."""

    def validate(self, schedule):
        constraints = getattr(schedule, "configuration", {}).get("group_time_window_constraints", {}) if hasattr(schedule, "configuration") else {}
        conflicts: list[Conflict] = []
        for activity in schedule.all():
            if bool(getattr(activity, "fixed", False)):
                continue
            if not activity.group or not activity.day or not activity.start:
                continue
            window = get_group_time_window(activity.group, constraints, day=activity.day)
            if window is None:
                continue

            required_slots = max(int(getattr(activity, "duration", 1) or 1), 1)
            start_slot = self._parse_slot_index(activity.start)
            for offset in range(required_slots):
                slot_index = start_slot + offset
                if slot_index < 0:
                    continue
                if not self._is_within_window(slot_index, window):
                    conflicts.append(
                        Conflict(
                            type="group_time_window",
                            message=(
                                f"El grup '{activity.group}' té classe fora de la seva franja horària permesa."
                            ),
                            day=activity.day,
                            start=activity.start,
                            activities=[activity.id],
                            data={"group": activity.group, "window": window},
                        )
                    )
                    break

        return conflicts

    def _parse_slot_index(self, value):
        text_value = str(value or "")
        match = re.match(r"\s*(\d+):(\d+)", text_value)
        if match is None:
            digits = re.search(r"(\d+)", text_value)
            return int(digits.group(1)) * 2 if digits else 0
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return (hours * 60 + minutes) // 30

    def _is_within_window(self, slot_index: int, window: Tuple[int, int]) -> bool:
        start, end = window
        if start > end:
            start, end = end, start
        return start <= slot_index <= end
