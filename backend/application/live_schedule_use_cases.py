from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from backend.services.fet_importer import load_activities, load_scheduler_activities
    from backend.scheduler_engine.models.activity import Activity
    from backend.scheduler_engine.models.schedule import Schedule
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.time_units import blocks_to_hours
except ModuleNotFoundError:  # pragma: no cover
    from repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from services.fet_importer import load_activities, load_scheduler_activities
    from scheduler_engine.models.activity import Activity
    from scheduler_engine.models.schedule import Schedule
    from repositories.academic_data_repository import AcademicDataRepository
    from time_units import blocks_to_hours

from .serializers import serialize_activity, serialize_conflicts

try:
    from backend.services.fet_importer import load_restrictions
except ModuleNotFoundError:  # pragma: no cover
    from services.fet_importer import load_restrictions


class LiveScheduleUseCases:
    def __init__(
        self,
        engine: Any,
        load_activities_fn: Any,
        load_scheduler_activities_fn: Any,
        fet_file: Path,
        working_timetable_repo: WorkingTimetableRepository,
        academic_data_repo: Optional[AcademicDataRepository] = None,
    ) -> None:
        self._engine = engine
        self._load_activities_fn = load_activities_fn
        self._load_scheduler_activities_fn = load_scheduler_activities_fn
        self._fet_file = fet_file
        self._working_timetable_repo = working_timetable_repo
        self._academic_data_repo = academic_data_repo

    def load(self, activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        schedule = Schedule()
        for activity in activities:
            schedule.add(Activity(**activity))

        self._engine.load(schedule)
        self._persist_active_schedule(clear_proposal=True)
        return {"status": "ok", "loaded": len(schedule.all())}

    def _resolve_fet_source(self, source: Any) -> Any:
        if isinstance(source, (bytes, bytearray)):
            return BytesIO(source)
        return source

    def load_fet(self, fet_file: Any | None = None) -> Dict[str, Any]:
        source = self._fet_file if fet_file is None else fet_file

        schedule = Schedule()
        for activity in self._load_scheduler_activities_fn(self._resolve_fet_source(source)):
            schedule.add(Activity(**activity))

        self._engine.load(schedule)
        self._persist_active_schedule(clear_proposal=True)

        if self._academic_data_repo is not None:
            try:
                activities = self._load_activities_fn(self._resolve_fet_source(source))

                teachers = set()
                groups = set()
                subjects = set()
                rooms = set()
                assignment_map = {}
                for a in activities:
                    t = a.get("teacher") or ""
                    s = a.get("subject") or ""
                    g = a.get("group_name") or ""
                    r = a.get("room")
                    d = a.get("duration") or 0

                    if t:
                        teachers.add(t)
                    if g:
                        groups.add(g)
                    if s:
                        subjects.add(s)
                    if r:
                        rooms.add(r)

                    key = (t, s, g)
                    assignment_map.setdefault(key, 0)
                    try:
                        assignment_map[key] += float(d)
                    except Exception:
                        pass

                teaching_assignments = []
                for (t, s, g), total_duration_blocks in assignment_map.items():
                    if not (t and s and g):
                        continue
                    # `duration` from the FET file is expressed in half-hour
                    # blocks (see fet_importer.load_activities), not hours.
                    # It must be converted before being stored as weekly_hours,
                    # otherwise e.g. 4 blocks (2h real) get shown as "4.0h".
                    weekly_hours = blocks_to_hours(int(round(total_duration_blocks)))
                    teaching_assignments.append({
                        "teacher": t,
                        "subject": s,
                        "group": g,
                        "weekly_hours": weekly_hours,
                    })

                snapshot = {
                    "teachers": [{"name": name} for name in sorted(teachers)],
                    "groups": [{"name": name} for name in sorted(groups)],
                    "subjects": [{"name": name} for name in sorted(subjects)],
                    "rooms": [{"name": name} for name in sorted(rooms)],
                    "teaching_assignments": teaching_assignments,
                }

                restrictions = load_restrictions(self._resolve_fet_source(source))
                if restrictions.get("teacher_restrictions"):
                    snapshot["teacher_restrictions"] = restrictions["teacher_restrictions"]
                if restrictions.get("group_restrictions"):
                    snapshot["group_restrictions"] = restrictions["group_restrictions"]

                try:
                    self._academic_data_repo.apply_snapshot(snapshot)
                except Exception:
                    pass
            except Exception:
                pass

        return {
            "ok": True,
            "loaded": len(schedule.all()),
            **self.state(),
        }

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
                **self.state(conflicts=conflicts),
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
                **self.state(conflicts=conflicts),
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

    _BREAK_WINDOW_STARTS = ["9:30", "10:00", "10:30", "11:00", "11:30", "12:00"]

    def toggle_group_break(self, group: str, day: str) -> Dict[str, Any]:
        """Activa/desactiva un descans de mitja hora per a un grup en un dia
        concret. El descans sempre cau entre les 9:30 i les 12:30, triant
        automàticament la primera franja lliure d'aquesta finestra."""
        existing = next(
            (
                item
                for item in self._engine.state.all()
                if item.group == group
                and item.day == day
                and (item.subject or "").strip().lower() == "descans"
            ),
            None,
        )

        if existing is not None:
            self._engine.state.remove(existing)
            self._persist_active_schedule(clear_proposal=False)
            return {"ok": True, "active": False, **self.state()}

        occupied_starts = {
            item.start
            for item in self._engine.state.all()
            if item.group == group and item.day == day
        }
        chosen_start = next(
            (start for start in self._BREAK_WINDOW_STARTS if start not in occupied_starts),
            None,
        )
        if chosen_start is None:
            return {"ok": False, "error": "no_free_slot", "active": False, **self.state()}

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
