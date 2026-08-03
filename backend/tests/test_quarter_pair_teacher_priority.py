"""Tests per a la soft constraint de màxima prioritat: quan una franja és
compartida per una parella vàlida 1Q/2Q, es prima que ambdues activitats
les imparteixi el mateix professor.

Aquesta preferència només s'aplica per decidir entre propostes que ja
compleixen la hard constraint de grups (una franja compartida sempre ha
de contenir exactament una assignatura 1Q i una 2Q del mateix grup pare).
"""

from scheduler_engine.models import Activity, GenerationContext, ScheduleProposal, SchoolCalendar
from scheduler_engine.proposal_scorer import ProposalScorer


def _context():
    calendar = SchoolCalendar(days=[0], periods_per_day=4, period_length_minutes=30)
    return GenerationContext(school_calendar=calendar)


def _proposal(activities):
    return ScheduleProposal(id="p", activities=activities)


def test_same_teacher_quarter_pair_scores_higher_than_different_teacher_pair():
    scorer = ProposalScorer()
    context = _context()

    same_teacher_proposal = _proposal(
        [
            Activity(id=1, teacher="Joan", subject="Dibuix 1Q", group="1A", room="A1", day="Day 0", start="Period 0", duration=1),
            Activity(id=2, teacher="Joan", subject="Dibuix 2Q", group="1A", room="A2", day="Day 0", start="Period 0", duration=1),
        ]
    )

    different_teacher_proposal = _proposal(
        [
            Activity(id=1, teacher="Joan", subject="Dibuix 1Q", group="1A", room="A1", day="Day 0", start="Period 0", duration=1),
            Activity(id=2, teacher="Maria", subject="Dibuix 2Q", group="1A", room="A2", day="Day 0", start="Period 0", duration=1),
        ]
    )

    same_teacher_score = scorer.calculate(same_teacher_proposal, context)
    different_teacher_score = scorer.calculate(different_teacher_proposal, context)

    assert same_teacher_score.total_score > different_teacher_score.total_score
    # La diferència ha de ser dominant respecte als altres components
    # (compactesa, distribució...), no un simple desempat marginal.
    assert same_teacher_score.total_score - different_teacher_score.total_score >= 900


def test_quarter_pair_bonus_ignores_unrelated_simultaneous_activities():
    """El bonus només s'aplica a parelles 1Q/2Q reals del mateix grup pare;
    activitats normals que comparteixen dia/hora sense ser parella vàlida
    no reben aquest bonus (encara que tinguin el mateix professor)."""
    scorer = ProposalScorer()
    context = _context()

    proposal = _proposal(
        [
            Activity(id=1, teacher="Joan", subject="Dibuix", group="1A", room="A1", day="Day 0", start="Period 0", duration=1),
            Activity(id=2, teacher="Joan", subject="Color", group="1B", room="A2", day="Day 0", start="Period 0", duration=1),
        ]
    )

    breakdown = scorer.calculate(proposal, context)
    assert breakdown.metadata["quarter_pair_teacher_score"] == 0.0


def test_quarter_pair_bonus_requires_both_activities_to_be_quarter_marked():
    scorer = ProposalScorer()
    context = _context()

    proposal = _proposal(
        [
            Activity(id=1, teacher="Joan", subject="Dibuix 1Q", group="1A", room="A1", day="Day 0", start="Period 0", duration=1),
            Activity(id=2, teacher="Joan", subject="Color", group="1A", room="A2", day="Day 0", start="Period 0", duration=1),
        ]
    )

    breakdown = scorer.calculate(proposal, context)
    assert breakdown.metadata["quarter_pair_teacher_score"] == 0.0
