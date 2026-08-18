"""Tests de regressió per als bugs crítics trobats i corregits durant la
sessió de treball sobre 'grups solapats' (p.ex. 'GI' i 'GI, GP' com a
parella 1Q/2Q vàlida) i la restricció de finestra horària per dia.

Cadascun d'aquests tests reprodueix un bug real que va passar
desapercebut en producció; si algú torna a introduir el mateix patró
(agrupar per text exacte de grup en lloc de per grup individual, o
barrejar unitats de minuts/índex de període), aquests tests han de
fallar per avisar-ho de seguida.
"""

from scheduler_engine.constraints.group_conflict import GroupConflictConstraint
from scheduler_engine.constraints.group_max_days import GroupMaxDaysConstraint
from scheduler_engine.constraints.group_time_window import (
    GroupTimeWindowConstraint,
    get_group_time_window,
)
from scheduler_engine.constraints.room_conflict import RoomConflictConstraint
from scheduler_engine.constraints.teacher_conflict import TeacherConflictConstraint
from scheduler_engine.models import Activity, Schedule
from scheduler_engine.proposal_scorer import ProposalScorer
from scheduler_engine.quarter_utils import group_names, is_valid_quarter_pair


class _FakeSchedule:
    """Un Schedule minimal amb `.configuration` per als validadors que el
    necessiten (group_time_window, group_max_days)."""

    def __init__(self, activities, configuration=None):
        self._activities = activities
        self.configuration = configuration or {}

    def all(self):
        return self._activities


# ---------------------------------------------------------------------------
# group_names(): parsejar grups combinats separats per coma
# ---------------------------------------------------------------------------


def test_group_names_splits_combined_groups():
    assert group_names("GI, GP") == ("gi", "gp")


def test_group_names_single_group_unchanged():
    assert group_names("GI") == ("gi",)


def test_group_names_empty_returns_nothing():
    assert group_names("") == ()
    assert group_names(None) == ()


# ---------------------------------------------------------------------------
# is_valid_quarter_pair(): grups que se solapen (no cal identitat exacta)
# ---------------------------------------------------------------------------


def test_is_valid_quarter_pair_allows_overlapping_groups():
    assert is_valid_quarter_pair(
        "GI", "Ll. Tec. Audio UF3 1Q",
        "GI, GP", "Ll. Tec. Audio UF3 2Q",
    ) is True


def test_is_valid_quarter_pair_rejects_unrelated_groups():
    assert is_valid_quarter_pair(
        "GP", "Assignatura 1Q",
        "GI", "Altra assignatura 2Q",
    ) is False


def test_is_valid_quarter_pair_detects_prefix_marker():
    # El marcador 1Q/2Q pot anar al principi del nom ("1Q Proj UF1"), no
    # nomes al final ("Metodologia 2Q").
    assert is_valid_quarter_pair(
        "Comú", "1Q Proj UF1",
        "Comú", "2Q Art Experience",
    ) is True


# ---------------------------------------------------------------------------
# GroupConflictConstraint: bucketitzar per grup individual, no per text
# exacte del grup pare
# ---------------------------------------------------------------------------


def test_group_conflict_allows_quarter_pair_with_overlapping_groups():
    a1 = Activity(id="a1", group="GI", subject="Ll. Tec. Audio UF3 1Q", teacher="Bego", room=None, day="Dimarts", start="10:00", duration=8)
    a2 = Activity(id="a2", group="GI, GP", subject="Ll. Tec. Audio UF3 2Q", teacher="Bego", room=None, day="Dimarts", start="10:00", duration=6)
    schedule = Schedule(lessons=[a1, a2])
    assert GroupConflictConstraint().validate(schedule) == []


def test_group_conflict_detects_real_conflict_between_overlapping_groups():
    # Mateix escenari, pero SENSE relacio 1Q/2Q: aixo SI ha de ser un
    # conflicte real, ja que GI no pot ser a dos llocs alhora.
    a1 = Activity(id="a1", group="GI", subject="Dibuix", teacher="X", room=None, day="Dijous", start="9:00", duration=1)
    a2 = Activity(id="a2", group="GI, GP", subject="Pintura", teacher="Y", room=None, day="Dijous", start="9:00", duration=1)
    schedule = Schedule(lessons=[a1, a2])
    conflicts = GroupConflictConstraint().validate(schedule)
    assert len(conflicts) == 1


def test_group_conflict_independent_groups_do_not_interfere():
    a1 = Activity(id="a1", group="GP", subject="Assig 2Q", teacher="X", room=None, day="Dimecres", start="9:00", duration=1)
    a2 = Activity(id="a2", group="GI", subject="Altra 1Q", teacher="Y", room=None, day="Dimecres", start="9:00", duration=1)
    schedule = Schedule(lessons=[a1, a2])
    assert GroupConflictConstraint().validate(schedule) == []


# ---------------------------------------------------------------------------
# RoomConflictConstraint / TeacherConflictConstraint: excepció 1Q/2Q
# ---------------------------------------------------------------------------


def test_room_conflict_allows_quarter_pair_sharing_room():
    a1 = Activity(id="a1", group="Comú", subject="1Q Proj UF1", teacher="Alfred", room="Aula 3", day="Dilluns", start="9:00", duration=1)
    a2 = Activity(id="a2", group="Comú", subject="2Q Art Experience", teacher="Alfred", room="Aula 3", day="Dilluns", start="9:00", duration=1)
    schedule = Schedule(lessons=[a1, a2])
    assert RoomConflictConstraint().validate(schedule) == []


def test_teacher_conflict_allows_quarter_pair_same_teacher():
    a1 = Activity(id="a1", group="1r APGI", subject="Metodologia 2Q", teacher="Sònia", room=None, day="Dimecres", start="12:00", duration=1)
    a2 = Activity(id="a2", group="1r APGI", subject="Multimèdia UF1 1Q", teacher="Sònia", room=None, day="Dimecres", start="12:00", duration=1)
    schedule = Schedule(lessons=[a1, a2])
    assert TeacherConflictConstraint().validate(schedule) == []


def test_teacher_conflict_still_detects_real_conflict():
    a1 = Activity(id="a1", group="1A", subject="Dibuix", teacher="Sònia", room=None, day="Dimecres", start="12:00", duration=1)
    a2 = Activity(id="a2", group="2A", subject="Pintura", teacher="Sònia", room=None, day="Dimecres", start="12:00", duration=1)
    schedule = Schedule(lessons=[a1, a2])
    conflicts = TeacherConflictConstraint().validate(schedule)
    assert len(conflicts) == 1


# ---------------------------------------------------------------------------
# GroupMaxDaysConstraint: comptar dies correctament amb grups combinats
# ---------------------------------------------------------------------------


def test_group_max_days_counts_combined_group_activities():
    constraints = {"GI": 2}
    day_order = ["Dilluns", "Dimarts", "Dimecres"]
    a1 = Activity(id="a1", group="GI", subject="Foto", teacher="X", room=None, day="Dilluns", start="9:00", duration=1)
    a2 = Activity(id="a2", group="GI, GP", subject="Audio", teacher="Y", room=None, day="Dimarts", start="9:00", duration=1)
    a3 = Activity(id="a3", group="GI", subject="Video", teacher="Z", room=None, day="Dimecres", start="9:00", duration=1)
    schedule = _FakeSchedule(
        [a1, a2, a3],
        {"group_max_days_constraints": constraints, "day_names": day_order},
    )
    conflicts = GroupMaxDaysConstraint().validate(schedule)
    assert len(conflicts) == 1


# ---------------------------------------------------------------------------
# GroupTimeWindowConstraint / get_group_time_window: unitats i dia per nom
# ---------------------------------------------------------------------------


def test_get_group_time_window_per_day_override():
    constraints = {
        "1R COM": {"default": None, "by_day": {"Dimecres": (900, 1140)}}  # 15:00-19:00
    }
    assert get_group_time_window("1r COM", constraints, day="Dimecres") == (900, 1140)
    assert get_group_time_window("1r COM", constraints, day="Dijous") is None


def test_get_group_time_window_day_lookup_is_case_insensitive():
    constraints = {"1R COM": {"default": None, "by_day": {"Dimecres": (900, 1140)}}}
    # El motor de generacio calcula el nom del dia en minuscules
    # ("dimecres"); la cerca ha de trobar-ho igualment.
    assert get_group_time_window("1r COM", constraints, day="dimecres") == (900, 1140)


def test_group_time_window_constraint_uses_real_minutes_not_period_index():
    constraints = {"1R COM": {"default": None, "by_day": {"Dimecres": (900, 1140)}}}
    a_within = Activity(id="a1", group="1r COM", subject="Mates", teacher="X", room=None, day="Dimecres", start="15:00", duration=2)
    a_outside = Activity(id="a2", group="1r COM", subject="Angles", teacher="Y", room=None, day="Dimecres", start="9:00", duration=1)
    schedule = _FakeSchedule([a_within, a_outside], {"group_time_window_constraints": constraints})
    conflicts = GroupTimeWindowConstraint().validate(schedule)
    assert len(conflicts) == 1
    assert conflicts[0].start == "9:00"


# ---------------------------------------------------------------------------
# ProposalScorer: bonus de compactacio 1Q/2Q amb grups no identics
# ---------------------------------------------------------------------------


def test_quarter_pair_score_applies_with_overlapping_groups():
    from scheduler_engine.models import ScheduleProposal

    a1 = Activity(id="a1", group="GI", subject="Ll. Tec. Audio UF3 1Q", teacher="Bego", room=None, day="Dimarts", start="10:00", duration=8)
    a2 = Activity(id="a2", group="GI, GP", subject="Ll. Tec. Audio UF3 2Q", teacher="Bego", room=None, day="Dimarts", start="10:00", duration=6)
    proposal = ScheduleProposal(id="p1", activities=[a1, a2], score=0, conflicts=[], warnings=[])
    score = ProposalScorer()._quarter_pair_teacher_priority_score(proposal)
    assert score == 1000.0
