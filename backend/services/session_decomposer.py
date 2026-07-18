from __future__ import annotations

from typing import List, Optional, Tuple


class SessionDecompositionError(Exception):
    pass


class SessionDecomposer:
    """Decomposes a weekly teaching load into session lengths.

    Rules:
    - use only allowed session lengths
    - minimize number of sessions
    - prefer balanced sessions
    - sum must equal weekly load
    """

    def __init__(self, granularity_factor: int = 2) -> None:
        # granularity_factor: multiply floats so that 0.5 -> int (factor=2)
        self._factor = granularity_factor

    def decompose(self, weekly_hours: float, allowed_lengths: List[float]) -> List[float]:
        if weekly_hours is None:
            raise SessionDecompositionError("weekly_hours_required")
        if not allowed_lengths:
            raise SessionDecompositionError("no_allowed_session_lengths")

        # transform to integer units
        target = int(round(weekly_hours * self._factor))
        coins = sorted({int(round(x * self._factor)) for x in allowed_lengths if x > 0})
        if not coins or target <= 0:
            raise SessionDecompositionError("invalid_parameters")

        # DP to find minimal number of sessions to reach target (unbounded coin change)
        INF = 10 ** 9
        dp = [INF] * (target + 1)
        dp[0] = 0
        for t in range(1, target + 1):
            for c in coins:
                if c <= t and dp[t - c] + 1 < dp[t]:
                    dp[t] = dp[t - c] + 1

        if dp[target] >= INF:
            raise SessionDecompositionError("no_valid_decomposition")

        min_sessions = dp[target]

        # find one decomposition with exactly min_sessions that is as balanced as possible
        # generate combinations (non-decreasing) of length min_sessions from coins that sum to target
        solutions: List[List[int]] = []

        coins_sorted = sorted(coins)

        def search(start_idx: int, slots_left: int, sum_left: int, path: List[int]):
            if slots_left == 0:
                if sum_left == 0:
                    solutions.append(list(path))
                return
            if sum_left < coins_sorted[start_idx] * slots_left:
                return
            max_possible = coins_sorted[-1] * slots_left
            if sum_left > max_possible:
                return

            for idx in range(start_idx, len(coins_sorted)):
                c = coins_sorted[idx]
                if c > sum_left:
                    break
                # choose c
                path.append(c)
                search(idx, slots_left - 1, sum_left - c, path)
                path.pop()

        # find minimal start index such that coins_sorted[start_idx]*min_sessions <= target
        start_idx = 0
        while start_idx < len(coins_sorted) and coins_sorted[start_idx] * min_sessions > target:
            start_idx += 1
        if start_idx >= len(coins_sorted):
            raise SessionDecompositionError("no_valid_decomposition")

        search(start_idx, min_sessions, target, [])

        if not solutions:
            # Shouldn't happen because DP said possible, but guard
            raise SessionDecompositionError("no_valid_decomposition")

        # evaluate balance: choose solution with minimal (max-min), then minimal variance
        def score(sol: List[int]) -> Tuple[int, float]:
            mx = max(sol)
            mn = min(sol)
            vals = [v / self._factor for v in sol]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            return (mx - mn, var)

        best = min(solutions, key=score)

        return [v / self._factor for v in best]

    def decompose_by_max_sessions(
        self,
        weekly_hours: float,
        max_sessions: int,
        min_session_length: float = 1.0,
    ) -> List[float]:
        """Reparteix la càrrega setmanal en com a màxim `max_sessions` sessions,
        tan equilibrades com sigui possible, sense que cap sessió baixi de
        `min_session_length` (per defecte, 1 hora)."""
        if weekly_hours is None or weekly_hours <= 0:
            raise SessionDecompositionError("weekly_hours_required")

        max_sessions = max(1, int(max_sessions or 1))

        best_n = 1
        for n in range(1, max_sessions + 1):
            if weekly_hours / n >= min_session_length - 1e-9:
                best_n = n
            else:
                break

        units_total = int(round(weekly_hours * self._factor))
        base = units_total // best_n
        remainder = units_total % best_n
        sessions_units = [base + (1 if i < remainder else 0) for i in range(best_n)]

        min_units = int(round(min_session_length * self._factor))
        if any(units < min_units for units in sessions_units):
            raise SessionDecompositionError("cannot_meet_minimum_session_length")

        sessions_units.sort(reverse=True)
        return [units / self._factor for units in sessions_units]
