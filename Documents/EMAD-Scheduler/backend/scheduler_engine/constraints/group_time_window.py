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


def get_group_time_window(group_name: Optional[str], constraints: Optional[Dict[str, Any]] = None) -> Optional[Tuple[int, int]]:
    normalized_group = normalize_group_name(group_name)
    if not normalized_group:
        return None

    if not constraints:
        return None

    raw_window = constraints.get(normalized_group)
    if raw_window is None:
        return None

    if isinstance(raw_window, tuple) and len(raw_window) == 2:
        start, end = raw_window
        return int(start), int(end)

    if isinstance(raw_window, list) and len(raw_window) == 2:
        start, end = raw_window
        return int(start), int(end)

    return None


class GroupTimeWindowConstraint(Constraint):
    """Ensure a group is only scheduled within its configured daily window."""

    def validate(self, schedule):
        constraints = getattr(schedule, "configuration", {}).get("group_time_window_constraints", {}) if hasattr(schedule, "configuration") else {}
        conflicts: list[Conflict] = []
        for activity in schedule.all():
            if not activity.group or not activity.day or not activity.start:
                continue
            window = get_group_time_window(activity.group, constraints)
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
