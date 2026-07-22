from __future__ import annotations

import hashlib
import random
import time
import zlib
from typing import List, Optional, Sequence, Union

try:
    from backend.models.teaching_block import TeachingBlock
    from backend.models.teaching_requirement import TeachingRequirement
    from backend.services.block_generator import BlockGenerator
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
    from models.teaching_requirement import TeachingRequirement
    from services.block_generator import BlockGenerator
from .models import Activity, Conflict, GenerationContext, GenerationResult, ScheduleProposal, ScheduledActivity
from .placement_strategy import GreedyPlacementStrategy, PlacementStrategy
from .proposal_scorer import ProposalScorer


class SchedulerGenerator:
    """A simple, deterministic first-pass scheduler.

    This implementation does not optimize, score, or backtrack. It only places
    teaching blocks into available school slots in a single pass and returns a
    generation result that contains one or more schedule proposals.
    """

    def __init__(self, placement_strategy: Optional[PlacementStrategy] = None, scorer: Optional[ProposalScorer] = None) -> None:
        self._placement_strategy = placement_strategy or GreedyPlacementStrategy()
        self._scorer = scorer or ProposalScorer()

    def generate(
        self,
        teaching_blocks: Union[List[TeachingBlock], List[TeachingRequirement]],
        context: GenerationContext,
        max_proposals: int = 10,
    ) -> GenerationResult:
        started_at = time.perf_counter()
        proposals: List[ScheduleProposal] = []
        warnings: List[dict] = []
        generated_scheduled_activities: List[ScheduledActivity] = []

        if teaching_blocks and isinstance(teaching_blocks[0], TeachingRequirement):
            teaching_blocks = self._build_blocks_from_requirements(teaching_blocks)

        total_blocks = len(teaching_blocks)

        if total_blocks == 0:
            proposal = self._build_proposal([], [], "empty")
            return GenerationResult(
                generated_scheduled_activities=[],
                warnings=[],
                statistics={"blocks_total": 0, "blocks_placed": 0, "blocks_failed": 0, "proposals_generated": 1},
                elapsed_time_ms=0.0,
                proposals=[proposal],
                valid=True,
                schedule_proposal=proposal,
            )

        orderings = self._build_orderings(teaching_blocks, context)
        for ordering in orderings[:max_proposals]:
            scheduled_activities, placement_warnings = self._generate_for_ordering(ordering, context)
            if not scheduled_activities and placement_warnings:
                warnings.extend(placement_warnings)
                continue

            proposal = self._build_proposal(scheduled_activities, placement_warnings, "phase-1", context)
            proposal.conflicts = self._detect_conflicts(proposal)
            breakdown = self._scorer.calculate(proposal, context)
            proposal.score = breakdown.total_score
            proposal.score_breakdown = breakdown
            proposal.metadata = {**(proposal.metadata or {}), "score_breakdown": breakdown}
            proposals.append(proposal)
            warnings.extend(placement_warnings)
            if not generated_scheduled_activities and scheduled_activities:
                generated_scheduled_activities = list(scheduled_activities)

        proposals.sort(key=lambda proposal: proposal.score, reverse=True)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        valid = len(proposals) > 0

        return GenerationResult(
            generated_scheduled_activities=generated_scheduled_activities,
            warnings=warnings,
            statistics={
                "blocks_total": total_blocks,
                "blocks_placed": len(proposals[0].activities) if proposals else 0,
                "blocks_failed": len(warnings),
                "proposals_generated": len(proposals),
            },
            elapsed_time_ms=elapsed_ms,
            proposals=proposals,
            valid=valid,
            schedule_proposal=proposals[0] if proposals else None,
        )

    def _build_blocks_from_requirements(self, requirements: Sequence[TeachingRequirement]) -> List[TeachingBlock]:
        block_generator = BlockGenerator()
        blocks: List[TeachingBlock] = []
        for requirement in requirements:
            distributions = block_generator.generate(requirement)
            if not distributions:
                continue

            # generate() returns every valid way to split the weekly hours
            # across days; only one of them should become real teaching
            # blocks. Distributions are pre-sorted by (fewest days, block
            # sizes), so the first one is the most concentrated valid option.
            distribution = distributions[0]

            for block in distribution:
                blocks.append(
                    TeachingBlock(
                        id=block.id,
                        duration=block.duration,
                        order=block.order,
                        duration_blocks=block.duration_blocks,
                        preferred_room_id=None,
                        preferred_teacher_id=requirement.teacher_id,
                        fixed=False,
                        metadata={
    "requirement_id": requirement.id,

    "group_id": requirement.group_id,
    "subject_id": requirement.subject_id,
    "teacher_id": requirement.teacher_id,

    "group": str(requirement.group_id),
    "subject": str(requirement.subject_id),
    "teacher": str(requirement.teacher_id),
},
                    )
                )
        return blocks

    def _detect_conflicts(self, proposal: ScheduleProposal) -> List[Conflict]:
        conflicts: List[Conflict] = []
        activity_by_key: dict[tuple[str, str, str], Activity] = {}

        for activity in proposal.activities:
            key = (activity.teacher, activity.day, activity.start)
            existing = activity_by_key.get(key)
            if existing is not None:
                conflicts.append(
                    Conflict(
                        type="teacher_conflict",
                        message=f"Teacher {activity.teacher} has overlapping activities",
                        teacher=activity.teacher,
                        day=activity.day,
                        start=activity.start,
                        activities=[existing.id, activity.id],
                    )
                )
            else:
                activity_by_key[key] = activity

        return conflicts

    def _build_orderings(self, teaching_blocks: Sequence[TeachingBlock], context: GenerationContext) -> List[List[TeachingBlock]]:
        blocks = list(teaching_blocks)
        orderings = [blocks[:], list(reversed(blocks))]

        sorted_by_duration_desc = sorted(blocks, key=lambda block: block.duration_blocks or 0, reverse=True)
        sorted_by_duration_asc = sorted(blocks, key=lambda block: block.duration_blocks or 0)
        orderings.extend([sorted_by_duration_desc, sorted_by_duration_asc])

        if context.random_seed is not None:
            rng = random.Random(context.random_seed)
            shuffled = list(blocks)
            rng.shuffle(shuffled)
            orderings.append(shuffled)
        else:
            orderings.append(list(blocks))

        unique_orderings: List[List[TeachingBlock]] = []
        seen = set()
        for ordering in orderings:
            key = tuple(block.id for block in ordering)
            if key not in seen:
                seen.add(key)
                unique_orderings.append(ordering)

        return unique_orderings

    def _generate_for_ordering(
        self,
        ordering: Sequence[TeachingBlock],
        context: GenerationContext,
    ) -> tuple[List[ScheduledActivity], List[dict]]:
        scheduled_activities: List[ScheduledActivity] = []
        warnings: List[dict] = []

        for block in ordering:
            placement = self._placement_strategy.place(
                block,
                context,
                scheduled_activities
            )

            if placement is None:
                metadata = block.metadata or {}

                label_parts = [
                    metadata.get("subject") or "",
                    metadata.get("teacher") or "",
                    metadata.get("group") or "",
                ]

                label = " · ".join(
                    part for part in label_parts if part
                )

                if not label:
                    label = f"bloc {block.id}"

                explain_failure = getattr(self._placement_strategy, "explain_failure", None)
                constraints = explain_failure(block, context, scheduled_activities) if callable(explain_failure) else []
                if not constraints:
                    constraints = ["No s'ha trobat cap franja vàlida per col·locar aquesta activitat."]

                warnings.append(
                    {
                        "id": metadata.get("fet_id", zlib.crc32(str(block.id).encode("utf-8"))),
                        "label": f"No s'ha pogut col·locar {label}",
                        "subject": metadata.get("subject"),
                        "teacher": metadata.get("teacher"),
                        "group": metadata.get("group"),
                        "duration": block.duration_blocks or block.duration,
                        "reason": "No s'ha pogut col·locar.",
                        "constraints": constraints,
                    }
                )

            else:
                scheduled_activities.append(placement)

        return scheduled_activities, warnings
    def _build_proposal(
        self,
        scheduled_activities: Sequence[ScheduledActivity],
        warnings: Sequence[str],
        generator_name: str,
        context: GenerationContext | None = None,
    ) -> ScheduleProposal:
        activities = [
            Activity(
                id=activity.teaching_block.metadata.get("fet_id", index),
                teacher=activity.teacher_id or activity.teaching_block.metadata.get("teacher", ""),
                subject=activity.teaching_block.metadata.get("subject")
                or activity.teaching_block.metadata.get("subject_id")
                or activity.teaching_block.id,
                group=activity.group_id or activity.teaching_block.metadata.get("group", ""),
                room=activity.room_id or activity.teaching_block.metadata.get("room", ""),
                day=f"Day {activity.day}",
                start=f"Period {activity.start_timeslot.period}",
                duration=activity.duration,
            )
            for index, activity in enumerate(scheduled_activities, start=1)
        ]

        proposal_id = self._proposal_id(generator_name, scheduled_activities)
        return ScheduleProposal(
            id=proposal_id,
            activities=activities,
            warnings=list(warnings),
            metadata={"generator": generator_name, "scheduled_activities": list(scheduled_activities)},
        )

    def _proposal_id(self, generator_name: str, scheduled_activities: Sequence[ScheduledActivity]) -> str:
        signature = "|".join(
            f"{activity.teaching_block.id}:{activity.day}:{activity.start_timeslot.period}:{activity.duration}"
            for activity in scheduled_activities
        )
        digest = hashlib.sha1(f"{generator_name}|{signature}".encode("utf-8")).hexdigest()[:12]
        return f"proposal-{digest}"
