from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

try:
    from models.teaching_block import TeachingBlock
except ModuleNotFoundError:  # pragma: no cover
    from backend.models.teaching_block import TeachingBlock
from .constraints.group_time_window import get_group_time_window
from .constraints.group_max_days import get_group_max_days
from .models import GenerationContext, ScheduledActivity, TimeSlot
from .quarter_utils import is_valid_quarter_pair, normalize_group_name, parent_and_quarter as _parent_and_quarter, quarter_suffix
from .teacher_utils import teacher_label, teacher_names


class PlacementStrategy(ABC):
    """Decides where a TeachingBlock should be placed in a generation pass."""

    @abstractmethod
    def place(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
        excluded_days: Optional[set] = None,
    ) -> Optional[ScheduledActivity]:
        """Return a scheduled activity or None when no placement is possible.

        `excluded_days` lists day indices to skip entirely — used to force
        the blocks of a single requirement onto distinct days when it has
        been split to satisfy a "days to spread across" restriction."""
        raise NotImplementedError

    def explain_failure(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
    ) -> List[str]:
        """Return every distinct reason placement failed, in Catalan.

        Optional to override. Strategies that don't implement this simply
        provide no explanation, keeping the base contract backward compatible.
        """
        return []


class GreedyPlacementStrategy(PlacementStrategy):
    """A deterministic first-valid-slot placement strategy."""

    _DAY_NAMES_CA = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]

    def place(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        current_scheduled_activities: Sequence[ScheduledActivity],
        excluded_days: Optional[set] = None,
    ) -> Optional[ScheduledActivity]:
        required_slots = teaching_block.duration_blocks or 1
        existing_activities = list(context.existing_scheduled_activities) + list(context.fixed_activities)
        all_activities = list(existing_activities) + list(current_scheduled_activities)

        preferred = self._try_quarter_pair_slot(
            teaching_block, context, all_activities, required_slots, excluded_days
        )
        if preferred is not None:
            return preferred

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

                if self._group_max_days_conflict_exists(teaching_block, slot, all_activities, context):
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

    def _try_quarter_pair_slot(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        all_activities: Sequence[ScheduledActivity],
        required_slots: int,
        excluded_days: Optional[set],
    ) -> Optional[ScheduledActivity]:
        """Per defecte, compacta les parelles 1Q/2Q: si el grup pare d'aquest
        bloc ja té col·locada una activitat de l'altre quadrimestre, intenta
        primer aquella mateixa franja (dia + hora d'inici) abans de fer la
        cerca general. Si hi ha diverses franges candidates (perquè el grup
        pare ja té diverses activitats de l'altre quadrimestre en dies
        diferents), es prioritza la que coincideixi de professor amb la
        parella ja col·locada."""
        metadata = teaching_block.metadata or {}
        group_id = metadata.get("group_id") or metadata.get("group")
        candidate_subject = metadata.get("subject")
        if not group_id:
            return None

        candidate_parent, candidate_quarter = _parent_and_quarter(group_id, candidate_subject)
        if candidate_quarter is None:
            return None

        candidate_teacher_ids = set(teacher_names(teaching_block.preferred_teacher_id))

        candidates = []
        seen_slots = set()
        for activity in all_activities:
            existing_subject = (activity.teaching_block.metadata or {}).get("subject")
            activity_parent, activity_quarter = _parent_and_quarter(activity.group_id, existing_subject)
            if activity_parent != candidate_parent or activity_quarter is None:
                continue
            if activity_quarter == candidate_quarter:
                continue

            slot_key = (activity.day, activity.start_timeslot.period)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)

            activity_teacher_ids = set(teacher_names(activity.teacher_id))
            teacher_matches = bool(candidate_teacher_ids) and not candidate_teacher_ids.isdisjoint(activity_teacher_ids)
            priority = 0 if teacher_matches else 1
            candidates.append((priority, activity.day, activity.start_timeslot.period, activity.start_timeslot))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))

        for _, day, _period, slot in candidates:
            if excluded_days and day in excluded_days:
                continue
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
            if self._group_max_days_conflict_exists(teaching_block, slot, all_activities, context):
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
                group_id=group_id,
            )

        return None

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

                if self._group_max_days_conflict_exists(teaching_block, slot, all_activities, context):
                    add(f"El grup {group_label} ja ha exhaurit el màxim de dies de classe permesos.")

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
                if self._group_max_days_conflict_exists(teaching_block, slot, all_activities, context):
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

        required_slots = teaching_block.duration_blocks or 1
        metadata = teaching_block.metadata or {}
        candidate_group = metadata.get("group_id") or metadata.get("group")
        candidate_subject = metadata.get("subject")
        candidate_quarter = quarter_suffix(candidate_subject) or quarter_suffix(candidate_group)

        for activity in activities:
            if activity.day != start_slot.day:
                continue
            activity_teacher_ids = teacher_names(activity.teacher_id)
            if not activity_teacher_ids or set(activity_teacher_ids).isdisjoint(teacher_ids):
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + required_slots
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                # Excepció: un professor pot fer una activitat de 1Q i una
                # altra de 2Q solapant-se en horari setmanal (sigui quina
                # sigui la durada exacta de cadascuna, p.ex. una assignatura
                # de 2h partida en dos blocs d'1h enfront d'una parella de 2h
                # en un sol bloc), ja que mai coincideixen en el temps real
                # (són trimestres/quadrimestres diferents dins el mateix
                # curs).
                if candidate_quarter is not None:
                    existing_subject = (activity.teaching_block.metadata or {}).get("subject")
                    existing_quarter = quarter_suffix(existing_subject) or quarter_suffix(activity.group_id)
                    if existing_quarter is not None and existing_quarter != candidate_quarter:
                        continue
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
            existing_subject = (activity.teaching_block.metadata or {}).get("subject")
            activity_parent, _ = _parent_and_quarter(activity.group_id, existing_subject)
            if activity_parent != candidate_parent:
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + required_slots
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                # Exception 1: two activities of the same parent group are
                # allowed to overlap when one subject/group is 1Q and the
                # other 2Q, sigui quina sigui la seva durada exacta (p.ex.
                # una assignatura de 2h partida en dos blocs d'1h enfront
                # d'una parella de 2h en un sol bloc): mai coincideixen en
                # el temps real, són trimestres/quadrimestres diferents.
                if is_valid_quarter_pair(
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

    def _group_max_days_conflict_exists(
        self,
        teaching_block: TeachingBlock,
        start_slot: TimeSlot,
        activities: Sequence[ScheduledActivity],
        context: GenerationContext,
    ) -> bool:
        if teaching_block.fixed and teaching_block.fixed_day and teaching_block.fixed_start:
            return False

        group_id = None
        if teaching_block.metadata:
            group_id = teaching_block.metadata.get("group_id") or teaching_block.metadata.get("group")
        if not group_id:
            return False

        max_days = get_group_max_days(group_id, context.configuration.get("group_max_days_constraints"))
        if max_days is None:
            return False

        candidate_subject = (teaching_block.metadata or {}).get("subject")
        candidate_parent, _ = _parent_and_quarter(group_id, candidate_subject)

        used_days = set()
        for activity in activities:
            existing_subject = (activity.teaching_block.metadata or {}).get("subject")
            activity_parent, _ = _parent_and_quarter(activity.group_id, existing_subject)
            if activity_parent != candidate_parent:
                continue
            used_days.add(activity.day)

        if start_slot.day in used_days:
            return False

        return len(used_days) >= max_days

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

        window = get_group_time_window(
            group_id, context.configuration.get("group_time_window_constraints"), day=start_slot.day
        )
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
        metadata = teaching_block.metadata or {}
        candidate_group = metadata.get("group_id") or metadata.get("group")
        candidate_subject = metadata.get("subject")
        candidate_quarter = quarter_suffix(candidate_subject) or quarter_suffix(candidate_group)

        for activity in activities:
            if activity.day != start_slot.day:
                continue
            if activity.room_id != room_id:
                continue
            activity_end = activity.start_timeslot.period + activity.duration
            candidate_end = start_slot.period + required_slots
            if start_slot.period < activity_end and candidate_end > activity.start_timeslot.period:
                # Excepció: dues activitats poden compartir aula i franja si
                # una és 1Q i l'altra 2Q, ja que mai coincideixen en el temps
                # real (són trimestres/quadrimestres diferents).
                if candidate_quarter is not None:
                    existing_subject = (activity.teaching_block.metadata or {}).get("subject")
                    existing_quarter = quarter_suffix(existing_subject) or quarter_suffix(activity.group_id)
                    if existing_quarter is not None and existing_quarter != candidate_quarter:
                        continue
                return True

        return False

