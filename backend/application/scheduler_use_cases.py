from __future__ import annotations

import zlib
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.scheduler_engine.quarter_utils import is_valid_quarter_pair, parent_and_quarter as _parent_and_quarter
    from backend.scheduler_engine.teacher_utils import teacher_label, teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.quarter_utils import is_valid_quarter_pair, parent_and_quarter as _parent_and_quarter
    from scheduler_engine.teacher_utils import teacher_label, teacher_names

try:
    from models.teaching_block import TeachingBlock
    from models.teaching_requirement import TeachingRequirement
    from repositories.academic_data_repository import AcademicDataRepository
    from repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.generator import SchedulerGenerator
    from scheduler_engine.models import Activity, GenerationContext, Schedule, ScheduledActivity, SchoolCalendar, ScheduleProposal, TimeSlot
except ModuleNotFoundError:  # pragma: no cover
    from backend.models.teaching_block import TeachingBlock
    from backend.models.teaching_requirement import TeachingRequirement
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
    from backend.scheduler_engine.engine import SchedulerEngine
    from backend.scheduler_engine.generator import SchedulerGenerator
    from backend.scheduler_engine.models import (
        Activity,
        GenerationContext,
        Schedule,
        ScheduledActivity,
        SchoolCalendar,
        ScheduleProposal,
        TimeSlot,
    )

from .serializers import serialize_activity, serialize_conflict, serialize_conflicts, serialize_proposal


class SchedulerUseCases:

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

    def _restricted_slots_for(self, teacher: str, group: str) -> set:
        """Franges (dia, hora) marcades com a no disponibles per aquest
        professor o grup a les seves restriccions (independent dels
        conflictes d'activitat contra activitat que ja comprova validate())."""
        restricted: set = set()
        for record in self._academic_data_repo.active_teacher_restrictions():
            if teacher and record.get("teacher") == teacher:
                for slot in record.get("unavailable_slots", []):
                    parts = str(slot).split(" ", 1)
                    if len(parts) == 2:
                        restricted.add((parts[0], parts[1]))
        for record in self._academic_data_repo.active_group_restrictions():
            if group and record.get("group") == group:
                for slot in record.get("unavailable_slots", []):
                    parts = str(slot).split(" ", 1)
                    if len(parts) == 2:
                        restricted.add((parts[0], parts[1]))
        return restricted

    def _suggest_alternative_slots(
        self,
        base_activities: List["Activity"],
        target_activity: "Activity",
        exclude_pairs: set,
        baseline_keys: set,
        max_results: int = 3,
    ) -> List[Dict[str, str]]:
        """Try every (day, start) combo and return up to max_results where
        target_activity would fit without introducing new conflicts, and
        that aren't marked as unavailable for this teacher/group."""
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        suggestions: List[Dict[str, str]] = []
        restricted_slots = self._restricted_slots_for(target_activity.teacher, target_activity.group)

        for day in day_names:
            for start in hour_names:
                if (day, start) in exclude_pairs or (day, start) in restricted_slots:
                    continue

                candidate = Activity(
                    id=target_activity.id,
                    teacher=target_activity.teacher,
                    subject=target_activity.subject,
                    group=target_activity.group,
                    room=target_activity.room,
                    day=day,
                    start=start,
                    duration=target_activity.duration,
                    fixed=bool(getattr(target_activity, "fixed", False)),
                )
                schedule = self._build_schedule(base_activities + [candidate])
                conflicts = self._scheduler_engine.validate(schedule)
                new_conflicts = [c for c in conflicts if self._conflict_key(c) not in baseline_keys]

                if not new_conflicts:
                    suggestions.append({"day": day, "start": start})
                    if len(suggestions) >= max_results:
                        return suggestions

        return suggestions

    def __init__(
        self,
        requirement_repo: Any,
        scheduler_engine: SchedulerEngine,
        proposal_store: Dict[str, ScheduleProposal],
        school_calendar: SchoolCalendar | None = None,
        time_labels: Dict[str, List[str]] | None = None,
        academic_data_repo: AcademicDataRepository | None = None,
        working_timetable_repo: WorkingTimetableRepository | None = None,
    ) -> None:
        self._requirement_repo = requirement_repo
        self._scheduler_engine = scheduler_engine
        self._proposal_store = proposal_store
        self._school_calendar = school_calendar or SchoolCalendar()
        self._time_labels = time_labels or {"day_names": [], "hour_names": []}
        self._academic_data_repo = academic_data_repo
        self._working_timetable_repo = working_timetable_repo
        self._move_history: Dict[str, List[Any]] = {}
        self._redo_history: Dict[str, List[Any]] = {}

    def validate(self, activities: List[Dict[str, Any]]) -> List[Any]:
        schedule = Schedule()
        for activity in activities:
            schedule.add(
                Activity(
                    id=activity["id"],
                    teacher=activity["teacher"],
                    subject=activity["subject"],
                    group=activity["group"],
                    room=activity["room"],
                    day=activity["day"],
                    start=activity["start"],
                    duration=activity["duration"],
                )
            )

        engine = SchedulerEngine()
        return engine.validate(schedule)

    def generate_proposals(self, requirement_ids: List[str]) -> Dict[str, Any]:
        if not requirement_ids:
            if self._academic_data_repo is not None and self._academic_data_repo.active_teaching_assignments():
                return self.generate_proposals_from_academic_data()
            return self._generate_empty_generation_result()

        requirements: List[TeachingRequirement] = []
        for requirement_id in requirement_ids:
            requirement = self._requirement_repo.get(requirement_id)
            if requirement is not None:
                requirements.append(requirement)

        if not requirements:
            raise LookupError("requirements_not_found")

        context = GenerationContext(
            school_calendar=self._school_calendar,
            existing_scheduled_activities=(),
            fixed_activities=(),
            blocked_time_slots=(),
            configuration={"room_constraints_enabled": False},
        )
        generator = SchedulerGenerator()
        generation_result = generator.generate(requirements, context)

        if not generation_result.valid or not generation_result.proposals:
            raise RuntimeError("generation_failed")

        for proposal in generation_result.proposals:
            self._proposal_store[proposal.id] = proposal

        if generation_result.schedule_proposal is not None:
            self._proposal_store[generation_result.schedule_proposal.id] = generation_result.schedule_proposal
            self._persist_proposal_state(generation_result.schedule_proposal, generation_result.statistics, [])

        return {
            "valid": generation_result.valid,
            "best_proposal": serialize_proposal(generation_result.schedule_proposal),
            "proposals": [serialize_proposal(proposal) for proposal in generation_result.proposals],
            "scores": [proposal.score for proposal in generation_result.proposals],
            "conflicts": [
                [serialize_conflict(conflict) for conflict in proposal.conflicts]
                for proposal in generation_result.proposals
            ],
            "statistics": generation_result.statistics,
            "unscheduled_activities": [],
        }

    def generate_proposals_from_academic_data(self) -> Dict[str, Any]:
        if self._academic_data_repo is None:
            return self._generate_empty_generation_result()

        assignments = self._academic_data_repo.active_teaching_assignments()
        if not assignments:
            return self._generate_empty_generation_result()

        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        day_indexes = {name: index for index, name in enumerate(day_names)}
        hour_indexes = {name: index for index, name in enumerate(hour_names)}

        flexible_assignments = []
        fixed_scheduled_activities: List[ScheduledActivity] = []
        for assignment in assignments:
            fixed_day = (assignment.get("fixed_day") or "").strip()
            fixed_start = (assignment.get("fixed_start") or "").strip()
            if fixed_day and fixed_start and fixed_day in day_indexes and fixed_start in hour_indexes:
                fixed_scheduled_activities.append(
                    self._build_fixed_activity_from_assignment(
                        assignment, day_indexes[fixed_day], hour_indexes[fixed_start]
                    )
                )
            else:
                flexible_assignments.append(assignment)

        teacher_restrictions = self._academic_data_repo.active_teacher_restrictions()
        group_restrictions = self._academic_data_repo.active_group_restrictions()

        restricted_teacher_names = {
            name
            for restriction in teacher_restrictions
            if restriction.get("unavailable_slots") or restriction.get("preferred_availability")
            for name in teacher_names(restriction.get("teacher"))
        }
        restricted_group_names = {
            (restriction.get("group") or "").strip()
            for restriction in group_restrictions
            if (
                restriction.get("unavailable_slots")
                or restriction.get("preferred_availability")
                or restriction.get("daily_start_time")
                or restriction.get("daily_max_end_time")
                or restriction.get("max_days")
            )
        }
        requirements = [
            self._build_requirement_from_assignment(index, assignment, restricted_teacher_names, restricted_group_names)
            for index, assignment in enumerate(flexible_assignments, start=1)
        ]
        blocked_activities = self._build_blocked_activities_from_restrictions(
            teacher_restrictions,
            group_restrictions,
        )
        blocked_activities += fixed_scheduled_activities

        split_groups = {
            (group.get("name") or "").strip()
            for group in self._academic_data_repo.list_groups()
            if group.get("is_split")
        }

        context = GenerationContext(
            school_calendar=self._school_calendar,
            existing_scheduled_activities=tuple(blocked_activities),
            fixed_activities=tuple(fixed_scheduled_activities),
            blocked_time_slots=(),
            configuration={
                "room_constraints_enabled": True,
                "day_names": day_names,
                "hour_names": hour_names,
                "split_groups": split_groups,
                "group_time_window_constraints": self._build_group_time_window_constraints(group_restrictions, hour_names),
                "group_max_days_constraints": self._build_group_max_days_constraints(group_restrictions),
            },
        )

        generator = SchedulerGenerator()
        generation_result = generator.generate(requirements, context)
        if not generation_result.valid or not generation_result.proposals:
            raise RuntimeError("generation_failed")

        fixed_activities = [
            self._scheduled_to_activity(activity, day_names, hour_names) for activity in fixed_scheduled_activities
        ]
        payload_for_merge = {"fixed_activities": fixed_scheduled_activities, "floating_blocks": []}
        proposals = [
            self._merge_fixed_activities_into_proposal(
                proposal,
                payload_for_merge,
                fixed_activities,
                day_names,
                hour_names,
            )
            for proposal in generation_result.proposals
        ]
        proposals = [
            self._apply_consecutive_group_preferences(proposal, assignments, hour_names)
            for proposal in proposals
        ]
        proposals = [self._apply_quarter_pair_alignment(proposal) for proposal in proposals]
        for proposal in proposals:
            compacted_activities, _ = self._compact_activities(list(proposal.activities))
            proposal.activities = self._insert_default_group_breaks(compacted_activities)
        proposals.sort(key=lambda proposal: proposal.score, reverse=True)

        for proposal in proposals:
            self._proposal_store[proposal.id] = proposal

        best_proposal = proposals[0]

        # Unifica "Incidències de generació" i "Sense franja": totes dues
        # han de mostrar exactament les mateixes activitats no col·locades.
        # Abans es calculaven per vies separades (aquí sempre quedava buit).
        unscheduled_from_warnings = [
            {
                "id": warning.get("id"),
                "teacher": warning.get("teacher", ""),
                "subject": warning.get("subject", ""),
                "group": warning.get("group", ""),
                "room": "",
                "duration": warning.get("duration", 1),
                "reason": warning.get("reason", ""),
            }
            for warning in (best_proposal.warnings or [])
            if isinstance(warning, dict) and warning.get("id") is not None
        ]
        for proposal in proposals:
            proposal.metadata = {**(proposal.metadata or {}), "unscheduled_activities": unscheduled_from_warnings}

        self._persist_proposal_state(
            best_proposal,
            {
                **generation_result.statistics,
                "source": "academic_workbook",
                "fixed_activities_total": len(fixed_activities),
            },
            unscheduled_from_warnings,
        )

        return {
            "valid": generation_result.valid,
            "best_proposal": serialize_proposal(best_proposal),
            "proposals": [serialize_proposal(proposal) for proposal in proposals],
            "scores": [proposal.score for proposal in proposals],
            "conflicts": [
                [serialize_conflict(conflict) for conflict in proposal.conflicts]
                for proposal in proposals
            ],
            "statistics": {
                **generation_result.statistics,
                "source": "academic_workbook",
                "fixed_activities_total": len(fixed_activities),
            },
            "unscheduled_activities": unscheduled_from_warnings,
        }

    def accept_proposal(self, proposal_id: str) -> Dict[str, Any]:
        proposal = self._proposal_store.get(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")

        unscheduled = (proposal.metadata or {}).get("unscheduled_activities", [])
        if unscheduled:
            return {
                "ok": False,
                "error": "unscheduled_activities_pending",
                "unscheduled_activities": unscheduled,
            }

        accepted_schedule = Schedule()
        for activity in proposal.activities:
            accepted_schedule.add(activity)

        conflicts = self._scheduler_engine.validate(accepted_schedule)
        if conflicts:
            return {
                "ok": False,
                "conflicts": serialize_conflicts(conflicts),
            }

        self._scheduler_engine.load(accepted_schedule)
        self._persist_active_schedule(clear_proposal=True)
        return {
            "ok": True,
            "message": "Proposal accepted",
        }

    def move_proposal_activity(
        self,
        proposal_id: str,
        activity_id: int,
        day: str,
        start: str,
    ) -> Dict[str, Any]:

        print("\n========== MOVE ==========")
        print("Proposal rebuda:", proposal_id)

        print("Proposal store:")

        for key in self._proposal_store.keys():
            print(" -", key)

        print("==========================\n")

        proposal = self._proposal_store.get(proposal_id)

        if proposal is None:
            raise LookupError("proposal_not_found")

        current_activities = [
            Activity(
                id=activity.id,
                teacher=activity.teacher,
                subject=activity.subject,
                group=activity.group,
                room=activity.room,
                day=activity.day,
                start=activity.start,
                duration=activity.duration,
                fixed=bool(getattr(activity, "fixed", False)),
            )
            for activity in proposal.activities
        ]

        baseline_schedule = self._build_schedule(current_activities)
        baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        target_activity = next(
            (item for item in current_activities if item.id == activity_id),
            None,
        )

        unscheduled_activities = list((proposal.metadata or {}).get("unscheduled_activities", []))
        newly_placed = False
        previous_day = previous_start = None

        if target_activity is None:
            # Not yet on the schedule: it may be one of the "unscheduled"
            # activities shown as incidences, which the user is placing
            # manually via drag & drop.
            pending_activity = next(
                (item for item in unscheduled_activities if item.get("id") == activity_id),
                None,
            )
            if pending_activity is None:
                return {
                    "ok": False,
                    "error": "activity_not_found",
                    "proposal": serialize_proposal(proposal),
                }

            target_activity = Activity(
                id=pending_activity["id"],
                teacher=pending_activity.get("teacher", ""),
                subject=pending_activity.get("subject", ""),
                group=pending_activity.get("group", ""),
                room=pending_activity.get("room", ""),
                day=day,
                start=start,
                duration=pending_activity.get("duration", 1),
            )
            current_activities.append(target_activity)
            newly_placed = True
        else:
            previous_day = target_activity.day
            previous_start = target_activity.start
            target_activity.day = day
            target_activity.start = start

        candidate_schedule = self._build_schedule(current_activities)
        conflicts = self._scheduler_engine.validate(candidate_schedule)

        new_conflicts = [
            conflict
            for conflict in conflicts
            if self._conflict_key(conflict) not in baseline_keys
        ]

        if new_conflicts:
            exclude_pairs = {(day, start)}
            if not newly_placed:
                exclude_pairs.add((previous_day, previous_start))
                base_activities = [a for a in current_activities if a is not target_activity]
                target_activity.day = previous_day
                target_activity.start = previous_start
            else:
                current_activities.remove(target_activity)
                base_activities = current_activities

            suggestions = self._suggest_alternative_slots(
                base_activities, target_activity, exclude_pairs, baseline_keys
            )

            return {
                "ok": False,
                "error": "validation_failed",
                "conflicts": serialize_conflicts(new_conflicts),
                "suggested_slots": suggestions,
                "proposal": serialize_proposal(proposal),
            }

        updated_metadata = dict(proposal.metadata or {})
        if newly_placed:
            updated_metadata["unscheduled_activities"] = [
                item for item in unscheduled_activities if item.get("id") != activity_id
            ]

        updated_proposal = ScheduleProposal(
            id=proposal.id,
            activities=current_activities,
            score=proposal.score,
            conflicts=conflicts,
            warnings=proposal.warnings,
            score_breakdown=getattr(proposal, "score_breakdown", None),
            metadata=updated_metadata,
        )
        self._redo_history.pop(proposal_id, None)
        self._move_history.setdefault(proposal_id, []).append(proposal)
        self._proposal_store[proposal_id] = updated_proposal
        self._persist_proposal_state(
            updated_proposal,
            self._load_snapshot().generation_stats,
            list((updated_proposal.metadata or {}).get("unscheduled_activities", [])),
        )

        return {
            "ok": True,
            "proposal": serialize_proposal(updated_proposal),
            "unscheduled_activities": updated_metadata.get("unscheduled_activities", []),
        }

    def swap_proposal_activities(
        self, proposal_id: str, activity_id_a: int, activity_id_b: int
    ) -> Dict[str, Any]:
        """Swap the day/start of two already-scheduled activities in a proposal."""
        proposal = self._proposal_store.get(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")

        current_activities = [
            Activity(
                id=activity.id,
                teacher=activity.teacher,
                subject=activity.subject,
                group=activity.group,
                room=activity.room,
                day=activity.day,
                start=activity.start,
                duration=activity.duration,
                fixed=bool(getattr(activity, "fixed", False)),
            )
            for activity in proposal.activities
        ]

        baseline_schedule = self._build_schedule(current_activities)
        baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        activity_a = next((item for item in current_activities if item.id == activity_id_a), None)
        activity_b = next((item for item in current_activities if item.id == activity_id_b), None)

        if activity_a is None or activity_b is None:
            return {
                "ok": False,
                "error": "activity_not_found",
                "proposal": serialize_proposal(proposal),
            }

        activity_a.day, activity_b.day = activity_b.day, activity_a.day
        activity_a.start, activity_b.start = activity_b.start, activity_a.start

        candidate_schedule = self._build_schedule(current_activities)
        conflicts = self._scheduler_engine.validate(candidate_schedule)
        new_conflicts = [
            conflict
            for conflict in conflicts
            if self._conflict_key(conflict) not in baseline_keys
        ]

        if new_conflicts:
            activity_a.day, activity_b.day = activity_b.day, activity_a.day
            activity_a.start, activity_b.start = activity_b.start, activity_a.start
            return {
                "ok": False,
                "error": "validation_failed",
                "conflicts": serialize_conflicts(new_conflicts),
                "proposal": serialize_proposal(proposal),
            }

        updated_proposal = ScheduleProposal(
            id=proposal.id,
            activities=current_activities,
            score=proposal.score,
            conflicts=conflicts,
            warnings=proposal.warnings,
            score_breakdown=getattr(proposal, "score_breakdown", None),
            metadata=dict(proposal.metadata or {}),
        )
        self._move_history.setdefault(proposal_id, []).append(proposal)
        self._redo_history.pop(proposal_id, None)
        self._proposal_store[proposal_id] = updated_proposal
        self._persist_proposal_state(
            updated_proposal,
            self._load_snapshot().generation_stats,
            list((updated_proposal.metadata or {}).get("unscheduled_activities", [])),
        )

        return {
            "ok": True,
            "proposal": serialize_proposal(updated_proposal),
        }

    def undo_last_move(self, proposal_id: str) -> Dict[str, Any]:
        """Revert the last move/swap applied to a proposal."""
        if proposal_id not in self._proposal_store:
            raise LookupError("proposal_not_found")

        history = self._move_history.get(proposal_id)
        if not history:
            return {"ok": False, "error": "nothing_to_undo"}

        current_proposal = self._proposal_store[proposal_id]
        previous_proposal = history.pop()
        self._redo_history.setdefault(proposal_id, []).append(current_proposal)
        self._proposal_store[proposal_id] = previous_proposal
        self._persist_proposal_state(
            previous_proposal,
            self._load_snapshot().generation_stats,
            list((previous_proposal.metadata or {}).get("unscheduled_activities", [])),
        )

        return {
            "ok": True,
            "proposal": serialize_proposal(previous_proposal),
            "unscheduled_activities": list((previous_proposal.metadata or {}).get("unscheduled_activities", [])),
        }

    def redo_last_move(self, proposal_id: str) -> Dict[str, Any]:
        """Re-apply the last move/swap that was undone."""
        if proposal_id not in self._proposal_store:
            raise LookupError("proposal_not_found")

        redo_stack = self._redo_history.get(proposal_id)
        if not redo_stack:
            return {"ok": False, "error": "nothing_to_redo"}

        current_proposal = self._proposal_store[proposal_id]
        next_proposal = redo_stack.pop()
        self._move_history.setdefault(proposal_id, []).append(current_proposal)
        self._proposal_store[proposal_id] = next_proposal
        self._persist_proposal_state(
            next_proposal,
            self._load_snapshot().generation_stats,
            list((next_proposal.metadata or {}).get("unscheduled_activities", [])),
        )

        return {
            "ok": True,
            "proposal": serialize_proposal(next_proposal),
            "unscheduled_activities": list((next_proposal.metadata or {}).get("unscheduled_activities", [])),
        }

    def suggest_slots_for_unscheduled(
        self, proposal_id: str, activity_id: int, max_results: int = 3
    ) -> Dict[str, Any]:
        """Suggest slots where a currently-unscheduled (pending) activity
        could be placed, given the rest of the schedule already in place."""
        proposal = self._proposal_store.get(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")

        unscheduled = list((proposal.metadata or {}).get("unscheduled_activities", []))
        pending = next((item for item in unscheduled if item.get("id") == activity_id), None)
        if pending is None:
            return {"ok": False, "error": "activity_not_found"}

        current_activities = [
            Activity(
                id=activity.id,
                teacher=activity.teacher,
                subject=activity.subject,
                group=activity.group,
                room=activity.room,
                day=activity.day,
                start=activity.start,
                duration=activity.duration,
                fixed=bool(getattr(activity, "fixed", False)),
            )
            for activity in proposal.activities
        ]

        baseline_schedule = self._build_schedule(current_activities)
        baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        target_activity = Activity(
            id=pending["id"],
            teacher=pending.get("teacher", ""),
            subject=pending.get("subject", ""),
            group=pending.get("group", ""),
            room=pending.get("room", ""),
            day="",
            start="",
            duration=pending.get("duration", 1),
        )

        suggestions = self._suggest_alternative_slots(
            current_activities, target_activity, set(), baseline_keys, max_results=max_results
        )

        return {"ok": True, "suggested_slots": suggestions}

    def _scheduled_to_activity(
        self,
        scheduled_activity: Any,
        day_names: List[str],
        hour_names: List[str],
    ) -> Activity:
        metadata = scheduled_activity.teaching_block.metadata or {}
        return Activity(
            id=metadata.get(
                "fet_id",
                zlib.crc32(
                    f"{scheduled_activity.teaching_block.id}|{scheduled_activity.day}|{scheduled_activity.start_timeslot.period}".encode(
                        "utf-8"
                    )
                ),
            ),
            teacher=scheduled_activity.teacher_id or metadata.get("teacher", ""),
            subject=metadata.get("subject") or metadata.get("subject_id") or scheduled_activity.teaching_block.id,
            group=scheduled_activity.group_id or metadata.get("group", ""),
            room=scheduled_activity.room_id or metadata.get("room", ""),
            day=day_names[scheduled_activity.day] if scheduled_activity.day < len(day_names) else f"Day {scheduled_activity.day}",
            start=hour_names[scheduled_activity.start_timeslot.period]
            if scheduled_activity.start_timeslot.period < len(hour_names)
            else f"Period {scheduled_activity.start_timeslot.period}",
            duration=scheduled_activity.duration,
            fixed=bool(getattr(scheduled_activity.teaching_block, "fixed", False)),
        )

    def _merge_fixed_activities_into_proposal(
        self,
        proposal: ScheduleProposal,
        payload: Dict[str, Any],
        fixed_activities: List[Activity],
        day_names: List[str],
        hour_names: List[str],
    ) -> ScheduleProposal:
        scheduled_activities = (proposal.metadata or {}).get("scheduled_activities", [])
        generated_activities = [self._scheduled_to_activity(activity, day_names, hour_names) for activity in scheduled_activities]
        full_schedule = Schedule()
        merged_activities = list(fixed_activities) + generated_activities
        for activity in merged_activities:
            full_schedule.add(activity)
        group_restrictions = self._academic_data_repo.active_group_restrictions()
        full_schedule.configuration = {
            "day_names": day_names,
            "split_groups": {
                (group.get("name") or "").strip()
                for group in self._academic_data_repo.list_groups()
                if group.get("is_split")
            },
            "group_time_window_constraints": self._build_group_time_window_constraints(group_restrictions, hour_names),
            "group_max_days_constraints": self._build_group_max_days_constraints(group_restrictions),
        }

        updated_metadata = dict(proposal.metadata or {})
        updated_metadata["unscheduled_activities"] = self._build_unscheduled_activities(payload, merged_activities)

        return ScheduleProposal(
            id=proposal.id,
            activities=merged_activities,
            score=proposal.score,
            warnings=proposal.warnings,
            conflicts=self._scheduler_engine.validate(full_schedule),
            score_breakdown=proposal.score_breakdown,
            metadata=updated_metadata,
        )

    def _build_unscheduled_activities(
        self,
        payload: Dict[str, Any],
        activities: List[Activity],
    ) -> List[Dict[str, Any]]:
        scheduled_ids = {activity.id for activity in activities}
        unscheduled = []

        for block in payload["floating_blocks"]:
            metadata = block.metadata or {}
            fet_id = metadata.get("fet_id")
            if fet_id in scheduled_ids:
                continue

            unscheduled.append(
                {
                    "id": fet_id,
                    "teacher": metadata.get("teacher", ""),
                    "subject": metadata.get("subject", block.id),
                    "group": metadata.get("group", ""),
                    "room": metadata.get("room", ""),
                    "duration": block.duration_blocks or 0,
                    "reason": "No s'ha trobat cap franja compatible amb la proposta actual.",
                }
            )

        return sorted(unscheduled, key=lambda activity: activity["id"])

    def _build_fixed_activity_from_assignment(
        self, assignment: Dict[str, Any], day_index: int, hour_index: int
    ) -> ScheduledActivity:
        subject = str(assignment["subject"])
        group = str(assignment["group"])
        teacher = str(assignment["teacher"])
        weekly_hours = float(assignment["weekly_hours"])
        duration_blocks = max(int(round(weekly_hours * 2)), 1)
        metadata = {
            "subject": subject,
            "group": group,
            "teacher": teacher,
        }
        teaching_block = TeachingBlock(
            id=f"fixed-{teacher}-{subject}-{group}",
            duration=weekly_hours,
            order=0,
            duration_blocks=duration_blocks,
            preferred_room_id=assignment.get("preferred_room", "") or "",
            preferred_teacher_id=teacher,
            fixed=True,
            fixed_day=str(assignment.get("fixed_day") or "") or None,
            fixed_start=str(assignment.get("fixed_start") or "") or None,
            metadata=metadata,
        )
        return ScheduledActivity(
            teaching_block=teaching_block,
            day=day_index,
            start_timeslot=TimeSlot(day=day_index, period=hour_index),
            duration=duration_blocks,
            room_id=assignment.get("preferred_room", "") or "",
            teacher_id=teacher,
            group_id=group,
            metadata=metadata,
        )

    def _build_group_time_window_constraints(
        self,
        group_restrictions: List[Dict[str, Any]],
        hour_names: List[str],
    ) -> Dict[str, Tuple[int, int]]:
        constraints: Dict[str, Tuple[int, int]] = {}

        for restriction in group_restrictions:
            group_name = (restriction.get("group") or "").strip()
            if not group_name:
                continue

            start_minutes = self._parse_time_to_minutes(restriction.get("daily_start_time"), hour_names)
            end_minutes = self._parse_time_to_minutes(restriction.get("daily_max_end_time"), hour_names)

            if start_minutes is None or end_minutes is None:
                preferred_slots = restriction.get("preferred_availability") or []
                preferred_minutes: List[int] = []
                for slot in preferred_slots:
                    _, _, slot_time = str(slot).partition("-")
                    minutes = self._parse_time_to_minutes(slot_time, hour_names)
                    if minutes is not None:
                        preferred_minutes.append(minutes)
                if preferred_minutes:
                    start_minutes = min(preferred_minutes)
                    end_minutes = max(preferred_minutes)

            if start_minutes is None or end_minutes is None:
                continue

            if start_minutes > end_minutes:
                start_minutes, end_minutes = end_minutes, start_minutes

            constraints[group_name.upper()] = (start_minutes, end_minutes)

        return constraints

    def _build_group_max_days_constraints(
        self,
        group_restrictions: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        constraints: Dict[str, int] = {}

        for restriction in group_restrictions:
            group_name = (restriction.get("group") or "").strip()
            if not group_name:
                continue

            raw_max_days = restriction.get("max_days")
            if raw_max_days is None or raw_max_days == "":
                continue

            try:
                max_days = int(raw_max_days)
            except (TypeError, ValueError):
                continue

            if max_days <= 0:
                continue

            constraints[group_name.upper()] = max_days

        return constraints

    def _parse_time_to_minutes(self, value: Any, hour_names: List[str]) -> Optional[int]:
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        if ":" in text:
            hour_text, minute_text = text.split(":", 1)
            try:
                return int(hour_text) * 60 + int(minute_text)
            except ValueError:
                return None

        if text.isdigit() and hour_names:
            index = int(text)
            if 0 <= index < len(hour_names):
                return self._parse_time_to_minutes(hour_names[index], hour_names)

        return None

    def _build_requirement_from_assignment(
        self,
        index: int,
        assignment: Dict[str, Any],
        restricted_teacher_names: set[str],
        restricted_group_names: set[str],
    ) -> TeachingRequirement:
        teacher = str(assignment.get("teacher", ""))
        teacher_list = teacher_names(teacher)
        subject = str(assignment.get("subject", ""))
        group = str(assignment.get("group", ""))
        weekly_hours = float(assignment.get("weekly_hours", 0.0) or 0.0)
        preferred_room = str(assignment.get("preferred_room", "") or "")
        allow_half_hour_blocks = bool(assignment.get("allow_half_hour_blocks", False))

        has_teacher_restrictions = bool(set(teacher_list).intersection(restricted_teacher_names))
        has_group_restrictions = group in restricted_group_names

        return TeachingRequirement(
            id=str(assignment.get("id") or f"assignment-{index}"),
            group_id=group,
            subject_id=subject,
            teacher_id=teacher_label(teacher_list or teacher),
            weekly_hours=weekly_hours,
            min_days=int(assignment.get("min_days") or assignment.get("min_distribution_days") or 1),
            max_days=int(assignment.get("max_days") or assignment.get("max_distribution_days") or 1),
            min_block_duration=float(assignment.get("min_block_duration") or 0.5),
            max_consecutive_hours=float(assignment.get("max_consecutive_hours") or weekly_hours or 0.5),
            allow_half_hour_blocks=allow_half_hour_blocks,
            min_distribution_days=assignment.get("min_distribution_days"),
            max_distribution_days=assignment.get("max_distribution_days"),
            preferred_rooms=[preferred_room] if preferred_room else [],
            fixed_teacher=has_teacher_restrictions,
            priority=1 if has_teacher_restrictions or has_group_restrictions else int(assignment.get("priority") or 2),
            fixed_day=assignment.get("fixed_day") or None,
            fixed_start=assignment.get("fixed_start") or None,
        )

    def _expand_preferred_availability_to_blocked_slots(
        self,
        preferred_slots: List[Any],
        day_names: List[str],
        hour_names: List[str],
    ) -> List[str]:
        """`preferred_availability` és una llista blanca (p.ex. "Dilluns-09:00")
        amb les úniques franges en què algú està disponible — a diferència
        d'`unavailable_slots`, que és una llista negra. Perquè el generador
        respecti de veritat aquesta restricció (i no només l'usi per prioritzar),
        cal bloquejar totes les franges de la setmana que NO hi apareixen.
        Si la llista és buida, no es bloqueja res (no hi ha restricció)."""
        allowed_pairs: set[Tuple[str, str]] = set()
        for slot in preferred_slots:
            day_label, separator, hour_label = str(slot).partition("-")
            if not separator:
                continue
            allowed_pairs.add((day_label.strip(), hour_label.strip()))

        if not allowed_pairs:
            return []

        blocked_labels: List[str] = []
        for day_label in day_names:
            for hour_label in hour_names:
                if (day_label, hour_label) not in allowed_pairs:
                    blocked_labels.append(f"{day_label} {hour_label}")
        return blocked_labels

    def _build_blocked_activities_from_restrictions(
        self,
        teacher_restrictions: List[Dict[str, Any]],
        group_restrictions: List[Dict[str, Any]],
    ) -> List[ScheduledActivity]:
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        day_indexes = {name: index for index, name in enumerate(day_names)}
        hour_indexes = {name: index for index, name in enumerate(hour_names)}

        blocked: List[ScheduledActivity] = []

        def add_blocked_activity(
            *,
            teacher_id: str = "",
            group_id: str = "",
            slot_label: str,
            constraint: str,
        ) -> None:
            parts = slot_label.rsplit(" ", 1)
            if len(parts) != 2:
                return
            day_label, hour_label = parts
            if day_label not in day_indexes or hour_label not in hour_indexes:
                return

            day_index = day_indexes[day_label]
            hour_index = hour_indexes[hour_label]
            teaching_block = TeachingBlock(
                id=f"blocked-{constraint}-{teacher_id or group_id}-{day_index}-{hour_index}",
                duration=0.5,
                order=0,
                duration_blocks=1,
                preferred_teacher_id=teacher_id or None,
                metadata={"synthetic": True, "constraint": constraint},
            )
            blocked.append(
                ScheduledActivity(
                    teaching_block=teaching_block,
                    day=day_index,
                    start_timeslot=TimeSlot(day=day_index, period=hour_index),
                    duration=1,
                    room_id="",
                    teacher_id=teacher_id,
                    group_id=group_id,
                    metadata={"synthetic": True, "constraint": constraint},
                )
            )

        for restriction in teacher_restrictions:
            teacher = (restriction.get("teacher") or "").strip()
            if not teacher:
                continue
            for slot in restriction.get("unavailable_slots") or []:
                add_blocked_activity(teacher_id=teacher, slot_label=str(slot), constraint="teacher_not_available")
            for slot_label in self._expand_preferred_availability_to_blocked_slots(
                restriction.get("preferred_availability") or [], day_names, hour_names
            ):
                add_blocked_activity(teacher_id=teacher, slot_label=slot_label, constraint="teacher_not_available")

        for restriction in group_restrictions:
            group = (restriction.get("group") or "").strip()
            if not group:
                continue
            for slot in restriction.get("unavailable_slots") or []:
                add_blocked_activity(group_id=group, slot_label=str(slot), constraint="group_not_available")
            for slot_label in self._expand_preferred_availability_to_blocked_slots(
                restriction.get("preferred_availability") or [], day_names, hour_names
            ):
                add_blocked_activity(group_id=group, slot_label=slot_label, constraint="group_not_available")

        return blocked

    def _apply_consecutive_group_preferences(
        self, proposal: ScheduleProposal, assignments: List[Dict[str, Any]], hour_names: List[str]
    ) -> ScheduleProposal:
        """Si dues assignacions comparteixen una mateixa etiqueta `consecutive_group`,
        intenta col·locar-les una justa darrere l'altra (mateix dia, sense forat).
        Preferència: si una acaba en '1Q' i l'altra en '2Q', la 1Q va primera, però
        s'accepta l'ordre invers si és l'única manera de fer-les consecutives."""
        hour_index = {name: index for index, name in enumerate(hour_names)}

        tags: Dict[str, List[Dict[str, Any]]] = {}
        for assignment in assignments:
            tag = (assignment.get("consecutive_group") or "").strip()
            if tag:
                tags.setdefault(tag, []).append(assignment)

        if not tags:
            return proposal

        activities = list(proposal.activities)
        by_key = {(a.subject, a.group, a.teacher): a for a in activities}

        def quarter(activity) -> str | None:
            text = (activity.subject or "").strip().lower()
            if text.endswith("1q"):
                return "1q"
            if text.endswith("2q"):
                return "2q"
            return None

        def is_adjacent(first, second) -> bool:
            if first.start not in hour_index or second.start not in hour_index:
                return False
            return (
                first.day == second.day
                and hour_index[second.start] == hour_index[first.start] + (first.duration or 1)
            )

        for tag, members in tags.items():
            if len(members) != 2:
                continue
            key_a = (members[0]["subject"], members[0]["group"], members[0]["teacher"])
            key_b = (members[1]["subject"], members[1]["group"], members[1]["teacher"])
            act_a = by_key.get(key_a)
            act_b = by_key.get(key_b)
            if act_a is None or act_b is None or act_a is act_b:
                continue
            if act_a.start not in hour_index or act_b.start not in hour_index:
                continue
            if is_adjacent(act_a, act_b) or is_adjacent(act_b, act_a):
                continue

            quarter_a, quarter_b = quarter(act_a), quarter(act_b)
            if quarter_a == "2q" and quarter_b == "1q":
                preferred_first, preferred_second = act_b, act_a
            else:
                preferred_first, preferred_second = act_a, act_b

            baseline_schedule = self._build_schedule(activities)
            baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
            baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

            for first, second in ((preferred_first, preferred_second), (preferred_second, preferred_first)):
                start_index = hour_index.get(first.start)
                if start_index is None:
                    continue
                new_index = start_index + (first.duration or 1)
                if new_index >= len(hour_names):
                    continue

                original_day, original_start = second.day, second.start
                second.day = first.day
                second.start = hour_names[new_index]

                candidate_schedule = self._build_schedule(activities)
                candidate_conflicts = self._scheduler_engine.validate(candidate_schedule)
                new_keys = [
                    conflict for conflict in candidate_conflicts
                    if self._conflict_key(conflict) not in baseline_keys
                ]
                if not new_keys:
                    break

                second.day, second.start = original_day, original_start

        final_schedule = self._build_schedule(activities)
        final_conflicts = self._scheduler_engine.validate(final_schedule)

        return ScheduleProposal(
            id=proposal.id,
            activities=activities,
            score=proposal.score,
            conflicts=final_conflicts,
            warnings=proposal.warnings,
            score_breakdown=getattr(proposal, "score_breakdown", None),
            metadata=dict(proposal.metadata or {}),
        )

    def _match_quarter_pairs(
        self, ones: List[Activity], twos: List[Activity]
    ) -> List[Tuple[Activity, Activity]]:
        """Aparella cada activitat marcada 1Q amb una de 2Q del mateix grup
        pare (mai 1Q amb 1Q ni 2Q amb 2Q). Quan un grup té més d'una parella
        possible, prioritza les combinacions on coincideix el professor;
        la resta s'aparellen en l'ordre en què apareixen com a darrer recurs,
        perquè cap activitat 1Q o 2Q es quedi sense parella si n'hi ha una
        de disponible. L'ordre retornat és sempre (activitat_1Q, activitat_2Q)."""
        remaining_ones = list(ones)
        remaining_twos = list(twos)
        pairs: List[Tuple[Activity, Activity]] = []

        for one in list(remaining_ones):
            match = next(
                (two for two in remaining_twos if (one.teacher or "").strip() and one.teacher == two.teacher),
                None,
            )
            if match is not None:
                pairs.append((one, match))
                remaining_ones.remove(one)
                remaining_twos.remove(match)

        for one, two in zip(remaining_ones, remaining_twos):
            pairs.append((one, two))

        return pairs

    def _apply_quarter_pair_alignment(self, proposal: ScheduleProposal) -> ScheduleProposal:
        """Si dues activitats són la variant 1Q i 2Q del mateix grup pare,
        intenta que comparteixin exactament la mateixa casella (dia i hora),
        perquè es mostrin juntes al calendari, sempre que això no introdueixi
        cap conflicte nou.

        Primer busca la franja MÉS D'HORA de tota la setmana on totes dues
        hi càpiguen (evita que la parella quedi relegada a l'hora on una
        d'elles va caure per casualitat durant la generació inicial, per
        exemple perquè altres assignatures del grup ja ocupaven la primera
        hora). Si no en troba cap (o si les dues duren coses diferents, cas
        en què compartir franja exacta no és possible), cau al comportament
        anterior: prova només les dues franges on ja es troben."""
        activities = list(proposal.activities)

        by_parent: Dict[str, Dict[str, List[Activity]]] = {}
        for activity in activities:
            parent, quarter_marker = _parent_and_quarter(activity.group, activity.subject)
            if quarter_marker is None:
                continue
            by_parent.setdefault(parent, {"1q": [], "2q": []})[quarter_marker].append(activity)

        pairs_to_align: List[Tuple[Activity, Activity]] = []
        for buckets in by_parent.values():
            pairs_to_align.extend(self._match_quarter_pairs(buckets["1q"], buckets["2q"]))

        if not pairs_to_align:
            return proposal

        baseline_schedule = self._build_schedule(activities)
        baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        for act_a, act_b in pairs_to_align:
            if act_a.day == act_b.day and act_a.start == act_b.start:
                continue  # ja comparteixen casella

            if not is_valid_quarter_pair(act_a.group, act_a.subject, act_b.group, act_b.subject):
                continue

            aligned = False

            if act_a.duration == act_b.duration:
                earliest = self._earliest_common_slot_for_pair(act_a, act_b, activities, baseline_keys)
                if earliest is not None:
                    day, start = earliest
                    act_a.day, act_a.start = day, start
                    act_b.day, act_b.start = day, start
                    aligned = True

            if not aligned:
                for first, second in ((act_a, act_b), (act_b, act_a)):
                    original_day, original_start = second.day, second.start
                    second.day, second.start = first.day, first.start

                    candidate_schedule = self._build_schedule(activities)
                    candidate_conflicts = self._scheduler_engine.validate(candidate_schedule)
                    new_keys = [
                        conflict for conflict in candidate_conflicts
                        if self._conflict_key(conflict) not in baseline_keys
                    ]
                    if not new_keys:
                        break

                    second.day, second.start = original_day, original_start

        final_schedule = self._build_schedule(activities)
        final_conflicts = self._scheduler_engine.validate(final_schedule)

        return ScheduleProposal(
            id=proposal.id,
            activities=activities,
            score=proposal.score,
            conflicts=final_conflicts,
            warnings=proposal.warnings,
            score_breakdown=getattr(proposal, "score_breakdown", None),
            metadata=dict(proposal.metadata or {}),
        )

    def _earliest_common_slot_for_pair(
        self,
        act_a: Activity,
        act_b: Activity,
        activities: List[Activity],
        baseline_keys: set,
    ) -> Optional[Tuple[str, str]]:
        """Busca la primera casella comuna on la parella encaixa sense nous conflictes."""
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        if not day_names or not hour_names:
            return None

        original_a = (act_a.day, act_a.start)
        original_b = (act_b.day, act_b.start)
        required_slots = act_a.duration or 1

        for day_index in self._school_calendar.days:
            if day_index >= len(day_names):
                continue
            for slot in self._school_calendar.periods_for_day(day_index):
                if slot.period + required_slots > self._school_calendar.periods_per_day:
                    continue
                if slot.period >= len(hour_names):
                    continue

                day_label = day_names[day_index]
                start_label = hour_names[slot.period]

                if (day_label, start_label) == original_a and (day_label, start_label) == original_b:
                    continue

                act_a.day, act_a.start = day_label, start_label
                act_b.day, act_b.start = day_label, start_label

                candidate_schedule = self._build_schedule(activities)
                candidate_conflicts = self._scheduler_engine.validate(candidate_schedule)
                new_keys = [
                    conflict for conflict in candidate_conflicts
                    if self._conflict_key(conflict) not in baseline_keys
                ]
                if not new_keys:
                    act_a.day, act_a.start = original_a
                    act_b.day, act_b.start = original_b
                    return day_label, start_label

                act_a.day, act_a.start = original_a
                act_b.day, act_b.start = original_b

        return None

    def _build_schedule(self, activities: List[Activity]) -> Schedule:
        schedule = Schedule()
        for activity in activities:
            schedule.add(activity)
        group_restrictions = self._academic_data_repo.active_group_restrictions()
        hour_names = self._time_labels.get("hour_names", [])
        schedule.configuration = {
            "day_names": self._time_labels.get("day_names", []),
            "split_groups": {
                (group.get("name") or "").strip()
                for group in self._academic_data_repo.list_groups()
                if group.get("is_split")
            },
            "group_time_window_constraints": self._build_group_time_window_constraints(group_restrictions, hour_names),
            "group_max_days_constraints": self._build_group_max_days_constraints(group_restrictions),
        }
        return schedule

    def _load_snapshot(self) -> WorkingTimetableSnapshot:
        if self._working_timetable_repo is None:
            return WorkingTimetableSnapshot()
        return self._working_timetable_repo.load_snapshot()

    def _persist_proposal_state(
        self,
        proposal: ScheduleProposal,
        generation_stats: Dict[str, Any] | None,
        unscheduled_activities: List[Dict[str, Any]],
    ) -> None:
        if self._working_timetable_repo is None:
            return

        previous = self._load_snapshot()
        self._working_timetable_repo.save_snapshot(
            WorkingTimetableSnapshot(
                active_schedule=previous.active_schedule,
                current_proposal={
                    "id": proposal.id,
                    "activities": [serialize_activity(activity) for activity in proposal.activities],
                    "score": proposal.score,
                    "warnings": list(proposal.warnings),
                    "conflicts": [serialize_conflict(conflict) for conflict in proposal.conflicts],
                    "metadata": dict(proposal.metadata or {}),
                },
                generation_stats=generation_stats,
                unscheduled_activities=unscheduled_activities,
                metadata={**previous.metadata, "last_source": "proposal"},
            )
        )

    def _collect_blocked_slots(self) -> Dict[tuple[str, str], set]:
        """Retorna un mapa {(\"teacher\"|\"group\", nom): {(day_index, hour_index), ...}}
        combinant restriccions de l'Excel acadèmic."""
        teacher_restrictions = (
            self._academic_data_repo.active_teacher_restrictions() if self._academic_data_repo else []
        )
        group_restrictions = (
            self._academic_data_repo.active_group_restrictions() if self._academic_data_repo else []
        )
        blocked_activities = self._build_blocked_activities_from_restrictions(
            teacher_restrictions, group_restrictions
        )

        blocked: Dict[tuple[str, str], set] = {}
        for blocked_activity in blocked_activities:
            if blocked_activity.teacher_id:
                key = ("teacher", blocked_activity.teacher_id)
            elif blocked_activity.group_id:
                key = ("group", blocked_activity.group_id)
            else:
                continue
            blocked.setdefault(key, set()).add(
                (blocked_activity.day, blocked_activity.start_timeslot.period)
            )
        return blocked

    def _compact_activities(self, activities: List[Activity]) -> tuple[List[Activity], List[int]]:
        """Reubica les activitats de cada grup, dia a dia, el més aviat
        possible dins la jornada per eliminar franges buides entre classes,
        respectant les franges no disponibles de grups i professors."""
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        day_index = {name: index for index, name in enumerate(day_names)}
        hour_index = {name: index for index, name in enumerate(hour_names)}

        blocked_slots = self._collect_blocked_slots()

        by_group_day: Dict[tuple[str, str], List[Activity]] = {}
        untouched: List[Activity] = []

        for activity in activities:
            if activity.group and activity.day in day_index and activity.start in hour_index:
                by_group_day.setdefault((activity.group, activity.day), []).append(activity)
            else:
                untouched.append(activity)

        moved_ids: List[int] = []
        result: List[Activity] = list(untouched)

        for (group, day), group_activities in by_group_day.items():
            day_idx = day_index[day]
            group_blocked = blocked_slots.get(("group", group), set())
            ordered = sorted(group_activities, key=lambda activity: hour_index[activity.start])

            cursor = 0
            position = 0
            while position < len(ordered):
                current = ordered[position]
                same_slot = [current]
                next_position = position + 1
                while (
                    next_position < len(ordered)
                    and hour_index[ordered[next_position].start] == hour_index[current.start]
                ):
                    same_slot.append(ordered[next_position])
                    next_position += 1

                start_idx = cursor
                while (day_idx, start_idx) in group_blocked and start_idx < len(hour_names):
                    start_idx += 1

                if start_idx < len(hour_names):
                    new_start = hour_names[start_idx]
                    for occupant in same_slot:
                        if occupant.start != new_start:
                            occupant.start = new_start
                            moved_ids.append(occupant.id)

                max_duration = max((occupant.duration or 1) for occupant in same_slot)
                cursor = start_idx + max_duration
                position = next_position

            result.extend(ordered)

        return result, moved_ids

    _MORNING_BREAK_GROUPS = {"1r apgi", "2n apgi", "pfi", "1r com", "2n com"}
    _AFTERNOON_BREAK_GROUPS = {"comú", "gp", "gi"}

    def _insert_default_group_breaks(self, activities: List[Activity]) -> List[Activity]:
        """Obre un buit de 30 min (descans flexible) en dies marcats a la
        restricció del grup (`break_days`), desplaçant les classes
        posteriors quan cal. No crea activitats `Descans`."""
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])
        day_index = {name: index for index, name in enumerate(day_names)}
        hour_index = {name: index for index, name in enumerate(hour_names)}
        midday_idx = hour_index.get("14:00")

        by_group_day: Dict[tuple[str, str], List[Activity]] = {}
        for activity in activities:
            if activity.group and activity.day in day_index and activity.start in hour_index:
                by_group_day.setdefault((activity.group, activity.day), []).append(activity)

        exception_slots_by_group: Dict[str, set] = {}
        break_days_by_group: Dict[str, set] = {}
        if self._academic_data_repo is not None:
            for restriction in self._academic_data_repo.list_group_restrictions():
                key = (restriction.get("group") or "").strip().lower()
                exception_slots_by_group[key] = set(restriction.get("exception_slots") or [])
                break_days_by_group[key] = set(restriction.get("break_days") or [])

        for (group, day), group_activities in by_group_day.items():
            group_key = (group or "").strip().lower()
            if day not in break_days_by_group.get(group_key, set()):
                continue

            exceptions = exception_slots_by_group.get(group_key, set())
            # Les classes marcades com a excepció (permeses fora de l'horari
            # habitual del grup) no compten per calcular la franja del dia,
            # perquè no desplacin el descans fora de lloc.
            span_activities = [a for a in group_activities if f"{a.day} {a.start}" not in exceptions]
            if not span_activities:
                continue

            start_indices = [hour_index[a.start] for a in span_activities]
            end_indices = [hour_index[a.start] + (a.duration or 1) for a in span_activities]
            day_start_idx = min(start_indices)
            day_end_idx = max(end_indices)

            window_start_idx = day_start_idx + 2  # 1h després de començar
            window_end_idx = day_end_idx - 3  # 1h30 abans d'acabar

            if midday_idx is not None:
                if group_key in self._MORNING_BREAK_GROUPS:
                    window_end_idx = min(window_end_idx, midday_idx - 1)
                elif group_key in self._AFTERNOON_BREAK_GROUPS:
                    window_start_idx = max(window_start_idx, midday_idx)

            if window_start_idx > window_end_idx or window_start_idx >= len(hour_names):
                continue  # no hi ha prou marge aquell dia

            insertion_idx = window_start_idx

            to_shift = sorted(
                (a for a in group_activities if hour_index[a.start] >= insertion_idx),
                key=lambda a: hour_index[a.start],
                reverse=True,
            )
            if any(hour_index[a.start] + 1 + (a.duration or 1) > len(hour_names) for a in to_shift):
                continue  # desplaçar-les faria sortir del graella; es queda sense descans

            for a in to_shift:
                a.start = hour_names[hour_index[a.start] + 1]

        return activities

    def compact_active_schedule(self) -> Dict[str, Any]:
        """Elimina els forats de l'horari actiu ('sense buits')."""
        current_activities = list(self._scheduler_engine.state.all())
        compacted_activities, moved_ids = self._compact_activities(current_activities)

        candidate_schedule = self._build_schedule(compacted_activities)
        conflicts = self._scheduler_engine.validate(candidate_schedule)
        if conflicts:
            return {
                "ok": False,
                "error": "compaction_conflict",
                "conflicts": serialize_conflicts(conflicts),
            }

        self._scheduler_engine.load(candidate_schedule)
        self._persist_active_schedule(clear_proposal=False)
        return {
            "ok": True,
            "moved": moved_ids,
            "activities": [serialize_activity(activity) for activity in compacted_activities],
            "conflicts": [],
        }

    def compact_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Elimina els forats d'una proposta generada ('sense buits')."""
        proposal = self._proposal_store.get(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")

        compacted_activities, moved_ids = self._compact_activities(list(proposal.activities))
        candidate_schedule = self._build_schedule(compacted_activities)
        conflicts = self._scheduler_engine.validate(candidate_schedule)
        if conflicts:
            return {
                "ok": False,
                "error": "compaction_conflict",
                "conflicts": serialize_conflicts(conflicts),
                "proposal": serialize_proposal(proposal),
            }

        updated_proposal = ScheduleProposal(
            id=proposal.id,
            activities=compacted_activities,
            score=proposal.score,
            conflicts=[],
            warnings=proposal.warnings,
            score_breakdown=getattr(proposal, "score_breakdown", None),
            metadata=dict(proposal.metadata or {}),
        )
        self._proposal_store[proposal_id] = updated_proposal
        self._persist_proposal_state(
            updated_proposal,
            self._load_snapshot().generation_stats,
            list((updated_proposal.metadata or {}).get("unscheduled_activities", [])),
        )
        return {
            "ok": True,
            "moved": moved_ids,
            "proposal": serialize_proposal(updated_proposal),
            "conflicts": [],
        }

    def _persist_active_schedule(self, clear_proposal: bool) -> None:
        if self._working_timetable_repo is None:
            return

        previous = self._load_snapshot()
        self._working_timetable_repo.save_snapshot(
            WorkingTimetableSnapshot(
                active_schedule=[serialize_activity(activity) for activity in self._scheduler_engine.state.all()],
                current_proposal=None if clear_proposal else previous.current_proposal,
                generation_stats=None if clear_proposal else previous.generation_stats,
                unscheduled_activities=[] if clear_proposal else previous.unscheduled_activities,
                metadata={**previous.metadata, "last_source": "active_schedule"},
            )
        )