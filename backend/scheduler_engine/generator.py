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
from .models import Activity, Conflict, GenerationContext, GenerationResult, ScheduleProposal, ScheduledActivity, TimeSlot
from .placement_strategy import GreedyPlacementStrategy, PlacementStrategy
from .quarter_utils import group_names, parent_and_quarter, quarter_suffix
from .teacher_utils import teacher_label, teacher_names
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
            teaching_blocks = sorted(teaching_blocks, key=lambda requirement: requirement.priority)
            teaching_blocks = self._build_blocks_from_requirements(teaching_blocks, context)

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
            scheduled_activities = self._balance_group_days(scheduled_activities, context)
            scheduled_activities = self._arrange_quarter_activities(scheduled_activities, context)
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
            if not generated_scheduled_activities and scheduled_activities:
                generated_scheduled_activities = list(scheduled_activities)

        proposals.sort(key=lambda proposal: (len(proposal.warnings), -proposal.score))
        result_warnings = proposals[0].warnings if proposals else warnings
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        valid = len(proposals) > 0

        return GenerationResult(
            generated_scheduled_activities=generated_scheduled_activities,
            warnings=result_warnings,
            statistics={
                "blocks_total": total_blocks,
                "blocks_placed": len(proposals[0].activities) if proposals else 0,
                "blocks_failed": len(result_warnings),
                "proposals_generated": len(proposals),
            },
            elapsed_time_ms=elapsed_ms,
            proposals=proposals,
            valid=valid,
            schedule_proposal=proposals[0] if proposals else None,
        )

    def _order_distributions_by_preference(self, distributions: Sequence[List]) -> List[List]:
        """Ordena les distribucions possibles evitant concentrar totes les
        hores en un únic bloc quan hi ha flexibilitat de dies: prioritza
        primer les distribucions amb més d'un bloc, després les més
        equilibrades (menys diferència entre el bloc més gran i el més
        petit), i deixa el bloc únic com a últim recurs."""

        def sort_key(distribution):
            sizes = [block.duration_blocks for block in distribution]
            is_single_block = 1 if len(sizes) == 1 else 0
            spread = max(sizes) - min(sizes) if len(sizes) > 1 else 0
            return (is_single_block, spread, len(sizes))

        return sorted(distributions, key=sort_key)

    def _widest_balanced_distribution(self, distributions: Sequence[List]) -> List:
        """Tria la distribució que fa servir MÉS dies (el màxim permès per la
        restricció "Màx. dies per repartir") i, entre aquestes, la més
        equilibrada — per tant, amb les sessions més curtes.

        S'usa només com a últim recurs, quan cap distribució no s'ha pogut
        col·locar sencera: amb sessions petites hi ha moltes més
        possibilitats de col·locar-les que amb un bloc únic gegant.
        """

        def sizes(distribution):
            return [block.duration_blocks for block in distribution]

        widest = max(len(distribution) for distribution in distributions)
        candidates = [distribution for distribution in distributions if len(distribution) == widest]
        return min(candidates, key=lambda distribution: (max(sizes(distribution)) - min(sizes(distribution)), sizes(distribution)))

    def _build_blocks_from_requirements(
        self, requirements: Sequence[TeachingRequirement], context: Optional[GenerationContext] = None
    ) -> List[TeachingBlock]:
        block_generator = BlockGenerator()
        blocks: List[TeachingBlock] = []
        # Activitats ja "compromeses" per requeriments anteriors d'aquesta
        # mateixa crida, per poder comprovar si una distribució concreta
        # realment té lloc a l'horari abans de triar-la.
        tentative_scheduled: List[ScheduledActivity] = []

        for requirement in requirements:
            distributions = block_generator.generate(requirement)
            if not distributions:
                continue

            metadata = {
                "requirement_id": requirement.id,
                "max_distribution_days": requirement.max_distribution_days,
                "priority": requirement.priority,
                "group_id": requirement.group_id,
                "subject_id": requirement.subject_id,
                "teacher_id": requirement.teacher_id,
                "group": str(requirement.group_id),
                "subject": str(requirement.subject_id),
                "teacher": teacher_label(requirement.teacher_id),
            }

            chosen_teaching_blocks: Optional[List[TeachingBlock]] = None

            if context is not None:
                # Prova cada distribució candidata (les més equilibrades
                # primer, el bloc únic com a últim recurs) contra el
                # calendari/restriccions reals, i es queda amb la primera
                # que aconsegueix col·locar-se sencera.
                for distribution in self._order_distributions_by_preference(distributions):
                    candidate_teaching_blocks = [
                        TeachingBlock(
                            id=block.id,
                            duration=block.duration,
                            order=block.order,
                            duration_blocks=block.duration_blocks,
                            preferred_room_id=(requirement.preferred_rooms[0] if requirement.preferred_rooms else None),
                            preferred_teacher_id=requirement.teacher_id,
                            fixed=bool(requirement.fixed_day and requirement.fixed_start),
                            fixed_day=requirement.fixed_day,
                            fixed_start=requirement.fixed_start,
                            metadata=metadata,
                        )
                        for block in distribution
                    ]

                    trial_scheduled = list(tentative_scheduled)
                    all_placed = True
                    # Quan una assignatura es reparteix en més d'un bloc (p.ex.
                    # "Màx. dies per repartir" = 2), cada bloc germà ha d'anar a
                    # un dia diferent dels seus germans: si no, els dos blocs
                    # acaben consecutius el mateix dia i la restricció de repartir
                    # en dies diferents queda sense efecte.
                    distribution_used_days: set = set()
                    for teaching_block in candidate_teaching_blocks:
                        excluded_days = distribution_used_days if len(candidate_teaching_blocks) > 1 else None
                        if excluded_days:
                            placement = self._placement_strategy.place(
                                teaching_block,
                                context,
                                trial_scheduled,
                                excluded_days=excluded_days,
                            )
                        else:
                            placement = self._placement_strategy.place(
                                teaching_block,
                                context,
                                trial_scheduled,
                            )
                        if placement is None:
                            all_placed = False
                            break
                        trial_scheduled.append(placement)
                        distribution_used_days.add(placement.day)

                    if all_placed:
                        chosen_teaching_blocks = candidate_teaching_blocks
                        tentative_scheduled = trial_scheduled
                        break

            if chosen_teaching_blocks is None:
                # Cap distribució s'ha pogut col·locar sencera (o no hi ha
                # context per provar-ho). Si l'assignació admet repartir-se
                # en més d'un dia ("Màx. dies per repartir" > 1), NO es cau
                # al bloc únic: es manté la distribució més repartida
                # permesa, perquè el generador principal pugui col·locar
                # cada sessió pel seu compte. Exemple real: el Taller de
                # 2n COM són 10h amb màxim 3 dies; amb la distribució
                # concentrada (un sol bloc de 10h) era impossible de
                # col·locar, i amb 3 sessions de 3,5h/3,5h/3h sí que s'hi
                # reparteix. Si només admet un dia, el bloc únic és l'única
                # opció i es manté el comportament anterior.
                fallback_distribution = (
                    self._widest_balanced_distribution(distributions)
                    if int(requirement.max_distribution_days or 1) > 1
                    else distributions[0]
                )
                chosen_teaching_blocks = [
                    TeachingBlock(
                        id=block.id,
                        duration=block.duration,
                        order=block.order,
                        duration_blocks=block.duration_blocks,
                        preferred_room_id=(requirement.preferred_rooms[0] if requirement.preferred_rooms else None),
                        preferred_teacher_id=requirement.teacher_id,
                        fixed=bool(requirement.fixed_day and requirement.fixed_start),
                        fixed_day=requirement.fixed_day,
                        fixed_start=requirement.fixed_start,
                        metadata=metadata,
                    )
                    for block in fallback_distribution
                ]

            blocks.extend(chosen_teaching_blocks)
        return blocks

    def _detect_conflicts(self, proposal: ScheduleProposal) -> List[Conflict]:
        conflicts: List[Conflict] = []
        activity_by_key: dict[tuple[str, str, str], Activity] = {}

        for activity in proposal.activities:
            teacher_ids = teacher_names(activity.teacher)
            conflict_found = None
            for teacher_id in teacher_ids:
                key = (teacher_id, activity.day, activity.start)
                existing = activity_by_key.get(key)
                if existing is not None and existing.id != activity.id:
                    conflict_found = existing
                    break

            if conflict_found is not None:
                conflicts.append(
                    Conflict(
                        type="teacher_conflict",
                        message=f"Teacher {teacher_label(activity.teacher)} has overlapping activities",
                        teacher=teacher_label(activity.teacher),
                        day=activity.day,
                        start=activity.start,
                        activities=[conflict_found.id, activity.id],
                    )
                )
                continue

            for teacher_id in teacher_ids:
                key = (teacher_id, activity.day, activity.start)
                activity_by_key[key] = activity

        return conflicts

    def _try_local_reorganization(
        self,
        teaching_block: TeachingBlock,
        context: GenerationContext,
        scheduled_activities: List[ScheduledActivity],
    ) -> Optional[ScheduledActivity]:
        """Move one flexible block aside to make room for a constrained one."""
        for index, displaced in enumerate(list(scheduled_activities)):
            if displaced.teaching_block.fixed:
                continue
            if not self._blocks_share_scheduling_resource(teaching_block, displaced, context):
                continue

            remaining = scheduled_activities[:index] + scheduled_activities[index + 1 :]
            replacement = self._placement_strategy.place(teaching_block, context, remaining)
            if replacement is None:
                continue

            displaced_replacement = self._placement_strategy.place(
                displaced.teaching_block,
                context,
                remaining + [replacement],
            )
            if displaced_replacement is None:
                continue

            scheduled_activities[:] = remaining + [displaced_replacement]
            return replacement

        return None

    @staticmethod
    def _blocks_share_scheduling_resource(
        candidate: TeachingBlock,
        scheduled: ScheduledActivity,
        context: GenerationContext,
    ) -> bool:
        candidate_metadata = candidate.metadata or {}
        scheduled_block = scheduled.teaching_block
        scheduled_metadata = scheduled_block.metadata or {}

        candidate_group = candidate_metadata.get("group_id") or candidate_metadata.get("group")
        scheduled_group = scheduled.group_id or scheduled_metadata.get("group_id") or scheduled_metadata.get("group")
        if candidate_group and scheduled_group:
            candidate_parent, _ = parent_and_quarter(candidate_group, candidate_metadata.get("subject"))
            scheduled_parent, _ = parent_and_quarter(scheduled_group, scheduled_metadata.get("subject"))
            if set(group_names(candidate_parent)) & set(group_names(scheduled_parent)):
                return True

        candidate_teachers = set(teacher_names(candidate.preferred_teacher_id or candidate_metadata.get("teacher")))
        scheduled_teachers = set(teacher_names(scheduled.teacher_id or scheduled_block.preferred_teacher_id or scheduled_metadata.get("teacher")))
        if candidate_teachers & scheduled_teachers:
            return True

        if context.configuration.get("room_constraints_enabled", False):
            candidate_room = candidate.preferred_room_id
            scheduled_room = scheduled.room_id or scheduled_block.preferred_room_id
            if candidate_room and candidate_room == scheduled_room:
                return True

        return False

    def _fixed_day_first(self, blocks: Sequence[TeachingBlock]) -> List[TeachingBlock]:
        """Manté l'ordre relatiu de cada llista (sort estable) però posa
        primer els blocs amb dia fix, perquè el motor els col·loqui abans
        que les activitats flexibles puguin ocupar-los la franja, i després
        els de prioritat 1 (aula assignada, professor amb màxim de dies,
        restriccions), perquè cap ordenació els relegui al final."""
        return sorted(
            blocks,
            key=lambda block: (
                0 if getattr(block, "fixed", False) else 1,
                int((block.metadata or {}).get("priority") or 2),
            ),
        )

    def _quarter_pair_anchor_key(self, block: TeachingBlock) -> tuple:
        """Clau d'ordenació que posa primer els blocs 1Q/2Q que afecten més
        d'un grup (p.ex. 'GI, GP'), perquè ancoren la franja comuna de la
        parella, i després ordena els blocs per durada descendent."""
        metadata = block.metadata or {}
        subject = metadata.get("subject")
        group = metadata.get("group") or metadata.get("group_id")
        is_combined_quarter = quarter_suffix(subject) is not None and len(group_names(group)) > 1
        return (0 if is_combined_quarter else 1, -(block.duration_blocks or 0))

    def _build_orderings(self, teaching_blocks: Sequence[TeachingBlock], context: GenerationContext) -> List[List[TeachingBlock]]:
        blocks = list(teaching_blocks)
        orderings = [self._fixed_day_first(blocks), self._fixed_day_first(list(reversed(blocks)))]

        sorted_by_duration_desc = sorted(blocks, key=lambda block: block.duration_blocks or 0, reverse=True)
        sorted_by_duration_asc = sorted(blocks, key=lambda block: block.duration_blocks or 0)
        orderings.extend([self._fixed_day_first(sorted_by_duration_desc), self._fixed_day_first(sorted_by_duration_asc)])

        # Nova ordenació: primer els blocs 1Q/2Q que afecten MÉS d'un grup
        # (p.ex. "Ll. Tec. Audio UF3 2Q" a "GI, GP"). Són els més restringits
        # (necessiten tots els seus grups lliures alhora) i així ancoren una
        # franja comuna; la seva parella 1Q/2Q d'un sol grup s'hi acaba
        # enganxant (via `_try_quarter_pair_slot`). La resta, dels blocs més
        # llargs als més curts, per encabir primer les peces més difícils.
        orderings.append(
            self._fixed_day_first(sorted(blocks, key=self._quarter_pair_anchor_key))
        )

        if context.random_seed is not None:
            rng = random.Random(context.random_seed)
            shuffled = list(blocks)
            rng.shuffle(shuffled)
            orderings.append(self._fixed_day_first(shuffled))
        else:
            orderings.append(self._fixed_day_first(list(blocks)))

        unique_orderings: List[List[TeachingBlock]] = []
        seen = set()
        for ordering in orderings:
            key = tuple(block.id for block in ordering)
            if key not in seen:
                seen.add(key)
                unique_orderings.append(ordering)

        return unique_orderings

    _BALANCE_MAX_MOVES = 40
    _BALANCE_MIN_DIFFERENCE_SLOTS = 2  # no toquem grups amb menys d'1 h de diferència

    @staticmethod
    def _group_day_intervals(activities: Sequence[ScheduledActivity]) -> dict:
        """{grup: {dia: [(inici, fi), ...]}} (els grups combinats compten per a
        cadascun dels grups implicats)."""
        by_group: dict = {}
        for activity in activities:
            interval = (activity.start_timeslot.period, activity.start_timeslot.period + activity.duration)
            for group in group_names(activity.group_id):
                by_group.setdefault(group, {}).setdefault(activity.day, []).append(interval)
        return by_group

    @staticmethod
    def _occupied_slots(intervals: Sequence[tuple]) -> int:
        occupied = set()
        for start, end in intervals:
            occupied.update(range(start, end))
        return len(occupied)

    def _group_imbalance(self, activities: Sequence[ScheduledActivity]) -> int:
        """Suma, per grup, de la diferència (en franges) entre el dia més
        carregat i el menys carregat. Les parelles 1Q/2Q a la mateixa franja
        compten un sol cop."""
        total = 0
        for per_day in self._group_day_intervals(activities).values():
            loads = [self._occupied_slots(intervals) for intervals in per_day.values()]
            if len(loads) > 1:
                total += max(loads) - min(loads)
        return total

    @staticmethod
    def _teacher_gap_slots_total(activities: Sequence[ScheduledActivity]) -> int:
        by_teacher_day: dict = {}
        for activity in activities:
            interval = (activity.start_timeslot.period, activity.start_timeslot.period + activity.duration)
            for teacher in teacher_names(activity.teacher_id):
                by_teacher_day.setdefault((teacher.casefold(), activity.day), []).append(interval)
        total = 0
        for intervals in by_teacher_day.values():
            merged: list = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            total += sum(merged[i][0] - merged[i - 1][1] for i in range(1, len(merged)))
        return total

    def _group_gap_slots_total(self, activities: Sequence[ScheduledActivity]) -> int:
        """Franges buides dins de l'horari dels grups (entre primera i última
        classe de cada dia)."""
        total = 0
        for per_day in self._group_day_intervals(activities).values():
            for intervals in per_day.values():
                merged: list = []
                for start, end in sorted(intervals):
                    if merged and start <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                    else:
                        merged.append((start, end))
                total += sum(merged[i][0] - merged[i - 1][1] for i in range(1, len(merged)))
        return total

    def _is_balance_movable(self, activity: ScheduledActivity, group: str, activities: Sequence[ScheduledActivity]) -> bool:
        block = activity.teaching_block
        if getattr(block, "fixed", False) or getattr(block, "fixed_day", None):
            return False
        subject = (block.metadata or {}).get("subject")
        _, quarter = parent_and_quarter(activity.group_id, subject)
        if quarter is not None:
            return False  # les parelles 1Q/2Q no es toquen
        start = activity.start_timeslot.period
        end = start + activity.duration
        same_group_day = [
            other for other in activities
            if other is not activity
            and other.day == activity.day
            and group in group_names(other.group_id)
        ]
        # Cap altra activitat del grup a la mateixa franja (parella alineada).
        if any(
            other.start_timeslot.period < end and start < other.start_timeslot.period + other.duration
            for other in same_group_day
        ):
            return False
        # Només es mouen classes de l'extrem del dia, perquè no hi quedi un forat.
        day_start = min([start] + [other.start_timeslot.period for other in same_group_day])
        day_end = max([end] + [other.start_timeslot.period + other.duration for other in same_group_day])
        return start == day_start or end == day_end

    def _balance_group_days(
        self,
        activities: List[ScheduledActivity],
        context: GenerationContext,
    ) -> List[ScheduledActivity]:
        """Millora, després de col·locar, l'equilibri d'hores entre els dies de
        cada grup: prova de moure classes soltes del dia més carregat a un
        altre dia, però només si la col·locació passa per les MATEIXES
        restriccions que la col·locació normal (`place`) i el resultat no
        empitjora els forats dels professors. Cada moviment redueix
        estrictament el desequilibri, per tant sempre acaba."""
        if not context.configuration.get("balance_group_days", True) or not activities:
            return activities

        days = list(context.school_calendar.days)
        activities = list(activities)

        for _ in range(self._BALANCE_MAX_MOVES):
            imbalance_before = self._group_imbalance(activities)
            teacher_gaps_before = self._teacher_gap_slots_total(activities)
            group_gaps_before = self._group_gap_slots_total(activities)
            moved = False

            loads = {
                group: {day: self._occupied_slots(intervals) for day, intervals in per_day.items()}
                for group, per_day in self._group_day_intervals(activities).items()
            }
            ordered_groups = sorted(
                (group for group, per_day in loads.items() if len(per_day) > 1),
                key=lambda group: -(max(loads[group].values()) - min(loads[group].values())),
            )

            for group in ordered_groups:
                per_day = loads[group]
                if max(per_day.values()) - min(per_day.values()) < self._BALANCE_MIN_DIFFERENCE_SLOTS:
                    break
                heavy_day = max(per_day, key=per_day.get)
                candidates = [
                    activity for activity in activities
                    if activity.day == heavy_day
                    and group in group_names(activity.group_id)
                    and self._is_balance_movable(activity, group, activities)
                ]
                candidates.sort(key=lambda activity: activity.duration)

                for activity in candidates:
                    others = [other for other in activities if other is not activity]
                    requirement_id = (activity.teaching_block.metadata or {}).get("requirement_id")
                    sibling_days = {
                        other.day for other in others
                        if requirement_id and (other.teaching_block.metadata or {}).get("requirement_id") == requirement_id
                    }
                    for target_day in sorted(days, key=lambda day: per_day.get(day, 0)):
                        if target_day == heavy_day or target_day in sibling_days:
                            continue
                        if per_day.get(target_day, 0) + activity.duration >= per_day[heavy_day]:
                            continue  # no milloraria l'equilibri d'aquest grup
                        placement = self._placement_strategy.place(
                            activity.teaching_block,
                            context,
                            others,
                            excluded_days=set(days) - {target_day},
                        )
                        if placement is None or placement.day != target_day:
                            continue
                        trial = others + [placement]
                        if (
                            self._group_imbalance(trial) < imbalance_before
                            and self._teacher_gap_slots_total(trial) <= teacher_gaps_before
                            and self._group_gap_slots_total(trial) <= group_gaps_before
                        ):
                            activities = trial
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break

            if not moved:
                break

        return activities

    _QUARTER_MAX_MOVES = 30

    @staticmethod
    def _quarter_of(activity: ScheduledActivity) -> Optional[str]:
        subject = (activity.teaching_block.metadata or {}).get("subject")
        return parent_and_quarter(activity.group_id, subject)[1]

    @staticmethod
    def _parent_group_set(activity: ScheduledActivity) -> set:
        subject = (activity.teaching_block.metadata or {}).get("subject")
        parent = parent_and_quarter(activity.group_id, subject)[0]
        return set(group_names(parent)) or {parent}

    def _is_lone_quarter(self, activity: ScheduledActivity, activities: Sequence[ScheduledActivity]) -> bool:
        quarter = self._quarter_of(activity)
        if quarter is None:
            return False
        start = activity.start_timeslot.period
        end = start + activity.duration
        parents = self._parent_group_set(activity)
        for other in activities:
            if other is activity or other.day != activity.day:
                continue
            other_quarter = self._quarter_of(other)
            if other_quarter is None or other_quarter == quarter:
                continue
            if not parents & self._parent_group_set(other):
                continue
            if other.start_timeslot.period < end and start < other.start_timeslot.period + other.duration:
                return False
        return True

    def _is_off_group_edge(self, activity: ScheduledActivity, activities: Sequence[ScheduledActivity]) -> bool:
        """Cert si l'activitat no és ni la primera ni l'última de l'horari del
        seu grup aquell dia."""
        groups = set(group_names(activity.group_id))
        same_day = [
            other for other in activities
            if other.day == activity.day and groups & set(group_names(other.group_id))
        ]
        if not same_day:
            return False
        start = activity.start_timeslot.period
        end = start + activity.duration
        first = min(other.start_timeslot.period for other in same_day)
        last = max(other.start_timeslot.period + other.duration for other in same_day)
        return start > first and end < last

    def _misplaced_lone_quarters(self, activities: Sequence[ScheduledActivity]) -> List[ScheduledActivity]:
        return [
            activity for activity in activities
            if self._is_lone_quarter(activity, activities) and self._is_off_group_edge(activity, activities)
        ]

    @staticmethod
    def _is_quarter_movable(activity: ScheduledActivity) -> bool:
        block = activity.teaching_block
        return not (getattr(block, "fixed", False) or getattr(block, "fixed_day", None))

    def _same_day_edge_options(
        self,
        activity: ScheduledActivity,
        activities: Sequence[ScheduledActivity],
        context: GenerationContext,
    ) -> List[List[ScheduledActivity]]:
        """Reordena el dia del grup perquè `activity` quedi a primera o a
        última hora: les classes que hi havia abans (o després) es desplacen
        tantes franges com dura, sense deixar cap forat nou. Cada classe
        moguda passa per les mateixes restriccions que `place()`."""
        groups = set(group_names(activity.group_id))
        day_items = [
            other for other in activities
            if other is not activity and other.day == activity.day and groups & set(group_names(other.group_id))
        ]
        start = activity.start_timeslot.period
        end = start + activity.duration
        duration = activity.duration
        options: List[List[ScheduledActivity]] = []

        before = [other for other in day_items if other.start_timeslot.period + other.duration <= start]
        after = [other for other in day_items if other.start_timeslot.period >= end]
        if len(before) + len(after) != len(day_items):
            return options  # alguna classe se solapa amb aquesta: no es toca

        first_start = min([item.start_timeslot.period for item in before] + [start])
        last_end = max([item.start_timeslot.period + item.duration for item in after] + [end])
        plans = []
        if before:
            plans.append((first_start, [(item, item.start_timeslot.period + duration) for item in before]))
        if after:
            plans.append((last_end - duration, [(item, item.start_timeslot.period - duration) for item in after]))

        for new_start, shifted in plans:
            movers = [activity] + [item for item, _ in shifted]
            if not all(self._is_quarter_movable(item) for item in movers):
                continue
            rest = [other for other in activities if all(other is not mover for mover in movers)]
            placed: List[ScheduledActivity] = []
            valid = True
            for item, new_period in [(activity, new_start)] + shifted:
                placement = self._placement_strategy.place_at_slot(
                    item.teaching_block,
                    context,
                    rest + placed,
                    TimeSlot(day=activity.day, period=new_period),
                )
                if placement is None:
                    valid = False
                    break
                placed.append(placement)
            if valid:
                options.append(rest + placed)
        return options

    def _arrange_quarter_activities(
        self,
        activities: List[ScheduledActivity],
        context: GenerationContext,
    ) -> List[ScheduledActivity]:
        """Dues passades sobre les activitats 1Q/2Q, sempre amb les MATEIXES
        restriccions que la col·locació normal i sense empitjorar els forats
        dels professors:
        1. Un 1Q o 2Q que queda sol (sense parella al seu grup) no pot quedar
           enmig de l'horari del grup: s'ha de moure a primera o última hora.
        2. Un 1Q i un 2Q del mateix professor, encara que siguin de grups
           diferents, comparteixen franja quan és possible."""
        if not context.configuration.get("arrange_quarter_activities", True) or not activities:
            return activities

        days = list(context.school_calendar.days)
        activities = list(activities)

        strategy = self._placement_strategy
        all_slots = [
            TimeSlot(day=day, period=period)
            for day in days
            for period in range(context.school_calendar.periods_per_day)
        ]

        def metrics(items: Sequence[ScheduledActivity]) -> tuple:
            return (
                len(self._misplaced_lone_quarters(items)),
                self._group_gap_slots_total(items),
                self._teacher_gap_slots_total(items),
            )

        # --- 1. Els 1Q/2Q sols, a primera o última hora.
        for _ in range(self._QUARTER_MAX_MOVES):
            misplaced = [a for a in self._misplaced_lone_quarters(activities) if self._is_quarter_movable(a)]
            if not misplaced:
                break
            before = metrics(activities)
            best = None
            for activity in misplaced:
                for trial in self._same_day_edge_options(activity, activities, context):
                    after = metrics(trial)
                    if after[0] < before[0] and after[1] <= before[1] and after[2] <= before[2]:
                        key = (after[2], after[1], False, activity.day, 0)
                        if best is None or key < best[0]:
                            best = (key, trial)
                others = [other for other in activities if other is not activity]
                for slot in all_slots:
                    if slot.day == activity.day and slot.period == activity.start_timeslot.period:
                        continue
                    placement = strategy.place_at_slot(activity.teaching_block, context, others, slot)
                    if placement is None or not strategy._is_group_day_edge(
                        activity.group_id, slot.day, slot, placement.duration, others
                    ):
                        continue
                    trial = others + [placement]
                    after = metrics(trial)
                    if after[0] < before[0] and after[1] <= before[1] and after[2] <= before[2]:
                        key = (after[2], after[1], slot.day != activity.day, slot.day, slot.period)
                        if best is None or key < best[0]:
                            best = (key, trial)
                if best is not None:
                    break
            if best is None:
                break
            activities = best[1]

        # --- 2. 1Q i 2Q del mateix professor (grups diferents) a la mateixa franja.
        for _ in range(self._QUARTER_MAX_MOVES):
            before = metrics(activities)
            firsts = [a for a in activities if self._quarter_of(a) == "1q" and self._is_quarter_movable(a)]
            seconds = [a for a in activities if self._quarter_of(a) == "2q" and self._is_quarter_movable(a)]
            best = None
            for first in firsts:
                for second in seconds:
                    if first.duration != second.duration:
                        continue
                    if first.day == second.day and first.start_timeslot.period == second.start_timeslot.period:
                        continue
                    if not {name.casefold() for name in teacher_names(first.teacher_id)} & {
                        name.casefold() for name in teacher_names(second.teacher_id)
                    }:
                        continue
                    if self._parent_group_set(first) & self._parent_group_set(second):
                        continue  # el mateix grup ja s'aparella per grup
                    rest = [a for a in activities if a is not first and a is not second]
                    for slot in all_slots:
                        moved_first = strategy.place_at_slot(first.teaching_block, context, rest, slot)
                        if moved_first is None:
                            continue
                        moved_second = strategy.place_at_slot(second.teaching_block, context, rest + [moved_first], slot)
                        if moved_second is None:
                            continue
                        if not strategy._is_group_day_edge(first.group_id, slot.day, slot, first.duration, rest) or not (
                            strategy._is_group_day_edge(second.group_id, slot.day, slot, second.duration, rest)
                        ):
                            continue
                        trial = rest + [moved_first, moved_second]
                        after = metrics(trial)
                        if after[0] <= before[0] and after[1] <= before[1] and after[2] <= before[2]:
                            moved_distance = (slot.day != first.day) + (slot.day != second.day)
                            key = (after[2], after[1], after[0], moved_distance, slot.day, slot.period)
                            if best is None or key < best[0]:
                                best = (key, trial)
            if best is None:
                break
            activities = best[1]

        return activities

    def _generate_for_ordering(
        self,
        ordering: Sequence[TeachingBlock],
        context: GenerationContext,
    ) -> tuple[List[ScheduledActivity], List[dict]]:
        scheduled_activities: List[ScheduledActivity] = []
        warnings: List[dict] = []
        # Recorda, per requeriment (mateixa assignatura+grup+professor
        # partida en diversos blocs), quins dies ja s'hi han fet servir,
        # perquè cap altre bloc germà hi torni a caure mentre hi hagi un
        # dia lliure alternatiu — és el mateix "Màx. dies per repartir"
        # que ja es prova d'honorar a _build_blocks_from_requirements,
        # però aquí cal repetir-ho perquè aquesta és la passada que
        # realment decideix l'horari final.
        used_days_by_requirement: dict[str, set] = {}

        for block in ordering:
            requirement_id = (block.metadata or {}).get("requirement_id")
            excluded_days = used_days_by_requirement.get(requirement_id) if requirement_id else None

            if excluded_days:
                placement = self._placement_strategy.place(
                    block,
                    context,
                    scheduled_activities,
                    excluded_days=excluded_days,
                )
            else:
                placement = self._placement_strategy.place(
                    block,
                    context,
                    scheduled_activities,
                )

            if placement is None:
                placement = self._try_local_reorganization(
                    block,
                    context,
                    scheduled_activities,
                )

            if placement is None and excluded_days:
                # Si no hi ha cap dia lliure diferent dels ja usats pels
                # germans, val més repetir dia que deixar el bloc sense
                # col·locar: es torna a intentar sense l'exclusió.
                placement = self._placement_strategy.place(block, context, scheduled_activities)

            if placement is not None and requirement_id:
                used_days_by_requirement.setdefault(requirement_id, set()).add(placement.day)

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
                        "id": metadata.get("assignment_id", zlib.crc32(str(block.id).encode("utf-8"))),
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
                id=activity.teaching_block.metadata.get("assignment_id", index),
                teacher=activity.teacher_id or activity.teaching_block.metadata.get("teacher", ""),
                subject=activity.teaching_block.metadata.get("subject")
                or activity.teaching_block.metadata.get("subject_id")
                or activity.teaching_block.id,
                group=activity.group_id or activity.teaching_block.metadata.get("group", ""),
                room=activity.room_id or activity.teaching_block.metadata.get("room", ""),
                day=f"Day {activity.day}",
                start=f"Period {activity.start_timeslot.period}",
                duration=activity.duration,
                fixed=bool(getattr(activity.teaching_block, "fixed", False)),
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
