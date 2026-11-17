from __future__ import annotations

import re
from typing import Optional, Sequence, Tuple

from .shared_group_rules import is_shared_gi_gp_day_edge, is_shared_gi_gp_group


class SchedulePreferencePolicy:
    @staticmethod
    def ranking_key(
        *,
        hard_conflicts: int,
        unplaced_activities: int,
        unjoined_consecutive_pairs: int,
        shared_group_not_edge: int,
        preferred_day_misses: int,
        ignores_preferred_days: bool,
        quality_score: float,
    ) -> tuple:
        return (
            hard_conflicts,
            unplaced_activities,
            unjoined_consecutive_pairs,
            shared_group_not_edge,
            0 if ignores_preferred_days else preferred_day_misses,
            -quality_score,
        )

    @staticmethod
    def shared_group_day_edge_violations(
        activities: Sequence[Tuple[Optional[str], int, int, int]],
    ) -> int:
        return sum(
            1
            for group, day, period, duration in activities
            if is_shared_gi_gp_group(group)
            and not is_shared_gi_gp_day_edge(group, day, period, duration, activities)
        )

    @staticmethod
    def preferred_day_misses(
        preferences: Sequence[Tuple[int, Optional[str]]],
        day_names: Sequence[str],
    ) -> int:
        normalized_days = [str(name).strip().casefold() for name in day_names]
        misses = 0
        for day, preferred in preferences:
            if not preferred:
                continue

            wanted = {
                item.strip().casefold()
                for item in re.split(r"[,;/+]", str(preferred))
                if item.strip()
            }
            preferred_indexes = {
                index for index, name in enumerate(normalized_days) if name in wanted
            }
            if preferred_indexes and day not in preferred_indexes:
                misses += 1
        return misses
