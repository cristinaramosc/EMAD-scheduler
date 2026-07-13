from __future__ import annotations

from typing import Any, Dict, List

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

    def __init__(
        self,
        requirement_repo: Any,
        scheduler_engine: SchedulerEngine,
        proposal_store: Dict[str, ScheduleProposal],
        school_calendar: SchoolCalendar | None = None,
        time_labels: Dict[str, List[str]] | None = None,
        fet_generation_inputs_fn: Any | None = None,
        fet_file: Any | None = None,
        academic_data_repo: AcademicDataRepository | None = None,
        working_timetable_repo: WorkingTimetableRepository | None = None,
    ) -> None:
        self._requirement_repo = requirement_repo
        self._scheduler_engine = scheduler_engine
        self._proposal_store = proposal_store
        self._school_calendar = school_calendar or SchoolCalendar()
        self._time_labels = time_labels or {"day_names": [], "hour_names": []}
        self._fet_generation_inputs_fn = fet_generation_inputs_fn
        self._fet_file = fet_file
        self._academic_data_repo = academic_data_repo
        self._working_timetable_repo = working_timetable_repo

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
            return self.generate_proposals_from_fet()

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
            return self.generate_proposals_from_fet()

        assignments = self._academic_data_repo.active_teaching_assignments()
        if not assignments:
            return self.generate_proposals_from_fet()

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

        requirements = [self._build_requirement_from_assignment(index, assignment) for index, assignment in enumerate(flexible_assignments, start=1)]
        blocked_activities = self._build_blocked_activities_from_restrictions(
            self._academic_data_repo.active_teacher_restrictions(),
            self._academic_data_repo.active_group_restrictions(),
        )
        blocked_activities += self._load_fet_blocked_activities()
        blocked_activities += fixed_scheduled_activities

        context = GenerationContext(
            school_calendar=self._school_calendar,
            existing_scheduled_activities=tuple(blocked_activities),
            fixed_activities=tuple(fixed_scheduled_activities),
            blocked_time_slots=(),
            configuration={
                "room_constraints_enabled": True,
                "day_names": day_names,
                "hour_names": hour_names,
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
        proposals.sort(key=lambda proposal: proposal.score, reverse=True)

        for proposal in proposals:
            self._proposal_store[proposal.id] = proposal

        best_proposal = proposals[0]
        self._persist_proposal_state(
            best_proposal,
            {
                **generation_result.statistics,
                "source": "academic_workbook",
                "fixed_activities_total": len(fixed_activities),
            },
            [],
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
            "unscheduled_activities": [],
        }

    def generate_proposals_from_fet(self) -> Dict[str, Any]:
        if self._fet_generation_inputs_fn is None or self._fet_file is None:
            raise ValueError("missing_requirement_ids")

        payload = self._fet_generation_inputs_fn(self._fet_file)
        context = GenerationContext(
            school_calendar=payload["school_calendar"],
            existing_scheduled_activities=tuple(payload["blocked_activities"]),
            fixed_activities=tuple(payload["fixed_activities"]),
            blocked_time_slots=(),
            configuration={
                "room_constraints_enabled": True,
                "day_names": payload["day_names"],
                "hour_names": payload["hour_names"],
            },
        )
        generator = SchedulerGenerator()
        generation_result = generator.generate(payload["floating_blocks"], context)

        if not generation_result.valid or not generation_result.proposals:
            raise RuntimeError("generation_failed")

        fixed_activities = [self._scheduled_to_activity(activity, payload["day_names"], payload["hour_names"]) for activity in payload["fixed_activities"]]
        proposals = [
            self._merge_fixed_activities_into_proposal(
                proposal,
                payload,
                fixed_activities,
                payload["day_names"],
                payload["hour_names"],
            )
            for proposal in generation_result.proposals
        ]
        proposals.sort(key=lambda proposal: proposal.score, reverse=True)

        for proposal in proposals:
            self._proposal_store[proposal.id] = proposal

        best_proposal = proposals[0]
        unscheduled_activities = list((best_proposal.metadata or {}).get("unscheduled_activities", []))
        self._persist_proposal_state(
            best_proposal,
            {
                **generation_result.statistics,
                "fixed_activities_total": len(fixed_activities),
                "floating_activities_total": len(payload["floating_blocks"]),
                "unscheduled_activities_total": len(unscheduled_activities),
            },
            unscheduled_activities,
        )
        return {
            "valid": True,
            "best_proposal": serialize_proposal(best_proposal),
            "proposals": [serialize_proposal(proposal) for proposal in proposals],
            "scores": [proposal.score for proposal in proposals],
            "conflicts": [[serialize_conflict(conflict) for conflict in proposal.conflicts] for proposal in proposals],
            "statistics": {
                **generation_result.statistics,
                "fixed_activities_total": len(fixed_activities),
                "floating_activities_total": len(payload["floating_blocks"]),
                "unscheduled_activities_total": len(unscheduled_activities),
            },
            "unscheduled_activities": unscheduled_activities,
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

    def move_proposal_activity(self, proposal_id: str, activity_id: int, day: str, start: str) -> Dict[str, Any]:
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
            )
            for activity in proposal.activities
        ]
        unscheduled = list((proposal.metadata or {}).get("unscheduled_activities", []))
        target = next((activity for activity in current_activities if activity.id == activity_id), None)

        baseline_schedule = self._build_schedule(current_activities)
        baseline_conflicts = self._scheduler_engine.validate(baseline_schedule)
        baseline_keys = {self._conflict_key(conflict) for conflict in baseline_conflicts}

        if target is None:
            pending = next((activity for activity in unscheduled if activity["id"] == activity_id), None)
            if pending is None:
                raise LookupError("proposal_activity_not_found")
            target = Activity(
                id=pending["id"],
                teacher=pending.get("teacher", ""),
                subject=pending.get("subject", ""),
                group=pending.get("group", ""),
                room=pending.get("room", ""),
                day=day,
                start=start,
                duration=pending.get("duration", 1),
            )
            current_activities.append(target)
        else:
            target.day = day
            target.start = start

        candidate_schedule = self._build_schedule(current_activities)
        conflicts = self._scheduler_engine.validate(candidate_schedule)
        new_conflicts = [conflict for conflict in conflicts if self._conflict_key(conflict) not in baseline_keys]
        if new_conflicts:
            return {
                "ok": False,
                "error": "validation_failed",
                "conflicts": serialize_conflicts(new_conflicts),
                "proposal": serialize_proposal(proposal),
                "unscheduled_activities": unscheduled,
            }

        remaining_unscheduled = [activity for activity in unscheduled if activity["id"] != activity_id]
        updated_metadata = dict(proposal.metadata or {})
        updated_metadata["unscheduled_activities"] = remaining_unscheduled
        updated_proposal = ScheduleProposal(
            id=proposal.id,
            activities=current_activities,
            score=proposal.score,
            conflicts=[],
            warnings=proposal.warnings,
            score_breakdown=proposal.score_breakdown,
            metadata=updated_metadata,
        )
        self._proposal_store[proposal_id] = updated_proposal
        self._persist_proposal_state(updated_proposal, self._load_snapshot().generation_stats, remaining_unscheduled)
        return {
            "ok": True,
            "proposal": serialize_proposal(updated_proposal),
            "conflicts": [],
            "unscheduled_activities": remaining_unscheduled,
        }

    def _scheduled_to_activity(
        self,
        scheduled_activity: Any,
        day_names: List[str],
        hour_names: List[str],
    ) -> Activity:
        metadata = scheduled_activity.teaching_block.metadata or {}
        return Activity(
            id=metadata.get("fet_id", hash((scheduled_activity.teaching_block.id, scheduled_activity.day, scheduled_activity.start_timeslot.period))),
            teacher=scheduled_activity.teacher_id or metadata.get("teacher", ""),
            subject=metadata.get("subject") or metadata.get("subject_id") or scheduled_activity.teaching_block.id,
            group=scheduled_activity.group_id or metadata.get("group", ""),
            room=scheduled_activity.room_id or metadata.get("room", ""),
            day=day_names[scheduled_activity.day] if scheduled_activity.day < len(day_names) else f"Day {scheduled_activity.day}",
            start=hour_names[scheduled_activity.start_timeslot.period]
            if scheduled_activity.start_timeslot.period < len(hour_names)
            else f"Period {scheduled_activity.start_timeslot.period}",
            duration=scheduled_activity.duration,
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

    def _build_requirement_from_assignment(self, index: int, assignment: Dict[str, Any]) -> TeachingRequirement:
        preferred_room = assignment.get("preferred_room", "")
        session_hours = float(assignment["weekly_hours"])
        return TeachingRequirement(
            id=f"academic-{index}",
            group_id=str(assignment["group"]),
            subject_id=str(assignment["subject"]),
            teacher_id=str(assignment["teacher"]),
            weekly_hours=session_hours,
            min_days=1,
            max_days=1,
            min_block_duration=session_hours,
            max_consecutive_hours=max(session_hours, 2.0),
            allow_half_hour_blocks=True,
            preferred_rooms=[preferred_room] if preferred_room else [],
            fixed_teacher=True,
            priority=2,
        )

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

        for record in teacher_restrictions:
            teacher = record.get("teacher", "")
            for slot in record.get("unavailable_slots", []):
                indexes = self._slot_to_indexes(slot, day_indexes, hour_indexes)
                if indexes is None:
                    continue
                day_index, hour_index = indexes
                blocked.append(
                    ScheduledActivity(
                        teaching_block=TeachingBlock(
                            id=f"teacher-blocked-{teacher}-{day_index}-{hour_index}",
                            duration=0.5,
                            order=0,
                            duration_blocks=1,
                            preferred_teacher_id=teacher,
                            metadata={"synthetic": True, "constraint": "teacher_not_available"},
                        ),
                        day=day_index,
                        start_timeslot=TimeSlot(day=day_index, period=hour_index),
                        duration=1,
                        teacher_id=teacher,
                        metadata={"synthetic": True, "constraint": "teacher_not_available"},
                    )
                )

        for record in group_restrictions:
            group = record.get("group", "")
            slots = list(record.get("unavailable_slots", [])) + list(record.get("fixed_slots", []))
            for slot in slots:
                indexes = self._slot_to_indexes(slot, day_indexes, hour_indexes)
                if indexes is None:
                    continue
                day_index, hour_index = indexes
                blocked.append(
                    ScheduledActivity(
                        teaching_block=TeachingBlock(
                            id=f"group-blocked-{group}-{day_index}-{hour_index}",
                            duration=0.5,
                            order=0,
                            duration_blocks=1,
                            metadata={"synthetic": True, "constraint": "group_not_available"},
                        ),
                        day=day_index,
                        start_timeslot=TimeSlot(day=day_index, period=hour_index),
                        duration=1,
                        group_id=group,
                        metadata={"synthetic": True, "constraint": "group_not_available"},
                    )
                )

        return blocked

    def _slot_to_indexes(
        self,
        slot: str,
        day_indexes: Dict[str, int],
        hour_indexes: Dict[str, int],
    ) -> tuple[int, int] | None:
        token = str(slot).strip()
        if not token:
            return None

        parts = token.rsplit(" ", 1)
        if len(parts) != 2:
            return None

        day, hour = parts
        if day not in day_indexes or hour not in hour_indexes:
            return None

        return day_indexes[day], hour_indexes[hour]

    def _build_schedule(self, activities: List[Activity]) -> Schedule:
        schedule = Schedule()
        for activity in activities:
            schedule.add(activity)
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

    def get_fet_restrictions(self) -> Dict[str, Dict[str, List[str]]]:
        """Retorna les franges no disponibles definides al fitxer FET
        (ConstraintTeacherNotAvailableTimes / ConstraintStudentsSetNotAvailableTimes),
        convertides al format "Dia Hora" i agrupades per professor i per grup,
        perquè el frontend les pugui mostrar marcades encara que no s'hagin
        desat manualment a l'Excel/panell de restriccions."""
        day_names = self._time_labels.get("day_names", [])
        hour_names = self._time_labels.get("hour_names", [])

        teachers: Dict[str, List[str]] = {}
        groups: Dict[str, List[str]] = {}

        for blocked in self._load_fet_blocked_activities():
            day_idx = blocked.start_timeslot.day
            hour_idx = blocked.start_timeslot.period
            if day_idx >= len(day_names) or hour_idx >= len(hour_names):
                continue
            slot = f"{day_names[day_idx]} {hour_names[hour_idx]}"

            if blocked.teacher_id:
                bucket = teachers.setdefault(blocked.teacher_id, [])
                if slot not in bucket:
                    bucket.append(slot)
            elif blocked.group_id:
                bucket = groups.setdefault(blocked.group_id, [])
                if slot not in bucket:
                    bucket.append(slot)

        return {"teachers": teachers, "groups": groups}

    def _load_fet_blocked_activities(self) -> List[ScheduledActivity]:
        """Llegeix directament del fitxer FET les franges no disponibles de
        professors i grups (ConstraintTeacherNotAvailableTimes /
        ConstraintStudentsSetNotAvailableTimes) i les retorna com a activitats
        bloquejades, perquè es respectin també quan la generació parteix de
        les dades acadèmiques (Excel) i no directament del FET."""
        if self._fet_generation_inputs_fn is None or self._fet_file is None:
            return []
        try:
            payload = self._fet_generation_inputs_fn(self._fet_file)
        except Exception:
            return []
        return list(payload.get("blocked_activities", []))

    def _collect_blocked_slots(self) -> Dict[tuple[str, str], set]:
        """Retorna un mapa {(\"teacher\"|\"group\", nom): {(day_index, hour_index), ...}}
        combinant restriccions de l'Excel acadèmic i del fitxer FET."""
        teacher_restrictions = (
            self._academic_data_repo.active_teacher_restrictions() if self._academic_data_repo else []
        )
        group_restrictions = (
            self._academic_data_repo.active_group_restrictions() if self._academic_data_repo else []
        )
        blocked_activities = self._build_blocked_activities_from_restrictions(
            teacher_restrictions, group_restrictions
        )
        blocked_activities += self._load_fet_blocked_activities()

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