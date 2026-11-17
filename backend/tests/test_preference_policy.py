from backend.scheduler_engine.preference_policy import SchedulePreferencePolicy


def _rank(**overrides):
    values = {
        "hard_conflicts": 0,
        "unplaced_activities": 0,
        "unjoined_consecutive_pairs": 0,
        "shared_group_not_edge": 0,
        "preferred_day_misses": 0,
        "ignores_preferred_days": False,
        "quality_score": 0.0,
    }
    values.update(overrides)
    return SchedulePreferencePolicy.ranking_key(**values)


def test_ranking_keeps_hard_constraints_and_consecutive_pairs_ahead_of_quality():
    assert _rank(unplaced_activities=1, quality_score=1000) > _rank(
        unjoined_consecutive_pairs=1, quality_score=-1000
    )
    assert _rank(unjoined_consecutive_pairs=1, quality_score=1000) > _rank(
        unjoined_consecutive_pairs=0, quality_score=-1000
    )
    assert _rank(hard_conflicts=1) > _rank()


def test_shared_group_day_edge_violations_ignore_weekday():
    activities = [
        ("GI, GP", 4, 0, 2),
        ("GI", 4, 2, 1),
        ("GI", 4, 7, 1),
        ("GP", 4, 2, 1),
        ("GP", 4, 7, 1),
        ("GP, GI", 1, 3, 2),
        ("GI", 1, 0, 1),
        ("GI", 1, 7, 1),
        ("GP", 1, 0, 1),
        ("GP", 1, 7, 1),
        ("GI, GP", 0, 3, 2),
        ("GI", 0, 5, 2),
    ]

    assert SchedulePreferencePolicy.shared_group_day_edge_violations(activities) == 1
    assert SchedulePreferencePolicy.shared_group_day_edge_violations(
        [("GI, GP", 0, 0, 2)]
    ) == SchedulePreferencePolicy.shared_group_day_edge_violations(
        [("GI, GP", 4, 0, 2)]
    ) == 0


def test_preferred_day_misses_accept_multiple_days_and_can_be_ignored():
    day_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    preferences = [
        (4, "Divendres"),
        (0, "Dilluns, Divendres"),
        (1, "Divendres"),
        (2, None),
    ]

    misses = SchedulePreferencePolicy.preferred_day_misses(preferences, day_names)
    assert misses == 1
    assert _rank(preferred_day_misses=misses) > _rank()
    assert _rank(preferred_day_misses=misses, ignores_preferred_days=True) == _rank()
