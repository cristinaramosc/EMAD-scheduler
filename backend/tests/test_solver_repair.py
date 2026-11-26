"""Tests del solver exacte de reparació (OR-Tools CP-SAT) i de la seva
integració al generador.

El solver és opcional: els tests que el necessiten se salten si `ortools` no
és instal·lat.
"""

import pytest

from backend.models.teaching_block import TeachingBlock
from backend.models.teaching_requirement import TeachingRequirement
from backend.scheduler_engine import generator as generator_module
from backend.scheduler_engine.generator import SchedulerGenerator
from backend.scheduler_engine.models import (
    GenerationContext,
    ScheduledActivity,
    SchoolCalendar,
    TimeSlot,
)
from backend.scheduler_engine.solver_repair import solve_requirements


def _requirement(
    req_id: str, group: str, teacher: str, hours: float = 2.0, room: str = ""
) -> TeachingRequirement:
    return TeachingRequirement(
        id=req_id,
        group_id=group,
        subject_id=f"Assignatura {req_id}",
        teacher_id=teacher,
        weekly_hours=hours,
        min_days=1,
        max_days=1,
        min_block_duration=0.5,
        max_consecutive_hours=hours,
        allow_half_hour_blocks=False,
        preferred_rooms=[room] if room else [],
    )


def _context(periods: int = 8, existing=()) -> GenerationContext:
    return GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=periods),
        existing_scheduled_activities=tuple(existing),
        configuration={},
    )


def _blocked_teacher(teacher: str, first_period: int, last_period: int) -> ScheduledActivity:
    return ScheduledActivity(
        teaching_block=TeachingBlock(
            id=f"blocked-{teacher}",
            duration=0.5,
            order=0,
            duration_blocks=1,
            metadata={"synthetic": True, "constraint": "teacher_not_available"},
        ),
        day=0,
        start_timeslot=TimeSlot(day=0, period=first_period),
        duration=last_period - first_period + 1,
        teacher_id=teacher,
        group_id="",
        metadata={"synthetic": True, "constraint": "teacher_not_available"},
    )


def _make_greedy_fail(monkeypatch):
    """El voraç (i el seu backtracking) no col·loquen res: una incidència per bloc."""
    monkeypatch.setattr(SchedulerGenerator, "_bounded_backtracking_search", lambda self, ordering, context: None)
    monkeypatch.setattr(
        SchedulerGenerator,
        "_generate_for_ordering",
        lambda self, ordering, context: (
            [],
            [{"id": index, "label": f"No s'ha pogut col·locar {index}"} for index, _ in enumerate(ordering)],
        ),
    )


def _intervals(placements):
    return sorted((start, start + duration) for _i, _o, duration, _day, start in placements)


def test_solver_places_requirements_of_the_same_teacher_without_overlap():
    pytest.importorskip("ortools")
    requirements = [_requirement("a", "G1", "Marta"), _requirement("b", "G2", "Marta")]

    placements = solve_requirements(requirements, _context(periods=8), time_limit_s=10)

    assert placements is not None and len(placements) == 2
    (first_start, first_end), (second_start, _second_end) = _intervals(placements)
    assert first_end <= second_start


def test_solver_returns_none_when_there_is_no_room():
    pytest.importorskip("ortools")
    requirements = [_requirement("a", "G1", "Marta"), _requirement("b", "G2", "Marta")]

    assert solve_requirements(requirements, _context(periods=6), time_limit_s=10) is None


def test_solver_respects_teacher_unavailability():
    pytest.importorskip("ortools")
    context = _context(periods=8, existing=[_blocked_teacher("Marta", 0, 3)])

    placements = solve_requirements([_requirement("a", "G1", "Marta")], context, time_limit_s=10)

    assert placements is not None
    assert all(start >= 4 for _i, _o, _duration, _day, start in placements)


def test_solver_keeps_the_hint_when_it_is_valid():
    pytest.importorskip("ortools")
    requirements = [_requirement("a", "G1", "Marta"), _requirement("b", "G2", "Marta")]
    hint = {(0, 1): (0, 4)}  # el primer requeriment ja estava col·locat a la franja 4

    placements = solve_requirements(requirements, _context(periods=8), hint=hint, time_limit_s=10)

    assert placements is not None
    assert {(i, start) for i, _o, _d, _day, start in placements}.issuperset({(0, 4)})


def test_generator_uses_the_solver_when_the_greedy_leaves_blocks_unplaced(monkeypatch):
    pytest.importorskip("ortools")
    _make_greedy_fail(monkeypatch)
    requirements = [_requirement("a", "G1", "Marta"), _requirement("b", "G2", "Marta")]

    result = SchedulerGenerator().generate(requirements, _context(periods=8))

    assert result.valid is True
    assert result.warnings == []
    best = result.proposals[0]
    assert (best.metadata or {}).get("solver_repaired") is True
    assert len(best.activities) == 2
    assert result.statistics["blocks_failed"] == 0
    assert len(result.generated_scheduled_activities) == 2


def test_generator_keeps_the_warnings_when_the_solver_is_not_available(monkeypatch):
    _make_greedy_fail(monkeypatch)
    monkeypatch.setattr(generator_module, "solver_available", lambda: False)
    requirements = [_requirement("a", "G1", "Marta"), _requirement("b", "G2", "Marta")]

    result = SchedulerGenerator().generate(requirements, _context(periods=8))

    assert result.valid is False
    # una incidència per bloc, sense duplicar-les per cada passada del generador
    assert len(result.warnings) == 2


def test_solver_joins_consecutive_pairs_when_it_can():
    pytest.importorskip("ortools")
    requirements = [_requirement("a", "G1", "Marta", hours=1.0), _requirement("b", "G2", "Pere", hours=1.0)]

    placements = solve_requirements(
        requirements, _context(periods=8), consecutive_pairs=[(0, 1)], time_limit_s=10
    )

    assert placements is not None
    (_first_start, first_end), (second_start, _second_end) = _intervals(placements)
    assert first_end == second_start


def test_solver_still_places_everything_when_a_consecutive_pair_is_impossible():
    pytest.importorskip("ortools")
    # "a" només pot anar a les franges 0-2 i "b" a les 6-7: mai poden quedar seguides
    context = _context(
        periods=8,
        existing=[_blocked_teacher("Marta", 3, 7), _blocked_teacher("Pere", 0, 5)],
    )
    requirements = [_requirement("a", "G1", "Marta", hours=1.0), _requirement("b", "G2", "Pere", hours=1.0)]

    placements = solve_requirements(requirements, context, consecutive_pairs=[(0, 1)], time_limit_s=10)

    assert placements is not None and len(placements) == 2


def test_solver_puts_a_quarter_pair_of_the_same_teacher_in_the_same_slot():
    pytest.importorskip("ortools")
    requirements = [_requirement("1Q", "G1", "Marta", hours=1.0), _requirement("2Q", "G1", "Marta", hours=1.0)]

    placements = solve_requirements(requirements, _context(periods=8), time_limit_s=10)

    assert placements is not None
    starts = {(day, start) for _i, _o, _duration, day, start in placements}
    assert len(starts) == 1


def test_solver_prefers_to_start_as_early_as_possible():
    pytest.importorskip("ortools")

    placements = solve_requirements([_requirement("a", "G1", "Marta", hours=1.0)], _context(periods=8), time_limit_s=10)

    assert placements is not None
    assert [start for _i, _o, _d, _day, start in placements] == [0]


def test_solver_packs_blocks_from_the_start_of_the_day():
    pytest.importorskip("ortools")
    requirements = [_requirement("a", "G1", "Marta", hours=1.0), _requirement("b", "G1", "Pere", hours=1.0)]

    placements = solve_requirements(requirements, _context(periods=8), time_limit_s=10)

    assert placements is not None
    assert sorted(start for _i, _o, _d, _day, start in placements) == [0, 2]


def test_solver_does_not_put_two_activities_in_the_same_room_at_once():
    pytest.importorskip("ortools")
    requirements = [
        _requirement("a", "G1", "Marta", hours=1.0, room="Taller"),
        _requirement("b", "G2", "Pere", hours=1.0, room="Taller"),
    ]
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=8),
        existing_scheduled_activities=(),
        configuration={"room_constraints_enabled": True},
    )

    placements = solve_requirements(requirements, context, time_limit_s=10)

    assert placements is not None
    (_first_start, first_end), (second_start, _second_end) = _intervals(placements)
    assert first_end <= second_start


def test_solver_does_not_count_a_fixed_coordination_as_a_class_day():
    pytest.importorskip("ortools")
    meeting = ScheduledActivity(
        teaching_block=TeachingBlock(
            id="fixed-meeting",
            duration=1.0,
            order=0,
            duration_blocks=2,
            fixed=True,
            metadata={"subject": "Coordinació conjunta · Gràfic", "teacher": "Marta"},
        ),
        day=1,
        start_timeslot=TimeSlot(day=1, period=0),
        duration=2,
        teacher_id="Marta",
        group_id="",
        metadata={"subject": "Coordinació conjunta · Gràfic"},
    )
    # El dia 1 només té lliures les franges de la reunió: la classe només cap el dia 0.
    rest_of_day_1 = ScheduledActivity(
        teaching_block=TeachingBlock(
            id="blocked-rest",
            duration=0.5,
            order=0,
            duration_blocks=1,
            metadata={"synthetic": True, "constraint": "teacher_not_available"},
        ),
        day=1,
        start_timeslot=TimeSlot(day=1, period=2),
        duration=6,
        teacher_id="Marta",
        group_id="",
        metadata={"synthetic": True, "constraint": "teacher_not_available"},
    )
    context = GenerationContext(
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=8),
        existing_scheduled_activities=(meeting, rest_of_day_1),
        fixed_activities=(meeting,),
        configuration={"teacher_max_days_constraints": {"marta": 1}},
    )

    placements = solve_requirements([_requirement("a", "G1", "Marta", hours=1.0)], context, time_limit_s=10)

    assert placements is not None
    assert all(day == 0 for _i, _o, _d, day, _start in placements)


def test_a_quarter_pair_counts_as_together_when_it_starts_or_ends_at_the_same_time():
    from backend.scheduler_engine.solver_repair import _quarter_aligned

    assert _quarter_aligned((0, 4), (0, 4), 8, 6)  # mateix inici
    assert _quarter_aligned((0, 2), (0, 4), 8, 6)  # una de 4 h i una de 3 h que acaben a la vegada
    assert not _quarter_aligned((0, 2), (0, 5), 8, 6)
    assert not _quarter_aligned((0, 4), (1, 4), 8, 8)  # un altre dia
    assert not _quarter_aligned(None, (0, 4), 8, 6)


@pytest.mark.parametrize("order", [("F", "2Q"), ("2Q", "F")])
def test_a_class_that_only_runs_one_semester_goes_after_the_full_year_class(order):
    pytest.importorskip("ortools")
    by_id = {
        "F": _requirement("F", "G1", "Marta", hours=1.0),
        "2Q": _requirement("2Q", "G1", "Pere", hours=1.0),
    }
    requirements = [by_id[key] for key in order]

    placements = solve_requirements(requirements, _context(periods=8), time_limit_s=10)

    assert placements is not None
    start = {requirements[i].id: begin for i, _o, _d, _day, begin in placements}
    # així, durant el 1r quadrimestre el grup comença a la primera franja
    assert start["F"] == 0 and start["2Q"] == 2
