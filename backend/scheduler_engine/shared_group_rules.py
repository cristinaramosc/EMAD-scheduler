from __future__ import annotations

from typing import Iterable, Optional, TypeAlias

from .quarter_utils import group_names

GroupDayInterval: TypeAlias = tuple[Optional[str], int | str, int, int]


def is_shared_gi_gp_group(group_id: Optional[str]) -> bool:
    return set(group_names(group_id)) == {"gi", "gp"}


def is_shared_gi_gp_day_edge(
    group_id: Optional[str],
    day: int | str,
    start: int,
    duration: int,
    activities: Iterable[GroupDayInterval],
) -> bool:
    """Return whether a shared GI/GP activity is an edge for both groups."""
    groups = set(group_names(group_id))
    if groups != {"gi", "gp"}:
        return False

    intervals = tuple(activities)
    end = start + duration
    for group in groups:
        group_intervals = [
            (activity_start, activity_start + activity_duration)
            for activity_group, activity_day, activity_start, activity_duration in intervals
            if activity_day == day and group in group_names(activity_group)
        ]
        if not group_intervals:
            return False
        if start != min(interval[0] for interval in group_intervals) and end != max(
            interval[1] for interval in group_intervals
        ):
            return False
    return True
