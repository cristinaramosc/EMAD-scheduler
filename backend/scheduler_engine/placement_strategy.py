from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

try:
    from models.teaching_block import TeachingBlock
except ModuleNotFoundError:  # pragma: no cover
    from backend.models.teaching_block import TeachingBlock
from .constraints.group_conflict import _parent_and_quarter, is_valid_quarter_pair, normalize_group_name
from .constraints.group_time_window import get_group_time_window
from .models import GenerationContext, ScheduledActivity, TimeSlot
from .teacher_utils import teacher_label, teacher_names


class PlacementStrategy(ABC):
    """Decides where a TeachingBlock should be placed in a generation pass."""

    def place(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
        excluded_days: Optional[set] = None,
    ) -> Optional[ScheduledActivity]:
        """Col·loca el bloc a la millor franja disponible, no simplement a la primera."""
        required_slots = teaching_block.duration_blocks or 1
        existing_activities = list(context.existing_scheduled_activities) + list(context.fixed_activities)
        all_activities = list(existing_activities) + list(current_scheduled_activities)

        candidates = []
        for day in context.school_calendar.days:
            if excluded_days and day in excluded_days:
                continue
            for slot in context.school_calendar.periods_for_day(day):
                if self._is_blocked(slot, context.blocked_time_slots):
                    continue
                if not self._fits_in_day(slot, required_slots, context.school_calendar.periods_per_day):
                    continue
                if self._group_conflict_exists(teaching_block, slot, all_activities, context):
                    continue
                if self._teacher_conflict_exists(teaching_block, slot, all_activities):
                    continue
                if self._group_time_window_conflict_exists(teaching_block, slot, context):
                    continue
                if self._room_conflict_exists(teaching_block, slot, all_activities, context):
                    continue
                candidates.append(slot)

        if not candidates:
            return None

        best_slot = min(candidates, key=lambda slot: self._placement_key(teaching_block, slot, all_activities, context))

        return ScheduledActivity(
            teaching_block=teaching_block,
            day=best_slot.day,
            start_timeslot=best_slot,
            duration=required_slots,
            room_id=teaching_block.preferred_room_id,
            teacher_id=teaching_block.preferred_teacher_id,
            group_id=(
                teaching_block.metadata.get("group_id")
                or teaching_block.metadata.get("group")
                if teaching_block.metadata
                else None
            ),
        )

    def _placement_key(
        self,
        teaching_block: TeachingBlock,
        slot: TimeSlot,
        activities: Sequence[ScheduledActivity],
        context: GenerationContext,
    ) -> tuple:
        """Clau lexicogràfica: primer grup, després professor."""
        required_slots = teaching_block.duration_blocks or 1
        group = self._group_of(teaching_block)

        group_activities = [a for a in activities if group and self._activity_group(a) == group]
        teacher_ids = set(teacher_names(teaching_block.preferred_teacher_id))
        teacher_activities = [
            a for a in activities
            if teacher_ids and not teacher_ids.isdisjoint(set(teacher_names(a.teacher_id)))
        ]

        candidate = ScheduledActivity(
            teaching_block=teaching_block,
            day=slot.day,
            start_timeslot=slot,
            duration=required_slots,
            room_id=teaching_block.preferred_room_id,
            teacher_id=teaching_block.preferred_teacher_id,
            group_id=group,
        )

        group_with_candidate = group_activities + [candidate]
        group_day_loads = self._day_loads(group_with_candidate)
        loads = list(group_day_loads.values())
        group_spread = max(loads) - min(loads) if len(loads) > 1 else 0

        group_gaps = self._gaps_for_entity(group_with_candidate)
        group_gap_count = sum(1 for gap in group_gaps if gap > 0)
        group_excess_gaps = sum(max(0, gap - 1) for gap in group_gaps)

        teacher_with_candidate = teacher_activities + [candidate]
        teacher_days = len({a.day for a in teacher_with_candidate})
        teacher_gaps = self._gaps_for_entity(teacher_with_candidate)
        real_teacher_gaps = 0
        for day, gap_start, gap_end in teacher_gaps:
            if self._is_midday_lunch_gap(gap_start, gap_end, context):
                continue
            real_teacher_gaps += 1

        # Primer: màxim una franja buida de 30 min al dia per grup.
        # Després: equilibri entre dies del grup.
        # Després: forats del professor (el dinar no compta) i dies del professor.
        return (
            group_excess_gaps * 100,
            max(0, group_gap_count - len(self._group_days(group_with_candidate))) * 100,
            group_spread,
            max(0, group_gap_count - 1) * 100,
            real_teacher_gaps,
            teacher_days,
            slot.period,
        )

    def _group_of(self, teaching_block: TeachingBlock) -> Optional[str]:
        metadata = teaching_block.metadata or {}
        return metadata.get("group_id") or metadata.get("group")

    def _activity_group(self, activity: ScheduledActivity) -> Optional[str]:
        metadata = activity.teaching_block.metadata or {}
        return activity.group_id or metadata.get("group_id") or metadata.get("group")

    def _group_days(self, activities: Sequence[ScheduledActivity]) -> set:
        return {a.day for a in activities}

    def _day_loads(self, activities: Sequence[ScheduledActivity]) -> dict:
        loads = {}
        for activity in activities:
            loads[activity.day] = loads.get(activity.day, 0) + (activity.duration or 1)
        return loads

    def _gaps_for_entity(self, activities: Sequence[ScheduledActivity]) -> List[Tuple[int, int, int]]:
        by_day = {}
        for activity in activities:
            by_day.setdefault(activity.day, []).append(activity)

        gaps = []
        for day, day_activities in by_day.items():
            ordered = sorted(day_activities, key=lambda a: a.start_timeslot.period)
            for previous, current in zip(ordered, ordered[1:]):
                start = previous.start_timeslot.period + previous.duration
                end = current.start_timeslot.period
                if end > start:
                    gaps.append((day, start, end))
        return gaps

    def _is_midday_lunch_gap(
        self,
        start_period: int,
        end_period: int,
        context: GenerationContext,
    ) -> bool:
        if end_period - start_period > 2:
            return False

        hour_names = context.configuration.get("hour_names") or []
        if not hour_names:
            middle = context.school_calendar.periods_per_day // 2
            return middle - 2 <= start_period <= middle + 2

        def minutes(period: int):
            if period >= len(hour_names):
                return None
            token = str(hour_names[period])
            if ":" not in token:
                return None
            try:
                hour, minute = token.split(":", 1)
                return int(hour) * 60 + int(minute)
            except ValueError:
                return None

        start = minutes(start_period)
        end = minutes(end_period)
        return start is not None and end is not None and 12 * 60 <= start and end <= 15 * 60 and end - start <= 60

    def _day_name(self, day: int) -> str:
        if 0 <= day < len(self._DAY_NAMES_CA):
            return self._DAY_NAMES_CA[day]
        return f"el dia {day}"

    def explain_failure(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
    ) -> List[str]:
        """Re-run the same slot scan as place(), but instead of stopping at
        the first valid slot, record every distinct constraint that rejected
        a candidate slot, so an incidence can explain all of its causes."""
        required_slots = teaching_block.duration_blocks or 1
        existing_activities = list(context.existing_scheduled_activities) + list(context.fixed_activities)
        all_activities = list(existing_activities) + list(current_scheduled_activities)

        metadata = teaching_block.metadata or {}
        teacher_name_label = metadata.get("teacher") or teacher_label(teaching_block.preferred_teacher_id) or "El professor"
        group_label = metadata.get("group") or metadata.get("group_id") or "El grup"
        room_label = teaching_block.preferred_room_id or metadata.get("room")

        reasons: List[str] = []
        seen: set = set()

        def add(reason: str) -> None:
            if reason not in seen:
                seen.add(reason)
                reasons.append(reason)

        any_calendar_slot = False

        for day in context.school_calendar.days:
            for slot in context.school_calendar.periods_for_day(day):
                if self._is_blocked(slot, context.blocked_time_slots):
                    continue

                if not self._fits_in_day(slot, required_slots, context.school_calendar.periods_per_day):
                    continue

                any_calendar_slot = True
                day_name = self._day_name(day)

                if self._group_conflict_exists(teaching_block, slot, all_activities, context):
                    add(f"El grup {group_label} ja té una altra activitat {day_name} en aquesta franja.")

                if self._teacher_conflict_exists(teaching_block, slot, all_activities):
                    add(f"El professor {teacher_name_label} no està disponible {day_name}.")

                if self._group_time_window_conflict_exists(teaching_block, slot, context):
                    add(f"El grup {group_label} supera la franja horària permesa {day_name}.")

                if room_label and self._room_conflict_exists(teaching_block, slot, all_activities, context):
                    add(f"L'aula {room_label} està ocupada {day_name} en aquesta franja.")

        if not reasons:
            if not any_calendar_slot:
                add("No hi ha cap franja horària amb prou durada disponible per a aquesta activitat.")
            else:
                add("No s'ha trobat cap franja vàlida per col·locar aquesta activitat.")

        return reasons

    def find_alternative_slots(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
        max_results: int = 3,
    ) -> List[dict]:
        """Return up to max_results slots where this block WOULD fit, given
        the current schedule. Reuses the exact same checks as place(), just
        collecting every valid slot instead of stopping at the first one."""
        required_slots = teaching_block.duration_blocks or 1
        existing_activities = list(context.existing_scheduled_activities) + list(context.fixed_activities)
        all_activities = list(existing_activities) + list(current_scheduled_activities)
        hour_names = context.configuration.get("hour_names") or []

        suggestions: List[dict] = []

        for day in context.school_calendar.days:
            for slot in context.school_calendar.periods_for_day(day):
                if len(suggestions) >= max_results:
                    return suggestions

                if self._is_blocked(slot, context.blocked_time_slots):
                    continue
                if not self._fits_in_day(slot, required_slots, context.school_calendar.periods_per_day):
                    continue
                if self._group_conflict_exists(teaching_block, slot, all_activities, context):
                    continue
                if self._teacher_conflict_exists(teaching_block, slot, all_activities):
                    continue
                if self._group_time_window_conflict_exists(teaching_block, slot, context):
                    continue
                if self._room_conflict_exists(teaching_block, slot, all_activities, context):
                    continue

                start_label = hour_names[slot.period] if slot.period < len(hour_names) else f"Període {slot.period}"
                suggestions.append({"day": self._day_name(day), "start": start_label})

        return suggestions

    def _is_blocked(self, slot: TimeSlot, blocked_time_slots: Sequence[Tuple[int, int]]) -> bool:
        return (slot.day, slot.period) in blocked_time_slots

    def _fits_in_day(self, slot: TimeSlot, required_slots: int, periods_per_day: int) -> bool:
        return slot.period + required_slots <= periods_per_day

    def _teacher_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        activities: Sequence[ScheduledActivity],
    ) -> bool:
        teacher_ids = teacher_names(teaching_block.preferred_teacher_id)
        if not teacher_ids:
            return False

        for activity in activities:
            if activity.day != start_slot.day:
                continue
            activity_teacher_ids = teacher_names(activity.teacher_id)
            if not activity_teacher_ids or set(activity_teacher_ids).isdisjoint(teacher_ids):
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + (teaching_block.duration_blocks or 1)
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                return True

        return False

    def _group_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        activities: Sequence[ScheduledActivity],
        context: Optional[GenerationContext] = None,
    ) -> bool:
        group_id = None
        if teaching_block.metadata:
            group_id = teaching_block.metadata.get("group_id") or teaching_block.metadata.get("group")
        if not group_id:
            return False

        required_slots = teaching_block.duration_blocks or 1
        candidate_subject = (teaching_block.metadata or {}).get("subject")
        candidate_parent, _ = _parent_and_quarter(group_id, candidate_subject)
        raw_split_groups = (context.configuration.get("split_groups") or set()) if context is not None else set()
        split_groups = {normalize_group_name(name) for name in raw_split_groups}
        group_is_split = candidate_parent in split_groups or normalize_group_name(group_id) in split_groups

        for activity in activities:
            if activity.day != start_slot.day:
                continue
            existing_subject = (activity.metadata or {}).get("subject")
            activity_parent, _ = _parent_and_quarter(activity.group_id, existing_subject)
            if activity_parent != candidate_parent:
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + required_slots
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                # Exception 1: two activities of the same parent group are
                # allowed to overlap in the same slot when one subject/group
                # ends in "1Q" and the other in "2Q".
                same_exact_slot = (
                    start_slot.period == activity.start_timeslot.period
                    and required_slots == activity.duration
                )
                if same_exact_slot and is_valid_quarter_pair(
                    group_id, candidate_subject, activity.group_id, existing_subject
                ):
                    continue

                # Exception 2: a group marked as "desdoblat" (split) can have
                # two simultaneous activities as long as the teacher and the
                # room are both different (each subgroup goes its own way).
                if group_is_split:
                    candidate_teacher_ids = teacher_names(teaching_block.preferred_teacher_id)
                    candidate_room = teaching_block.preferred_room_id
                    activity_teacher_ids = teacher_names(activity.teacher_id)
                    different_teacher = bool(candidate_teacher_ids) and bool(activity_teacher_ids) and set(candidate_teacher_ids).isdisjoint(activity_teacher_ids)
                    different_room = candidate_room and activity.room_id and candidate_room != activity.room_id
                    if different_teacher and different_room:
                        continue
                return True

        return False

    def _group_time_window_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        context: GenerationContext,
    ) -> bool:
        if teaching_block.fixed and teaching_block.fixed_day and teaching_block.fixed_start:
            return False

        group_id = None
        if teaching_block.metadata:
            group_id = teaching_block.metadata.get("group_id") or teaching_block.metadata.get("group")
        if not group_id:
            return False

        window = get_group_time_window(group_id, context.configuration.get("group_time_window_constraints"))
        if window is None:
            return False

        required_slots = teaching_block.duration_blocks or 1
        if self._uses_period_index_window(window, context.school_calendar.periods_per_day):
            for offset in range(required_slots):
                slot_period = start_slot.period + offset
                if slot_period >= context.school_calendar.periods_per_day:
                    return True
                if not self._is_within_window(slot_period, window):
                    return True
            return False

        hour_names = context.configuration.get("hour_names") or []
        period_length = context.school_calendar.period_length_minutes
        for offset in range(required_slots):
            slot_period = start_slot.period + offset
            if slot_period >= context.school_calendar.periods_per_day:
                return True

            slot_time = None
            if hour_names:
                if slot_period < len(hour_names):
                    slot_time = hour_names[slot_period]
            if slot_time is None:
                slot_time = (slot_period * period_length) + context.school_calendar.period_length_minutes

            slot_minutes = self._parse_minutes(slot_time)
            if slot_minutes is None:
                continue
            if not self._is_within_window(slot_minutes, window):
                return True

        return False

    def _uses_period_index_window(self, window: Tuple[int, int], periods_per_day: int) -> bool:
        start, end = window
        return all(isinstance(value, int) and 0 <= value < periods_per_day for value in (start, end))

    def _parse_minutes(self, value) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            token = value.strip()
            if not token:
                return None
            if re.fullmatch(r"\d+", token):
                return int(token)
            if ":" in token:
                hour_text, minute_text = token.split(":", 1)
                try:
                    hour = int(hour_text)
                    minute = int(minute_text)
                except ValueError:
                    return None
                return hour * 60 + minute
        return None

    def _is_within_window(self, slot_minutes: int, window: Tuple[int, int]) -> bool:
        start_minutes, end_minutes = window
        if start_minutes > end_minutes:
            start_minutes, end_minutes = end_minutes, start_minutes
        return start_minutes <= slot_minutes <= end_minutes

    def _room_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        activities: Sequence[ScheduledActivity],
        context: GenerationContext,
    ) -> bool:
        if not context.configuration.get("room_constraints_enabled", False):
            return False

        room_id = teaching_block.preferred_room_id
        if not room_id:
            return False

        required_slots = teaching_block.duration_blocks or 1
        for activity in activities:
            if activity.day != start_slot.day:
                continue
            if activity.room_id != room_id:
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + required_slots
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                return True

        return False



class GreedyPlacementStrategy(PlacementStrategy):
    """Compatibility name used by the scheduler generator.

    The scheduler now uses the full candidate-scoring logic implemented in
    PlacementStrategy.place(), so this class intentionally inherits it
    instead of reverting to the old first-valid-slot behaviour.
    """

    _DAY_NAMES_CA = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]
