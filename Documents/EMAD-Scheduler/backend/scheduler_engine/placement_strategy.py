from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

try:
    from models.teaching_block import TeachingBlock
except ModuleNotFoundError:  # pragma: no cover
    from backend.models.teaching_block import TeachingBlock
from .constraints.group_conflict import _parent_and_quarter, is_valid_quarter_pair
from .constraints.group_time_window import get_group_time_window
from .models import GenerationContext, ScheduledActivity, TimeSlot


class PlacementStrategy(ABC):
    """Decides where a TeachingBlock should be placed in a generation pass."""

    @abstractmethod
    def place(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
    ) -> Optional[ScheduledActivity]:
        """Return a scheduled activity or None when no placement is possible."""
        raise NotImplementedError


class GreedyPlacementStrategy(PlacementStrategy):
    """A deterministic first-valid-slot placement strategy."""

    def place(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
    ) -> Optional[ScheduledActivity]:
        required_slots = teaching_block.duration_blocks or 1
        existing_activities = list(context.existing_scheduled_activities) + list(context.fixed_activities)
        all_activities = list(existing_activities) + list(current_scheduled_activities)

        for day in context.school_calendar.days:
            for slot in context.school_calendar.periods_for_day(day):
                if self._is_blocked(slot, context.blocked_time_slots):
                    continue

                if not self._fits_in_day(slot, required_slots, context.school_calendar.periods_per_day):
                    continue

                if self._group_conflict_exists(teaching_block, slot, all_activities):
                    continue

                if self._teacher_conflict_exists(teaching_block, slot, all_activities):
                    continue

                if self._group_time_window_conflict_exists(teaching_block, slot, context):
                    continue

                if self._room_conflict_exists(teaching_block, slot, all_activities, context):
                    continue

                return ScheduledActivity(
                    teaching_block=teaching_block,
                    day=day,
                    start_timeslot=slot,
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

        return None

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
        teacher_id = teaching_block.preferred_teacher_id
        if not teacher_id:
            return False

        for activity in activities:
            if activity.day != start_slot.day:
                continue
            if activity.teacher_id != teacher_id:
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
    ) -> bool:
        group_id = None
        if teaching_block.metadata:
            group_id = teaching_block.metadata.get("group_id") or teaching_block.metadata.get("group")
        if not group_id:
            return False

        required_slots = teaching_block.duration_blocks or 1
        candidate_subject = (teaching_block.metadata or {}).get("subject")
        candidate_parent, _ = _parent_and_quarter(group_id, candidate_subject)

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
                # Exception: two activities of the same parent group are allowed
                # to overlap in the same slot when one subject/group ends in
                # "1Q" and the other in "2Q".
                same_exact_slot = (
                    start_slot.period == activity.start_timeslot.period
                    and required_slots == activity.duration
                )
                if same_exact_slot and is_valid_quarter_pair(
                    group_id, candidate_subject, activity.group_id, existing_subject
                ):
                    continue
                return True

        return False

    def _group_time_window_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        context: GenerationContext,
    ) -> bool:
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

