from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from backend.scheduler_engine.models.activity import Activity
    from backend.scheduler_engine.models.schedule import Schedule
    from backend.repositories.academic_data_repository import AcademicDataRepository
except ModuleNotFoundError:  # pragma: no cover
    from repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from scheduler_engine.models.activity import Activity
    from scheduler_engine.models.schedule import Schedule
    from repositories.academic_data_repository import AcademicDataRepository

from .serializers import serialize_activity, serialize_conflicts


class LiveScheduleUseCases:
    def __init__(
        self,
        engine: Any,
        working_timetable_repo: WorkingTimetableRepository,
        academic_data_repo: Optional[AcademicDataRepository] = None,
    ) -> None:
        self._engine = engine
        self._working_timetable_repo = working_timetable_repo
        self._academic_data_repo = academic_data_repo

    def load(self, activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        schedule = Schedule()
        for activity in activities:
            schedule.add(Activity(**activity))

        self._engine.load(schedule)
        self._persist_active_schedule(clear_proposal=True)
        return {"status": "ok", "loaded": len(schedule.all())}

    def state(self, conflicts: List[Any] | None = None) -> Dict[str, Any]:
        if conflicts is not None:
            return {
                "activities": [
                    serialize_activity(activity)
                    for activity in self._engine.state.all()
                ],
                "conflicts": serialize_conflicts(conflicts),
                "proposal": None,
                "generation_stats": None,
                "unscheduled_activities": [],
            }

        snapshot = self._working_timetable_repo.load_snapshot()
        if snapshot.current_proposal is not None:
            proposal_payload = dict(snapshot.current_proposal)
            return {
                "activities": proposal_payload.get("activities", []),
                "conflicts": proposal_payload.get("conflicts", []),
                "proposal": proposal_payload,
                "generation_stats": snapshot.generation_stats,
                "unscheduled_activities": snapshot.unscheduled_activities,
            }

        active_conflicts = self._engine.validate()
        return {
            "activities": [
                serialize_activity(activity)
                for activity in self._engine.state.all()
            ],
            "conflicts": serialize_conflicts(active_conflicts),
            "proposal": None,
            "generation_stats": None,
            "unscheduled_activities": [],
        }

    def teacher_schedule(self, teacher_name: str) -> Dict[str, Any]:
        current_state = self.state()
        activities = [
            activity
            for activity in current_state.get("activities", [])
            if activity.get("teacher") == teacher_name
        ]
        return {
            "teacher": teacher_name,
            "activities": activities,
        }

    @staticmethod
    def _conflict_key(conflict: Any) -> tuple:
        return (
            conflict.type,
            conflict.day,
            conflict.start,
            conflict.teacher,
            conflict.room,
            frozenset(conflict.activities or []),
        )

    def move(self, activity_id: int, day: str, start: str) -> Dict[str, Any]:
        activity = next((item for item in self._engine.state.all() if item.id == activity_id), None)
        if activity is None:
            return {
                "ok": False,
                "error": "activity_not_found",
                **self.state(),
            }

        baseline_conflicts = self._engine.validate()
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        previous_day = activity.day
        previous_start = activity.start
        activity.day = day
        activity.start = start

        conflicts = self._engine.validate()
        new_conflicts = [
            conflict for conflict in conflicts if self._conflict_key(conflict) not in baseline_keys
        ]

        if new_conflicts:
            activity.day = previous_day
            activity.start = previous_start
            return {
                "ok": False,
                "error": "validation_failed",
                "conflicts": serialize_conflicts(new_conflicts),
                **self.state(conflicts=baseline_conflicts),
            }

        self._persist_active_schedule(clear_proposal=False)
        return {
            "ok": True,
            **self.state(),
        }

    def add_manual_activity(
        self,
        subject: str,
        day: str,
        start: str,
        duration: int = 1,
        teacher: str = "",
        group: str = "",
        room: str = "",
    ) -> Dict[str, Any]:
        """Afegeix una activitat manual a l'horari actiu (p.ex. un descans
        d'estudiants o una hora de coordinació d'un professor) sense passar
        pel generador. Es valida que no introdueixi cap conflicte nou."""
        existing_ids = [item.id for item in self._engine.state.all()]
        new_id = (max(existing_ids) + 1) if existing_ids else 1

        new_activity = Activity(
            id=new_id,
            teacher=teacher,
            subject=subject,
            group=group,
            room=room,
            day=day,
            start=start,
            duration=duration,
        )

        baseline_conflicts = self._engine.validate()
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        self._engine.state.add(new_activity)

        conflicts = self._engine.validate()
        new_conflicts = [
            conflict for conflict in conflicts if self._conflict_key(conflict) not in baseline_keys
        ]

        if new_conflicts:
            self._engine.state.remove(new_activity)
            return {
                "ok": False,
                "error": "validation_failed",
                "conflicts": serialize_conflicts(new_conflicts),
                **self.state(conflicts=baseline_conflicts),
            }

        self._persist_active_schedule(clear_proposal=False)
        return {
            "ok": True,
            "activity": serialize_activity(new_activity),
            **self.state(),
        }

    def remove_activity(self, activity_id: int) -> Dict[str, Any]:
        activity = next((item for item in self._engine.state.all() if item.id == activity_id), None)
        if activity is None:
            return {
                "ok": False,
                "error": "activity_not_found",
                **self.state(),
            }

        self._engine.state.remove(activity)
        self._persist_active_schedule(clear_proposal=False)
        return {
            "ok": True,
            **self.state(),
        }

    _MORNING_BREAK_GROUPS = {"1r apgi", "2n apgi", "pfi", "1r com", "2n com"}
    _AFTERNOON_BREAK_GROUPS = {"comú", "gp", "gi"}

    @staticmethod
    def _norm_name(value: str) -> str:
        return (value or "").strip().lower()

    def toggle_group_break(self, group: str, day: str) -> Dict[str, Any]:
        """Activa/desactiva un descans de 30 min per a un grup en un dia
        concret. Si cal, desplaça 30 min més tard totes les classes
        d'aquell grup a partir del punt d'inserció per obrir un forat
        lliure de veritat (no es limita a buscar-ne un que ja existeixi).
        El punt d'inserció és com a mínim 1h després de l'inici de la
        primera classe del dia i com a màxim 1h30 abans del final de
        l'última, i a més es limita al matí o la tarda segons el grup
        (1r/2n APGI, PFI, 1r/2n COM -> matí; Comú, GP, GI -> tarda).
        En desactivar-lo, torna a ajuntar l'horari desplaçant cap enrere
        les classes que hi havia després."""
        hour_names, hour_index = self._half_hour_grid()
        target_group = self._norm_name(group)

        existing = next(
            (
                item
                for item in self._engine.state.all()
                if self._norm_name(item.group) == target_group
                and item.day == day
                and (item.subject or "").strip().lower() == "descans"
            ),
            None,
        )

        if existing is not None:
            removed_idx = hour_index.get(existing.start, None)
            self._engine.state.remove(existing)
            if removed_idx is not None:
                later_items = sorted(
                    (
                        item
                        for item in self._engine.state.all()
                        if self._norm_name(item.group) == target_group and item.day == day
                        and hour_index.get(item.start, -1) > removed_idx
                    ),
                    key=lambda item: hour_index.get(item.start, -1),
                )
                for item in later_items:
                    idx = hour_index.get(item.start, -1)
                    if idx <= 0:
                        continue
                    result = self.move(item.id, day, hour_names[idx - 1])
                    if not result.get("ok"):
                        break  # es queda on és si no es pot desplaçar (p.ex. xoca amb el professor en un altre grup)
            self._persist_active_schedule(clear_proposal=False)
            return {"ok": True, "active": False, **self.state()}

        day_activities = [
            item for item in self._engine.state.all()
            if self._norm_name(item.group) == target_group and item.day == day
            and (item.subject or "").strip().lower() != "descans"
        ]
        if not day_activities:
            known_groups = sorted({item.group for item in self._engine.state.all() if item.day == day and item.group})
            return {
                "ok": False,
                "error": "no_free_slot",
                "detail": f"cap classe aquell dia per aquest grup (grups amb classe {day}: {known_groups})",
                "active": False,
                **self.state(),
            }

        exceptions = set()
        if self._academic_data_repo is not None:
            restriction = next(
                (
                    r for r in self._academic_data_repo.list_group_restrictions()
                    if self._norm_name(r.get("group")) == target_group
                ),
                None,
            )
            if restriction:
                exceptions = set(restriction.get("exception_slots") or [])

        span_activities = [item for item in day_activities if f"{item.day} {item.start}" not in exceptions] or day_activities

        start_indices = [hour_index.get(item.start, -1) for item in span_activities]
        end_indices = [hour_index.get(item.start, -1) + item.duration for item in span_activities]
        if -1 in start_indices:
            bad_starts = [item.start for item in span_activities if hour_index.get(item.start, -1) == -1]
            return {"ok": False, "error": "no_free_slot", "detail": f"hora no reconeguda: {bad_starts}", "active": False, **self.state()}

        day_start_idx = min(start_indices)
        day_end_idx = max(end_indices)

        window_start_idx = day_start_idx + 2  # 1h després de començar
        window_end_idx = day_end_idx - 3  # 1h30 abans d'acabar

        midday_idx = hour_index.get("14:00")
        if midday_idx is not None:
            if target_group in self._MORNING_BREAK_GROUPS:
                window_end_idx = min(window_end_idx, midday_idx - 1)
            elif target_group in self._AFTERNOON_BREAK_GROUPS:
                window_start_idx = max(window_start_idx, midday_idx)

        if window_start_idx > window_end_idx or window_start_idx >= len(hour_names):
            return {
                "ok": False,
                "error": "no_free_slot",
                "detail": f"classes de {hour_names[day_start_idx]} a {hour_names[day_end_idx - 1] if day_end_idx - 1 < len(hour_names) else '?'} "
                          f"({(day_end_idx - day_start_idx) * 0.5}h seguides, calen minim 3h per deixar els dos marges "
                          f"dins del mati o la tarda segons el grup)",
                "active": False,
                **self.state(),
            }

        insertion_idx = window_start_idx
        chosen_start = hour_names[insertion_idx]

        # Desplaça 30 min més tard totes les activitats d'aquest grup/dia
        # que comencin al punt d'inserció o després, començant per la
        # darrera perquè no xoquin entre elles durant el desplaçament.
        to_shift = sorted(
            (item for item in day_activities if hour_index.get(item.start, -1) >= insertion_idx),
            key=lambda item: hour_index.get(item.start, -1),
            reverse=True,
        )
        for item in to_shift:
            idx = hour_index.get(item.start, -1)
            new_idx = idx + 1
            if new_idx + item.duration > len(hour_names):
                return {"ok": False, "error": "no_free_slot", "active": False, **self.state()}
            result = self.move(item.id, day, hour_names[new_idx])
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error", "validation_failed"), "active": False, **self.state()}

        result = self.add_manual_activity(
            subject="Descans",
            day=day,
            start=chosen_start,
            duration=1,
            group=group,
        )
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "validation_failed"), "active": False, **self.state()}

        return {"ok": True, "active": True, **self.state()}

    _LUNCH_WINDOW_STARTS = ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00"]
    _LUNCH_MORNING_BEFORE = "12:00"
    _LUNCH_AFTERNOON_FROM = "16:00"

    def assign_teacher_lunch_breaks(self) -> Dict[str, Any]:
        """Afegeix una hora de dinar (entre les 12h i les 16h) a cada
        professor que tingui classe abans de les 12h i també a partir de
        les 16h el mateix dia, si encara no en té cap assignada."""
        hour_names = []
        hour = 8 * 60
        while hour <= 21 * 60:
            hour_names.append(f"{hour // 60}:{hour % 60:02d}")
            hour += 30
        hour_index = {name: index for index, name in enumerate(hour_names)}
        morning_limit = hour_index.get(self._LUNCH_MORNING_BEFORE)
        afternoon_start = hour_index.get(self._LUNCH_AFTERNOON_FROM)
        if morning_limit is None or afternoon_start is None:
            return {"ok": False, "error": "invalid_time_window", **self.state()}

        activities = list(self._engine.state.all())
        by_teacher_day: Dict[tuple, List[Activity]] = {}
        for activity in activities:
            if not activity.teacher or not activity.day or activity.start not in hour_index:
                continue
            by_teacher_day.setdefault((activity.teacher, activity.day), []).append(activity)

        added = []
        skipped_no_slot = []
        for (teacher, day), day_activities in by_teacher_day.items():
            has_morning = any(hour_index[a.start] < morning_limit for a in day_activities)
            has_afternoon = any(hour_index[a.start] >= afternoon_start for a in day_activities)
            already_has_lunch = any((a.subject or "").strip().lower() == "dinar" for a in day_activities)
            if not (has_morning and has_afternoon) or already_has_lunch:
                continue

            occupied_starts = {a.start for a in day_activities}
            chosen_start = None
            for start in self._LUNCH_WINDOW_STARTS:
                start_idx = hour_index[start]
                second_half = hour_names[start_idx + 1] if start_idx + 1 < len(hour_names) else None
                if start in occupied_starts:
                    continue
                if second_half and second_half in occupied_starts:
                    continue
                chosen_start = start
                break

            if chosen_start is None:
                skipped_no_slot.append({"teacher": teacher, "day": day})
                continue

            result = self.add_manual_activity(
                subject="Dinar",
                day=day,
                start=chosen_start,
                duration=2,
                teacher=teacher,
            )
            if result.get("ok"):
                added.append({"teacher": teacher, "day": day, "start": chosen_start})

        return {
            "ok": True,
            "added": added,
            "skipped_no_slot": skipped_no_slot,
            **self.state(),
        }

    # ---------------------------------------------------------------
    # Reunió/Coordinació fixes (dimecres) + repartiment automàtic de les
    # hores de centre i coordinació restants de cada professor.
    # ---------------------------------------------------------------

    _DAY_ORDER = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    _FIXED_MEETING_DAY = "Dimecres"
    _FIXED_MEETING_BLOCKS = [("Reunió", "14:00"), ("Coordinació", "15:00")]  # 1h cadascun
    _MAX_DAILY_BLOCKS = 24  # 12h * 2 blocs de 30 min

    @staticmethod
    def _half_hour_grid() -> tuple[List[str], Dict[str, int]]:
        hour_names = []
        hour = 8 * 60
        while hour <= 21 * 60:
            hour_names.append(f"{hour // 60}:{hour % 60:02d}")
            hour += 30
        return hour_names, {name: index for index, name in enumerate(hour_names)}

    @staticmethod
    def _to_hours(value: Any) -> float:
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _place_extra_hours_for_teacher(
        self,
        teacher: str,
        subject: str,
        blocks_needed: int,
        hour_names: List[str],
        hour_index: Dict[str, int],
    ) -> tuple:
        """Col·loca `blocks_needed` blocs de 30 min per a `teacher` com a
        `subject`, enganxats abans o després de les classes que ja tingui
        cada dia, sense superar les 12h/dia (_MAX_DAILY_BLOCKS) si és
        evitable. Si no hi caben enlloc, els assigna igualment al final
        del darrer dia amb classes i ho marca com a conflicte."""
        added: List[Dict[str, Any]] = []
        exceeded: List[Dict[str, Any]] = []

        teacher_days = [
            day for day in self._DAY_ORDER
            if any(a.teacher == teacher and a.day == day for a in self._engine.state.all())
        ]

        for day in teacher_days:
            if blocks_needed <= 0:
                break

            day_activities = sorted(
                (a for a in self._engine.state.all() if a.teacher == teacher and a.day == day),
                key=lambda a: hour_index.get(a.start, -1),
            )
            if not day_activities:
                continue

            used_blocks = sum(a.duration for a in day_activities)
            free_blocks = self._MAX_DAILY_BLOCKS - used_blocks
            if free_blocks <= 0:
                continue
            chunk = min(blocks_needed, free_blocks)

            placed = False
            last = day_activities[-1]
            last_end_idx = hour_index.get(last.start, -1) + last.duration
            if 0 <= last_end_idx and last_end_idx + chunk <= len(hour_names):
                start_name = hour_names[last_end_idx]
                result = self.add_manual_activity(subject=subject, day=day, start=start_name, duration=chunk, teacher=teacher)
                if result.get("ok"):
                    added.append({"teacher": teacher, "day": day, "start": start_name, "duration": chunk, "subject": subject})
                    blocks_needed -= chunk
                    placed = True

            if not placed:
                first = day_activities[0]
                first_start_idx = hour_index.get(first.start, -1)
                place_blocks = min(chunk, first_start_idx) if first_start_idx > 0 else 0
                if place_blocks > 0:
                    start_idx = first_start_idx - place_blocks
                    start_name = hour_names[start_idx]
                    result = self.add_manual_activity(subject=subject, day=day, start=start_name, duration=place_blocks, teacher=teacher)
                    if result.get("ok"):
                        added.append({"teacher": teacher, "day": day, "start": start_name, "duration": place_blocks, "subject": subject})
                        blocks_needed -= place_blocks

        if blocks_needed > 0 and teacher_days:
            day = teacher_days[-1]
            day_activities = sorted(
                (a for a in self._engine.state.all() if a.teacher == teacher and a.day == day),
                key=lambda a: hour_index.get(a.start, -1),
            )
            if day_activities:
                last = day_activities[-1]
                last_end_idx = hour_index.get(last.start, -1) + last.duration
                if 0 <= last_end_idx < len(hour_names):
                    place_blocks = min(blocks_needed, len(hour_names) - last_end_idx)
                    if place_blocks > 0:
                        start_name = hour_names[last_end_idx]
                        result = self.add_manual_activity(subject=subject, day=day, start=start_name, duration=place_blocks, teacher=teacher)
                        if result.get("ok"):
                            added.append({"teacher": teacher, "day": day, "start": start_name, "duration": place_blocks, "subject": subject})
                            blocks_needed -= place_blocks
                            exceeded.append({"teacher": teacher, "day": day, "subject": subject, "extra_blocks": place_blocks})

        return blocks_needed, added, exceeded

    def assign_center_and_coordination_hours(self) -> Dict[str, Any]:
        """Per a cada professor: si té el bloc fix de dimecres (Reunió
        14-15h + Coordinació 15-16h) activat, l'assigna i en resta 1h de
        les hores de centre i 1h de les de coordinació. Reparteix la resta
        de les hores de centre/coordinació enganxades a les classes que ja
        tingui, sense superar les 12h/dia si és evitable; si no hi caben
        enlloc, les assigna igualment i ho marca com a conflicte."""
        if self._academic_data_repo is None:
            return {"ok": False, "error": "academic_data_repo_unavailable", **self.state()}

        hour_names, hour_index = self._half_hour_grid()
        restrictions = {r.get("teacher"): r for r in self._academic_data_repo.list_teacher_restrictions()}

        added_meetings: List[Dict[str, Any]] = []
        added_hours: List[Dict[str, Any]] = []
        daily_hours_exceeded: List[Dict[str, Any]] = []
        skipped_no_slot: List[Dict[str, Any]] = []

        for teacher in self._academic_data_repo.list_teachers():
            name = teacher.get("name")
            if not name:
                continue

            restriction = restrictions.get(name, {})
            weekly_meeting_active = restriction.get("weekly_meeting_active", True)
            weekly_coordination_active = restriction.get("weekly_coordination_active", True)
            block_active = {"Reunió": weekly_meeting_active, "Coordinació": weekly_coordination_active}

            remaining_center = self._to_hours(teacher.get("center_hours"))
            remaining_coordination = self._to_hours(teacher.get("coordination_hours"))

            existing_day_activities = [
                a for a in self._engine.state.all()
                if a.teacher == name and a.day == self._FIXED_MEETING_DAY
            ]
            for subject, start in self._FIXED_MEETING_BLOCKS:
                if not block_active[subject]:
                    continue
                already_present = any(
                    (a.subject or "").strip().lower() == subject.lower() and a.start == start
                    for a in existing_day_activities
                )
                if not already_present:
                    result = self.add_manual_activity(
                        subject=subject, day=self._FIXED_MEETING_DAY, start=start, duration=2, teacher=name,
                    )
                    if result.get("ok"):
                        added_meetings.append({"teacher": name, "subject": subject})
                    else:
                        skipped_no_slot.append({"teacher": name, "subject": subject, "reason": "conflict"})
                        continue
                if subject == "Reunió":
                    remaining_center = max(0.0, remaining_center - 1.0)
                else:
                    remaining_coordination = max(0.0, remaining_coordination - 1.0)

            for subject, remaining in (("Hores de centre", remaining_center), ("Coordinació", remaining_coordination)):
                blocks_needed = round(remaining * 2)
                if blocks_needed <= 0:
                    continue
                pending, added, exceeded = self._place_extra_hours_for_teacher(
                    teacher=name, subject=subject, blocks_needed=blocks_needed,
                    hour_names=hour_names, hour_index=hour_index,
                )
                added_hours.extend(added)
                daily_hours_exceeded.extend(exceeded)
                if pending > 0:
                    skipped_no_slot.append({"teacher": name, "subject": subject, "reason": "no_existing_day", "pending_blocks": pending})

        return {
            "ok": True,
            "added_meetings": added_meetings,
            "added_hours": added_hours,
            "daily_hours_exceeded": daily_hours_exceeded,
            "skipped_no_slot": skipped_no_slot,
            **self.state(),
        }


    def _persist_active_schedule(self, clear_proposal: bool) -> None:
        previous = self._working_timetable_repo.load_snapshot()
        self._working_timetable_repo.save_snapshot(
            WorkingTimetableSnapshot(
                active_schedule=[serialize_activity(activity) for activity in self._engine.state.all()],
                current_proposal=None if clear_proposal else previous.current_proposal,
                generation_stats=None if clear_proposal else previous.generation_stats,
                unscheduled_activities=[] if clear_proposal else previous.unscheduled_activities,
                metadata={**previous.metadata, "last_source": "active_schedule"},
            )
        )
