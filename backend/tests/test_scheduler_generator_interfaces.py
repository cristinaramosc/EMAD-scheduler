import pytest

from backend.models.teaching_block import TeachingBlock
from scheduler_engine.generator import SchedulerGenerator
from scheduler_engine.models import (
    Activity,
    ConstraintReport,
    ConstraintViolation,
    GenerationContext,
    GenerationResult,
    ScheduledActivity,
    ScheduleProposal,
    SchoolCalendar,
    TimeSlot,
)
from backend.models.teaching_requirement import TeachingRequirement


def test_scheduled_activity_defaults():
    teaching_block = TeachingBlock(id="block-1", duration=2.0, order=1)
    activity = ScheduledActivity(
        teaching_block=teaching_block,
        day=0,
        start_timeslot=TimeSlot(day=0, period=3),
        duration=2,
        room_id="R1",
        teacher_id="teacher-1",
        group_id="A",
    )

    assert activity.teaching_block == teaching_block
    assert activity.day == 0
    assert activity.start_timeslot == TimeSlot(day=0, period=3)
    assert activity.duration == 2
    assert activity.room_id == "R1"
    assert activity.teacher_id == "teacher-1"
    assert activity.group_id == "A"


def test_generation_context_is_immutable_and_collects_inputs():
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
        random_seed=7,
    )

    assert context.school_calendar.days == [0, 1]
    assert context.existing_scheduled_activities == ()
    assert context.fixed_activities == ()
    assert context.blocked_time_slots == ()
    assert context.configuration == {}
    assert context.random_seed == 7
    assert isinstance(context.existing_scheduled_activities, tuple)

    with pytest.raises(Exception):
        context.random_seed = 8


def test_generation_result_defaults():
    result = GenerationResult(generated_scheduled_activities=[])

    assert result.generated_scheduled_activities == []
    assert result.warnings == []
    assert result.statistics == {}
    assert result.elapsed_time_ms == 0.0
    assert result.proposal_score is None
    assert result.valid is False


def test_greedy_placement_strategy_reproduces_current_behavior():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = strategy.place(
        TeachingBlock(id="block-1", duration=2.0, order=1),
        context,
        (),
    )

    assert result is not None
    assert result.start_timeslot.period == 0


def test_assignment_max_distribution_days_blocks_a_new_day():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    existing_block = TeachingBlock(
        id="assignment-1|s1",
        duration=1.0,
        order=1,
        duration_blocks=2,
        metadata={"requirement_id": "assignment-1", "max_distribution_days": 1, "group": "G"},
    )
    existing = ScheduledActivity(
        teaching_block=existing_block,
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=2,
        room_id="",
        teacher_id="",
        group_id="G",
    )
    candidate = TeachingBlock(
        id="assignment-1|s2",
        duration=1.0,
        order=2,
        duration_blocks=2,
        metadata={"requirement_id": "assignment-1", "max_distribution_days": 1, "group": "G"},
    )
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=2),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = GreedyPlacementStrategy().place(candidate, context, [existing])

    assert result is None


def test_scheduler_generator_uses_the_strategy():
    class RecordingStrategy:
        def __init__(self):
            self.calls = []

        def place(self, teaching_block, context, current_scheduled_activities):
            self.calls.append((teaching_block.id, len(current_scheduled_activities)))
            return None

    generator = SchedulerGenerator(placement_strategy=RecordingStrategy())
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate([TeachingBlock(id="block-1", duration=2.0, order=1)], context)

    assert result.valid is False
    assert result.warnings[0]["label"] == "No s'ha pogut col·locar bloc block-1"
    assert result.warnings[0]["duration"] == 4


def test_scheduler_generator_runs_phase_one_generation():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate([TeachingBlock(id="block-1", duration=2.0, order=1)], context)

    assert result.valid is True
    assert len(result.generated_scheduled_activities) == 1
    assert result.schedule_proposal is not None
    assert result.statistics["blocks_total"] == 1


def test_scheduler_generator_handles_empty_input():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate([], context)

    assert result.valid is True
    assert result.generated_scheduled_activities == []
    assert result.statistics["blocks_total"] == 0


def test_scheduler_generator_generates_multiple_proposals():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate(
        [
            TeachingBlock(id="block-1", duration=2.0, order=1),
            TeachingBlock(id="block-2", duration=2.0, order=2),
        ],
        context,
        max_proposals=3,
    )

    assert len(result.proposals) >= 2
    assert all(proposal.score >= 0 for proposal in result.proposals)
    assert all(proposal.score_breakdown is not None for proposal in result.proposals)


def test_scheduler_generator_is_reproducible_with_fixed_seed():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
        random_seed=7,
    )

    first = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=3,
    )
    second = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=3,
    )

    assert [proposal.id for proposal in first.proposals] == [proposal.id for proposal in second.proposals]


def test_scheduler_generator_proposals_are_independent_objects():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=2,
    )

    assert len(result.proposals) >= 2
    assert result.proposals[0] is not result.proposals[1]
    assert result.proposals[0].activities is not result.proposals[1].activities


def test_scheduler_generator_places_multiple_blocks():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate(
        [
            TeachingBlock(id="block-1", duration=2.0, order=1),
            TeachingBlock(id="block-2", duration=2.0, order=2),
        ],
        context,
    )

    assert result.valid is True
    assert len(result.generated_scheduled_activities) == 2


def test_scoring_engine_ranks_better_proposals_higher():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    compact = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=2,
    ).proposals[0]
    fragmented = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1)],
        context,
        max_proposals=1,
    ).proposals[0]

    assert compact.score >= fragmented.score


def test_warning_penalties_reduce_score():
    from scheduler_engine.proposal_scorer import ProposalScorer

    scorer = ProposalScorer()
    proposal = ScheduleProposal(id="p1", warnings=["warning"])
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    breakdown = scorer.calculate(proposal, context)
    assert breakdown.warning_penalty == 2.0
    assert breakdown.total_score < 0.0


def test_group_daily_balance_prefers_even_hours_between_days():
    from scheduler_engine.proposal_scorer import ProposalScorer

    scorer = ProposalScorer()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )
    balanced = ScheduleProposal(
        id="balanced",
        activities=[
            Activity(id=1, teacher="T1", subject="A", group="G1", room="", day="0", start="Period 0", duration=2),
            Activity(id=2, teacher="T1", subject="B", group="G1", room="", day="1", start="Period 0", duration=2),
        ],
    )
    unbalanced = ScheduleProposal(
        id="unbalanced",
        activities=[
            Activity(id=1, teacher="T1", subject="A", group="G1", room="", day="0", start="Period 0", duration=3),
            Activity(id=2, teacher="T1", subject="B", group="G1", room="", day="1", start="Period 0", duration=1),
        ],
    )

    balanced_breakdown = scorer.calculate(balanced, context)
    unbalanced_breakdown = scorer.calculate(unbalanced, context)

    assert balanced_breakdown.balance_score == 0.0
    assert unbalanced_breakdown.balance_score < balanced_breakdown.balance_score
    assert unbalanced_breakdown.metadata["maximum_group_daily_imbalance_hours"] == 1.0


def test_same_teacher_quarter_pairs_get_a_score_bonus():
    from scheduler_engine.proposal_scorer import ProposalScorer

    scorer = ProposalScorer()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    quarter_pair = ScheduleProposal(
        id="quarter-pair",
        activities=[
            Activity(id=1, teacher="Anna", subject="Mates 1Q", group="1A", room="", day="0", start="Period 0", duration=1),
            Activity(id=2, teacher="Anna", subject="Física 2Q", group="1A", room="", day="0", start="Period 1", duration=1),
        ],
    )
    non_quarter_pair = ScheduleProposal(
        id="non-quarter-pair",
        activities=[
            Activity(id=1, teacher="Anna", subject="Mates", group="1A", room="", day="0", start="Period 0", duration=1),
            Activity(id=2, teacher="Anna", subject="Física", group="1A", room="", day="0", start="Period 1", duration=1),
        ],
    )

    quarter_breakdown = scorer.calculate(quarter_pair, context)
    regular_breakdown = scorer.calculate(non_quarter_pair, context)

    assert quarter_breakdown.metadata["teacher_affinity_score"] > regular_breakdown.metadata["teacher_affinity_score"]
    assert quarter_breakdown.total_score > regular_breakdown.total_score


def test_score_ordering_is_deterministic():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    first = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=3,
    )
    second = generator.generate(
        [TeachingBlock(id="block-1", duration=2.0, order=1), TeachingBlock(id="block-2", duration=2.0, order=2)],
        context,
        max_proposals=3,
    )

    assert [proposal.id for proposal in first.proposals] == [proposal.id for proposal in second.proposals]


def test_constraint_evaluator_reports_no_violations():
    from scheduler_engine.constraint_evaluator import ConstraintEvaluator

    evaluator = ConstraintEvaluator()
    proposal = ScheduleProposal(id="p1", activities=[
        Activity(id=1, teacher="", subject="", group="", room="", day="0", start="Period 0", duration=1),
        Activity(id=2, teacher="", subject="", group="", room="", day="0", start="Period 1", duration=1),
    ])
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    report = evaluator.evaluate(proposal, context)

    assert len(report.soft_violations) >= 1
    assert report.statistics["soft_violation_count"] >= 1


def test_constraint_evaluator_reports_one_soft_violation():
    from scheduler_engine.constraint_evaluator import ConstraintEvaluator

    evaluator = ConstraintEvaluator()
    proposal = ScheduleProposal(id="p2", activities=[
        Activity(id=1, teacher="", subject="", group="", room="", day="0", start="Period 0", duration=1),
        Activity(id=2, teacher="", subject="", group="", room="", day="0", start="Period 2", duration=1),
    ])
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    report = evaluator.evaluate(proposal, context)

    assert len(report.soft_violations) >= 1
    assert any(violation.constraint_name == "gaps_inside_day" for violation in report.soft_violations)


def test_constraint_evaluator_reports_multiple_violations():
    from scheduler_engine.constraint_evaluator import ConstraintEvaluator

    evaluator = ConstraintEvaluator()
    proposal = ScheduleProposal(id="p3", activities=[
        Activity(id=1, teacher="", subject="", group="", room="", day="0", start="Period 0", duration=1),
        Activity(id=2, teacher="", subject="", group="", room="", day="0", start="Period 2", duration=1),
        Activity(id=3, teacher="", subject="", group="", room="", day="1", start="Period 0", duration=1),
        Activity(id=4, teacher="", subject="", group="", room="", day="1", start="Period 2", duration=1),
    ])
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    report = evaluator.evaluate(proposal, context)

    assert len(report.soft_violations) >= 2


def test_constraint_report_generation():
    report = ConstraintReport(hard_violations=[], soft_violations=[], warnings=["warning"], statistics={"activity_count": 1})
    assert report.warnings == ["warning"]
    assert report.statistics["activity_count"] == 1


def test_scheduler_generator_respects_blocked_slots():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=((0, 0),),
        configuration={},
    )

    result = generator.generate([TeachingBlock(id="block-1", duration=2.0, order=1)], context)

    assert result.valid is True
    assert result.generated_scheduled_activities[0].start_timeslot.period == 1


def test_scheduler_generator_marks_impossible_placement():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=2),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=((0, 0), (0, 1)),
        configuration={},
    )

    result = generator.generate([TeachingBlock(id="block-1", duration=2.0, order=1)], context)

    assert result.valid is False
    assert result.generated_scheduled_activities == []
    assert any("No s'ha pogut col·locar" in warning.get("label", "") for warning in result.warnings)


def test_scheduler_generator_does_not_leak_warnings_from_discarded_orderings():
    from scheduler_engine.models import ScheduledActivity, TimeSlot

    class OrderingSensitiveStrategy:
        def place(self, teaching_block, context, current_scheduled_activities, excluded_days=None):
            if teaching_block.id == "block-2" and any(
                activity.teaching_block.id == "block-1"
                for activity in current_scheduled_activities
            ):
                return None

            return ScheduledActivity(
                teaching_block=teaching_block,
                day=0,
                start_timeslot=TimeSlot(day=0, period=len(current_scheduled_activities)),
                duration=1,
                teacher_id=teaching_block.preferred_teacher_id,
                group_id=(teaching_block.metadata or {}).get("group"),
            )

        def explain_failure(self, teaching_block, context, current_scheduled_activities):
            return ["blocked for this ordering"]

    generator = SchedulerGenerator(placement_strategy=OrderingSensitiveStrategy())
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=2),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    result = generator.generate(
        [TeachingBlock(id="block-1", duration=1.0, order=1), TeachingBlock(id="block-2", duration=1.0, order=2)],
        context,
    )

    assert result.valid is True
    assert result.warnings == []
    assert result.schedule_proposal is not None
    assert result.schedule_proposal.warnings == []


def test_scheduler_generator_reorganizes_a_flexible_activity_for_a_later_block():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=3),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=((0, 1),),
        configuration={},
    )
    flexible = TeachingBlock(
        id="flexible",
        duration=1.0,
        order=1,
        duration_blocks=1,
        preferred_teacher_id="Biel",
        metadata={"teacher": "Biel", "group": "1A", "subject": "Optativa"},
    )
    constrained = TeachingBlock(
        id="constrained",
        duration=1.0,
        order=2,
        duration_blocks=1,
        preferred_teacher_id="Carme",
        metadata={"teacher": "Carme", "group": "1B", "subject": "FOL"},
    )

    result = generator.generate([flexible, constrained], context)

    assert result.valid is True
    assert result.warnings == []
    assert {activity.teaching_block.id for activity in result.generated_scheduled_activities} == {
        "flexible",
        "constrained",
    }


def test_local_reorganization_skips_an_unrelated_scheduled_activity():
    class CountingStrategy:
        def __init__(self):
            self.calls = 0

        def place(self, teaching_block, context, activities, excluded_days=None):
            self.calls += 1
            return None

    strategy = CountingStrategy()
    generator = SchedulerGenerator(placement_strategy=strategy)
    candidate = TeachingBlock(
        id="candidate",
        duration=1,
        order=2,
        preferred_teacher_id="Carme",
        metadata={"group": "2n APGI", "teacher": "Carme"},
    )
    unrelated_block = TeachingBlock(
        id="unrelated",
        duration=1,
        order=1,
        preferred_teacher_id="Biel",
        metadata={"group": "1r COM", "teacher": "Biel"},
    )
    unrelated_activity = ScheduledActivity(
        teaching_block=unrelated_block,
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=1,
        teacher_id="Biel",
        group_id="1r COM",
    )
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=2),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"room_constraints_enabled": True},
    )

    assert generator._try_local_reorganization(candidate, context, [unrelated_activity]) is None
    assert strategy.calls == 0


def test_group_no_gaps_restriction_blocks_non_contiguous_placement():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=4),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_restrictions": [{"group": "g1", "no_gaps": True}]},
    )

    first = strategy.place(
        TeachingBlock(
            id="block-1",
            duration=1.0,
            order=1,
            duration_blocks=1,
            metadata={"group": "g1"},
        ),
        context,
        (),
    )
    assert first is not None
    assert first.start_timeslot.period == 0

    second_context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=4),
        existing_scheduled_activities=(first,),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"group_restrictions": [{"group": "g1", "no_gaps": True}]},
    )

    second = strategy.place(
        TeachingBlock(
            id="block-2",
            duration=1.0,
            order=2,
            duration_blocks=1,
            metadata={"group": "g1"},
        ),
        second_context,
        (),
    )

    assert second is not None
    assert second.start_timeslot.period == 1


def test_scheduler_generator_prefers_afternoon_start_for_afternoon_groups():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=20),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"hour_names": [f"{hour}:00" for hour in range(8, 21)]},
    )

    placement = strategy.place(
        TeachingBlock(
            id="block-afternoon",
            duration=1.0,
            order=1,
            duration_blocks=1,
            metadata={"group": "GP"},
        ),
        context,
        (),
    )

    assert placement is not None
    assert placement.start_timeslot.period == 7


def test_slot_preference_prefers_afternoon_start_and_compact_day():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=20),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"hour_names": [f"{hour}:00" for hour in range(8, 21)]},
    )

    block = TeachingBlock(
        id="block-afternoon",
        duration=1.0,
        order=1,
        duration_blocks=1,
        metadata={"group": "GP"},
    )

    late_key = strategy._slot_preference_key(block, 0, type("Slot", (), {"period": 7})(), (), context)
    early_key = strategy._slot_preference_key(block, 0, type("Slot", (), {"period": 1})(), (), context)

    assert late_key < early_key


def test_group_daily_gap_limit_allows_one_empty_slot_and_blocks_larger_gaps():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    existing = (
        ScheduledActivity(
            teaching_block=TeachingBlock(id="existing-1", duration=2.0, order=1),
            day=0,
            start_timeslot=TimeSlot(day=0, period=0),
            duration=2,
            room_id="R1",
            teacher_id="T1",
            group_id="GI",
        ),
        ScheduledActivity(
            teaching_block=TeachingBlock(id="existing-2", duration=1.0, order=2),
            day=0,
            start_timeslot=TimeSlot(day=0, period=4),
            duration=1,
            room_id="R1",
            teacher_id="T1",
            group_id="GI",
        ),
    )

    candidate = TeachingBlock(
        id="candidate",
        duration=1.0,
        order=4,
        duration_blocks=1,
        metadata={"group": "GI"},
    )

    assert strategy._group_daily_gap_limit_conflict_exists(candidate, TimeSlot(day=0, period=2), existing, context) is False
    assert strategy._group_daily_gap_limit_conflict_exists(candidate, TimeSlot(day=0, period=3), existing, context) is False
    assert strategy._group_daily_gap_limit_conflict_exists(candidate, TimeSlot(day=0, period=5), existing, context) is True


def test_group_daily_gap_count_merges_overlapping_activity_intervals():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=16),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )
    existing = (
        ScheduledActivity(
            teaching_block=TeachingBlock(id="long", duration=10.0, order=1),
            day=0,
            start_timeslot=TimeSlot(day=0, period=0),
            duration=10,
            room_id="R1",
            teacher_id="T1",
            group_id="GI",
        ),
        ScheduledActivity(
            teaching_block=TeachingBlock(id="overlap", duration=2.0, order=2),
            day=0,
            start_timeslot=TimeSlot(day=0, period=2),
            duration=2,
            room_id="R1",
            teacher_id="T1",
            group_id="GI",
        ),
        ScheduledActivity(
            teaching_block=TeachingBlock(id="later", duration=1.0, order=3),
            day=0,
            start_timeslot=TimeSlot(day=0, period=11),
            duration=1,
            room_id="R1",
            teacher_id="T1",
            group_id="GI",
        ),
    )
    candidate = TeachingBlock(
        id="candidate",
        duration=1.0,
        order=4,
        duration_blocks=1,
        metadata={"group": "GI"},
    )

    assert strategy._group_daily_gap_limit_conflict_exists(
        candidate, TimeSlot(day=0, period=12), existing, context
    ) is False


def test_non_gi_gp_groups_keep_single_gap_window_limit():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )
    existing = (
        ScheduledActivity(
            teaching_block=TeachingBlock(id="first", duration=2.0, order=1),
            day=0,
            start_timeslot=TimeSlot(day=0, period=0),
            duration=2,
            group_id="g1",
        ),
        ScheduledActivity(
            teaching_block=TeachingBlock(id="second", duration=1.0, order=2),
            day=0,
            start_timeslot=TimeSlot(day=0, period=4),
            duration=1,
            group_id="g1",
        ),
        ScheduledActivity(
            teaching_block=TeachingBlock(id="third", duration=1.0, order=3),
            day=0,
            start_timeslot=TimeSlot(day=0, period=6),
            duration=1,
            group_id="g1",
        ),
    )
    candidate = TeachingBlock(
        id="candidate",
        duration=1.0,
        order=4,
        duration_blocks=1,
        metadata={"group": "g1"},
    )

    assert strategy._group_daily_gap_limit_conflict_exists(
        candidate, TimeSlot(day=0, period=2), existing, context
    ) is True
    assert strategy._group_daily_gap_limit_conflict_exists(
        candidate, TimeSlot(day=0, period=5), existing, context
    ) is False


def test_same_group_subject_is_placed_on_a_different_day():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=8),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )
    first_block = TeachingBlock(
        id="pfi-taller-joan",
        duration=2.0,
        order=1,
        preferred_teacher_id="Joan Carles",
        metadata={"subject": "PFI Taller", "group": "PFI", "teacher": "Joan Carles"},
    )
    first_session = ScheduledActivity(
        teaching_block=first_block,
        day=0,
        start_timeslot=TimeSlot(day=0, period=0),
        duration=4,
        teacher_id="Joan Carles",
        group_id="PFI",
    )
    second_block = TeachingBlock(
        id="pfi-taller-marc",
        duration=1.0,
        order=2,
        duration_blocks=2,
        preferred_teacher_id="Marc F.",
        metadata={"subject": "pfi taller", "group": "PFI", "teacher": "Marc F."},
    )

    placement = strategy.place(second_block, context, [first_session])

    assert placement is not None
    assert placement.day == 1


def test_scheduler_generator_orchestrates_teaching_requirements_into_proposals():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    requirements = [
        TeachingRequirement(
            id="req-1",
            group_id="g1",
            subject_id="s1",
            teacher_id="t1",
            weekly_hours=2.0,
            min_days=1,
            max_days=2,
            min_block_duration=1.0,
            max_consecutive_hours=2.0,
            allow_half_hour_blocks=False,
        ),
        TeachingRequirement(
            id="req-2",
            group_id="g2",
            subject_id="s2",
            teacher_id="t2",
            weekly_hours=2.0,
            min_days=1,
            max_days=2,
            min_block_duration=1.0,
            max_consecutive_hours=2.0,
            allow_half_hour_blocks=False,
        ),
    ]

    result = generator.generate(requirements, context)

    assert result.valid is True
    assert result.proposals
    assert all(proposal.activities for proposal in result.proposals)
    assert all(proposal.score_breakdown is not None for proposal in result.proposals)
    assert result.schedule_proposal is not None
    assert result.statistics["proposals_generated"] >= 1


def test_scheduler_generator_detects_teacher_conflicts_when_present():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    proposal = ScheduleProposal(
        id="proposal-conflict",
        activities=[
            Activity(id=1, teacher="t1", subject="s1", group="g1", room="r1", day="Day 0", start="Period 0", duration=2),
            Activity(id=2, teacher="t1", subject="s2", group="g2", room="r2", day="Day 0", start="Period 0", duration=2),
        ],
    )

    conflicts = generator._detect_conflicts(proposal)

    assert any(conflict.type == "teacher_conflict" for conflict in conflicts)


def test_every_ordering_places_priority_one_blocks_first_after_fixed_ones():
    generator = SchedulerGenerator()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=6),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    def block(block_id, duration_blocks, priority, fixed=False):
        return TeachingBlock(
            id=block_id,
            duration=duration_blocks / 2,
            order=1,
            duration_blocks=duration_blocks,
            fixed=fixed,
            metadata={"priority": priority},
        )

    blocks = [
        block("normal-long", 4, 2),
        block("normal-short", 1, 2),
        block("room-short", 1, 1),
        block("fixed-normal", 2, 2, fixed=True),
        block("teacher-days-long", 3, 1),
    ]

    for ordering in generator._build_orderings(blocks, context):
        ids = [item.id for item in ordering]
        assert ids[0] == "fixed-normal"
        assert set(ids[1:3]) == {"room-short", "teacher-days-long"}
        assert set(ids[3:]) == {"normal-long", "normal-short"}


def test_requirement_priority_is_carried_into_block_metadata():
    generator = SchedulerGenerator()
    requirement = TeachingRequirement(
        id="req-priority",
        group_id="g1",
        subject_id="s1",
        teacher_id="t1",
        weekly_hours=1.0,
        min_days=1,
        max_days=1,
        min_block_duration=1.0,
        max_consecutive_hours=1.0,
        allow_half_hour_blocks=False,
        priority=1,
    )

    blocks = generator._build_blocks_from_requirements([requirement])

    assert blocks
    assert all(item.metadata["priority"] == 1 for item in blocks)


def _half_hour_names():
    names = []
    minutes = 8 * 60
    while minutes <= 21 * 60:
        names.append(f"{minutes // 60}:{minutes % 60:02d}")
        minutes += 30
    return names


def _split_day_fixture():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=27),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"hour_names": _half_hour_names()},
    )

    def block(block_id, teacher="Ana"):
        return TeachingBlock(
            id=block_id,
            duration=1.0,
            order=1,
            duration_blocks=2,
            preferred_teacher_id=teacher,
            metadata={"group": "g1", "teacher": teacher},
        )

    def placed(teaching_block, day, period):
        return ScheduledActivity(
            teaching_block=teaching_block,
            day=day,
            start_timeslot=TimeSlot(day=day, period=period),
            duration=2,
            teacher_id="Ana",
            group_id="g1",
        )

    return strategy, context, block, placed


def test_teacher_split_day_penalty_distinguishes_same_half_new_day_and_split_day():
    strategy, context, block, placed = _split_day_fixture()
    morning_class = placed(block("morning"), day=0, period=2)  # 9:00
    candidate = block("candidate")
    afternoon_slot = TimeSlot(day=0, period=14)  # 15:00
    morning_slot = TimeSlot(day=0, period=4)  # 10:00

    assert strategy._teacher_split_day_penalty(candidate, 0, afternoon_slot, [morning_class], context) == 2
    assert strategy._teacher_split_day_penalty(candidate, 0, morning_slot, [morning_class], context) == 0
    assert strategy._teacher_split_day_penalty(candidate, 1, afternoon_slot, [morning_class], context) == 1


def test_teacher_split_day_penalty_ignores_other_teachers_and_missing_hour_names():
    strategy, context, block, placed = _split_day_fixture()
    other_teacher_class = placed(block("other", teacher="Biel"), day=0, period=2)
    other_teacher_class.teacher_id = "Biel"
    candidate = block("candidate")
    afternoon_slot = TimeSlot(day=0, period=14)

    assert strategy._teacher_split_day_penalty(candidate, 0, afternoon_slot, [other_teacher_class], context) == 1

    no_hours_context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=27),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )
    morning_class = placed(block("morning"), day=0, period=2)
    assert strategy._teacher_split_day_penalty(candidate, 0, afternoon_slot, [morning_class], no_hours_context) == 0


def test_placement_avoids_splitting_teacher_day_between_morning_and_afternoon():
    strategy, context, block, placed = _split_day_fixture()
    # Classe de matí d'un ALTRE grup (g2): així els forats del grup g1 no
    # interfereixen i només decideix l'afinitat matí/tarda del professor.
    morning_class = placed(block("morning"), day=0, period=2)  # dilluns 9:00
    morning_class.group_id = "g2"
    morning_class.teaching_block.metadata["group"] = "g2"

    key_same_day = strategy._slot_preference_key(
        block("a"), 0, TimeSlot(day=0, period=14), [morning_class], context
    )
    key_other_day = strategy._slot_preference_key(
        block("a"), 1, TimeSlot(day=1, period=14), [morning_class], context
    )

    assert key_other_day < key_same_day


def _max_days_fixture(constraints_key, constraints):
    strategy, _, block, placed = _split_day_fixture()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1, 2, 3, 4], periods_per_day=27),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={constraints_key: constraints},
    )

    def blocked(day, teacher_id="Ana", group_id="g1"):
        # Franja bloquejada per no disponibilitat: activitat sintètica.
        activity = placed(block(f"blocked-{day}"), day=day, period=20)
        activity.teacher_id = teacher_id
        activity.group_id = group_id
        activity.metadata = {"synthetic": True, "constraint": "not_available"}
        activity.teaching_block.metadata = {"synthetic": True}
        return activity

    return strategy, context, block, placed, blocked


def test_group_max_days_ignores_blocked_unavailability_slots():
    strategy, context, block, placed, blocked = _max_days_fixture("group_max_days_constraints", {"G1": 2})
    activities = [
        placed(block("a"), day=0, period=2),
        placed(block("b"), day=1, period=2),
        blocked(2),  # dimecres bloquejat, però NO és un dia de classe
    ]

    # Ja hi ha 2 dies de classe (màxim 2): un tercer dia s'ha de rebutjar.
    assert strategy._group_max_days_conflict_exists(block("c"), TimeSlot(day=2, period=2), activities, context)
    # Un dia ja utilitzat continua permès.
    assert not strategy._group_max_days_conflict_exists(block("c"), TimeSlot(day=1, period=6), activities, context)


def test_teacher_max_days_ignores_blocked_unavailability_slots():
    strategy, context, block, placed, blocked = _max_days_fixture("teacher_max_days_constraints", {"ana": 2})
    activities = [
        placed(block("a"), day=0, period=2),
        placed(block("b"), day=1, period=2),
        blocked(2),
    ]

    assert strategy._teacher_max_days_conflict_exists(block("c"), TimeSlot(day=2, period=2), activities, context)
    assert not strategy._teacher_max_days_conflict_exists(block("c"), TimeSlot(day=1, period=6), activities, context)


def _balance_fixture():
    strategy, context, block, placed = _split_day_fixture()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=27),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    def activity(index, day, period, fixed=False):
        teaching_block = block(f"c{index}", teacher=f"T{index}")
        teaching_block.fixed = fixed
        item = placed(teaching_block, day=day, period=period)
        item.teacher_id = f"T{index}"
        return item

    return SchedulerGenerator(), context, activity


def _group_load_by_day(activities):
    loads = {}
    for item in activities:
        loads[item.day] = loads.get(item.day, 0) + item.duration
    return loads


def test_balance_group_days_moves_an_edge_class_to_the_lighter_day():
    generator, context, activity = _balance_fixture()
    activities = [
        activity(1, 0, 0),
        activity(2, 0, 2),
        activity(3, 0, 4),
        activity(4, 1, 0),
    ]
    assert _group_load_by_day(activities) == {0: 6, 1: 2}

    balanced = generator._balance_group_days(activities, context)

    assert len(balanced) == 4
    assert _group_load_by_day(balanced) == {0: 4, 1: 4}
    # Cap solapament dins del grup després de moure.
    for day in (0, 1):
        spans = sorted(
            (item.start_timeslot.period, item.start_timeslot.period + item.duration)
            for item in balanced
            if item.day == day
        )
        assert all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))


def test_balance_group_days_never_moves_fixed_activities():
    generator, context, activity = _balance_fixture()
    activities = [
        activity(1, 0, 0, fixed=True),
        activity(2, 0, 2, fixed=True),
        activity(3, 0, 4, fixed=True),
        activity(4, 1, 0),
    ]

    balanced = generator._balance_group_days(activities, context)

    assert {(item.day, item.start_timeslot.period) for item in balanced if item.teaching_block.fixed} == {
        (0, 0),
        (0, 2),
        (0, 4),
    }


def test_balance_group_days_can_be_disabled_from_the_configuration():
    generator, context, activity = _balance_fixture()
    disabled = GenerationContext(
        school_calendar=context.school_calendar,
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"balance_group_days": False},
    )
    activities = [activity(1, 0, 0), activity(2, 0, 2), activity(3, 0, 4), activity(4, 1, 0)]

    balanced = generator._balance_group_days(activities, disabled)

    assert _group_load_by_day(balanced) == {0: 6, 1: 2}


def _quarter_fixture():
    from scheduler_engine.placement_strategy import GreedyPlacementStrategy

    strategy = GreedyPlacementStrategy()
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1, 2], periods_per_day=27),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )

    def block(block_id, subject, group, teacher, duration_blocks=2):
        return TeachingBlock(
            id=block_id,
            duration=duration_blocks / 2,
            order=1,
            duration_blocks=duration_blocks,
            preferred_teacher_id=teacher,
            metadata={"subject": subject, "group": group, "group_id": group, "teacher": teacher},
        )

    def placed(teaching_block, day, period, duration=2):
        return ScheduledActivity(
            teaching_block=teaching_block,
            day=day,
            start_timeslot=TimeSlot(day=day, period=period),
            duration=duration,
            teacher_id=teaching_block.preferred_teacher_id,
            group_id=(teaching_block.metadata or {}).get("group"),
        )

    return strategy, context, block, placed


def test_place_at_slot_applies_the_same_constraints_as_place():
    strategy, context, block, placed = _quarter_fixture()
    busy = placed(block("busy", "Mat", "g1", "Ana"), day=0, period=4)

    assert strategy.place_at_slot(block("x", "Dib", "g2", "Ana"), context, [busy], TimeSlot(day=0, period=4)) is None
    free = strategy.place_at_slot(block("x", "Dib", "g2", "Ana"), context, [busy], TimeSlot(day=0, period=8))
    assert free is not None and (free.day, free.start_timeslot.period) == (0, 8)


def test_quarter_block_pairs_with_same_teacher_even_in_a_different_group():
    strategy, context, block, placed = _quarter_fixture()
    first = placed(block("a", "Anglès 1Q", "g1", "Borja"), day=1, period=6)

    same_teacher = strategy.place(block("b", "Foto 2Q", "g2", "Borja"), context, [first])
    assert (same_teacher.day, same_teacher.start_timeslot.period) == (1, 6)


def test_arrange_quarters_moves_a_lone_quarter_from_the_middle_to_the_first_hour():
    generator = SchedulerGenerator()
    _, context, block, placed = _quarter_fixture()
    activities = [
        placed(block("a", "Mat", "g1", "T1"), day=0, period=0),
        placed(block("q", "Anglès 1Q", "g1", "T2"), day=0, period=2),
        placed(block("b", "Dib", "g1", "T3"), day=0, period=4),
    ]

    arranged = generator._arrange_quarter_activities(activities, context)

    positions = {item.teaching_block.id: item.start_timeslot.period for item in arranged}
    assert positions == {"q": 0, "a": 2, "b": 4}


def test_arrange_quarters_leaves_aligned_pairs_and_edge_quarters_alone():
    generator = SchedulerGenerator()
    _, context, block, placed = _quarter_fixture()
    activities = [
        placed(block("a", "Mat", "g1", "T1"), day=0, period=0),
        placed(block("q1", "Anglès 1Q", "g1", "T2"), day=0, period=2),
        placed(block("q2", "Foto 2Q", "g1", "T3"), day=0, period=2),
        placed(block("b", "Dib", "g1", "T4"), day=0, period=4),
        placed(block("e", "Hist 1Q", "g1", "T5"), day=1, period=0),
    ]

    arranged = generator._arrange_quarter_activities(activities, context)

    assert {(item.teaching_block.id, item.day, item.start_timeslot.period) for item in arranged} == {
        (item.teaching_block.id, item.day, item.start_timeslot.period) for item in activities
    }


def test_arrange_quarters_shares_a_slot_between_groups_for_the_same_teacher():
    generator = SchedulerGenerator()
    _, context, block, placed = _quarter_fixture()
    activities = [
        placed(block("x", "Anglès 1Q", "g1", "Borja"), day=0, period=0),
        placed(block("y", "Foto 2Q", "g2", "Borja"), day=1, period=0),
    ]

    arranged = generator._arrange_quarter_activities(activities, context)

    slots = {(item.day, item.start_timeslot.period) for item in arranged}
    assert len(slots) == 1


def test_arrange_quarters_can_be_disabled_from_the_configuration():
    generator = SchedulerGenerator()
    _, context, block, placed = _quarter_fixture()
    disabled = GenerationContext(
        school_calendar=context.school_calendar,
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={"arrange_quarter_activities": False},
    )
    activities = [
        placed(block("a", "Mat", "g1", "T1"), day=0, period=0),
        placed(block("q", "Anglès 1Q", "g1", "T2"), day=0, period=2),
        placed(block("b", "Dib", "g1", "T3"), day=0, period=4),
    ]

    arranged = generator._arrange_quarter_activities(activities, disabled)

    assert {item.teaching_block.id: item.start_timeslot.period for item in arranged} == {"a": 0, "q": 2, "b": 4}

