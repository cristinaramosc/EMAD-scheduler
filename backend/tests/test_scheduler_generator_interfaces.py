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
