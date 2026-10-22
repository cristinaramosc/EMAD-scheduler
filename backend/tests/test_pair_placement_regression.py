"""Tests de regressió: restriccions de parella que el generador ignorava.

1. "Consecutiva amb" entre dues assignatures AMB EL MATEIX NOM i diferent
   professor (p.ex. Projecte Integrat de la Cristina i de la Sònia a GI):
   la regla "una assignatura no es repeteix el mateix dia al grup" ho feia
   impossible i el motor deixava les dues sessions en dies diferents.

2. Parella 1Q/2Q amb durades diferents i grups diferents (p.ex. Ll. Tec.
   Audio UF3 1Q de GI, 4 h, i 2Q de GI+GP, 3 h, ambdues del mateix
   professor): la peça curta ocupava una franja on la llarga ja no hi cabia
   i la parella quedava a dies diferents.
"""

from backend.models.teaching_block import TeachingBlock
from backend.scheduler_engine.generator import SchedulerGenerator
from backend.scheduler_engine.models import GenerationContext, SchoolCalendar


def _block(block_id, subject, group, teacher, duration_blocks):
    return TeachingBlock(
        id=block_id,
        duration=duration_blocks / 2,
        order=1,
        duration_blocks=duration_blocks,
        preferred_teacher_id=teacher,
        metadata={
            "subject": subject,
            "group": group,
            "group_id": group,
            "teacher": teacher,
            "requirement_id": block_id,
        },
    )


def _context(configuration=None, days=(0, 1, 2)):
    return GenerationContext(
        school_calendar=SchoolCalendar(days=list(days), periods_per_day=27),
        configuration=configuration or {},
    )


def _period(activity):
    return int(str(activity.start).split()[-1])


def _find(proposal, subject, group):
    return next(
        item for item in proposal.activities
        if item.subject == subject and item.group == group
    )


def test_consecutive_pair_with_the_same_subject_name_lands_back_to_back():
    # Els blocs "de farciment" ocupen el grup perquè la parella no hi caigui
    # per casualitat: l'única manera de complir és enganxar-les expressament.
    blocks = [
        _block("fill-1", "Dibuix", "GI", "Ana", 6),
        _block("fill-2", "Color", "GI", "Bruno", 6),
        _block("pi-sonia", "Projecte Integrat", "GI", "Sònia", 4),
        _block("pi-cristina", "Projecte Integrat", "GI", "Cristina", 2),
    ]
    context = _context(
        {
            "consecutive_pairs": [
                {
                    "a": ("Projecte Integrat", "GI", "Cristina"),
                    "b": ("Projecte Integrat", "GI", "Sònia"),
                }
            ]
        }
    )

    result = SchedulerGenerator().generate(blocks, context)

    assert result.valid
    for proposal in result.proposals:
        sonia = next(a for a in proposal.activities if a.teacher == "Sònia")
        cristina = next(a for a in proposal.activities if a.teacher == "Cristina")
        if len(proposal.activities) != len(blocks):
            continue  # només es comproven les propostes completes
        assert sonia.day == cristina.day
        first, second = sorted((sonia, cristina), key=_period)
        assert _period(first) + first.duration == _period(second)


def test_same_subject_same_day_is_still_rejected_when_not_declared_consecutive():
    """La regla original es manté per a la resta d'assignatures: sense
    "Consecutiva amb", dues sessions de la mateixa assignatura al mateix
    grup no poden caure el mateix dia."""
    blocks = [
        _block("pi-sonia", "Projecte Integrat", "GI", "Sònia", 4),
        _block("pi-cristina", "Projecte Integrat", "GI", "Cristina", 2),
    ]

    result = SchedulerGenerator().generate(blocks, _context(days=(0, 1)))

    for proposal in result.proposals:
        days = {a.day for a in proposal.activities}
        assert len(proposal.activities) == 2
        assert len(days) == 2


def test_quarter_pair_with_different_duration_and_groups_shares_the_same_slot():
    blocks = [
        _block("audio-2q", "Ll. Tec. Audio UF3 2Q", "GI, GP", "Bego", 6),
        _block("audio-1q", "Ll. Tec. Audio UF3 1Q", "GI", "Bego", 8),
        _block("fill-gi", "Dibuix", "GI", "Ana", 6),
        _block("fill-gp", "Color", "GP", "Bruno", 6),
    ]

    result = SchedulerGenerator().generate(blocks, _context())

    assert result.valid
    complete = [p for p in result.proposals if len(p.activities) == len(blocks)]
    assert complete
    for proposal in complete:
        audio_1q = _find(proposal, "Ll. Tec. Audio UF3 1Q", "GI")
        audio_2q = _find(proposal, "Ll. Tec. Audio UF3 2Q", "GI, GP")
        assert audio_1q.day == audio_2q.day
        assert _period(audio_1q) == _period(audio_2q)
        # La llarga (4 h) ha de cabre abans del final de la jornada.
        assert _period(audio_1q) + audio_1q.duration <= 27


def test_unequal_quarter_pair_is_centered_and_following_class_shifts_with_it():
    """Audio 1Q (4 h, GI) i 2Q (3 h, GI+GP) alineades per dalt deixarien 2
    franges buides seguides en un quadrimestre. La 2Q ha de començar una
    franja més tard, i la classe de GP just darrere s'hi desplaça."""
    from backend.bootstrap import reset_dependencies
    from backend.dependencies import get_scheduler_use_cases
    from backend.scheduler_engine.models import Activity

    reset_dependencies()
    use_cases = get_scheduler_use_cases()
    activities = [
        Activity(1, "Bego", "Ll. Tec. Audio UF3 1Q", "GI", "", "Dimarts", "15:00", 8),
        Activity(2, "Bego", "Ll. Tec. Audio UF3 2Q", "GI, GP", "", "Dimarts", "15:00", 6),
        Activity(3, "Cristina", "Projecte Integrat", "GP", "", "Dimarts", "18:00", 4),
    ]

    use_cases._center_unequal_quarter_pairs(activities)

    assert [a.start for a in activities] == ["15:00", "15:30", "18:30"]


def test_equal_duration_quarter_pair_is_left_untouched():
    from backend.bootstrap import reset_dependencies
    from backend.dependencies import get_scheduler_use_cases
    from backend.scheduler_engine.models import Activity

    reset_dependencies()
    use_cases = get_scheduler_use_cases()
    activities = [
        Activity(1, "Bego", "Audio 1Q", "GI", "", "Dimarts", "15:00", 6),
        Activity(2, "Bego", "Audio 2Q", "GI", "", "Dimarts", "15:00", 6),
    ]

    use_cases._center_unequal_quarter_pairs(activities)

    assert [a.start for a in activities] == ["15:00", "15:00"]


def _fresh_use_cases():
    from backend.bootstrap import reset_dependencies
    from backend.dependencies import get_scheduler_use_cases

    reset_dependencies()
    return get_scheduler_use_cases()


def _overlaps(activities):
    for i, first in enumerate(activities):
        for second in activities[i + 1:]:
            if first.day != second.day:
                continue
            a0 = int(first.start.split(":")[0]) * 2 + (1 if first.start.endswith(":30") else 0)
            b0 = int(second.start.split(":")[0]) * 2 + (1 if second.start.endswith(":30") else 0)
            if a0 < b0 + second.duration and b0 < a0 + first.duration:
                return True
    return False


def test_a_group_with_empty_days_gets_its_classes_spread_over_more_days():
    from backend.scheduler_engine.models import Activity

    use_cases = _fresh_use_cases()
    activities = [
        Activity(1, "Ana", "Mat", "1A", "", "Dilluns", "8:00", 4),
        Activity(2, "Bruno", "Hist", "1A", "", "Dilluns", "10:00", 4),
        Activity(3, "Carla", "Dibuix", "1A", "", "Dilluns", "12:00", 4),
        Activity(4, "Dani", "Musica", "1A", "", "Dimarts", "8:00", 4),
    ]

    use_cases._spread_group_days(activities, [])

    assert len({a.day for a in activities}) >= 3
    assert not _overlaps(activities)
    # Cap classe queda amb més d'una franja buida al mig del seu dia.
    assert use_cases._scheduler_engine.validate(use_cases._build_schedule(activities)) == []


def test_classes_tied_by_consecutive_with_and_fixed_classes_are_never_spread():
    from backend.scheduler_engine.models import Activity

    use_cases = _fresh_use_cases()
    activities = [
        Activity(1, "Ana", "Mat", "1A", "", "Dilluns", "8:00", 4),
        Activity(2, "Bruno", "Hist", "1A", "", "Dilluns", "10:00", 4),
        Activity(3, "Carla", "Dibuix", "1A", "", "Dilluns", "12:00", 4, True),
    ]
    assignments = [
        {"subject": "Mat", "group": "1A", "teacher": "Ana", "consecutive_group": "Hist::Bruno"},
        {"subject": "Hist", "group": "1A", "teacher": "Bruno"},
    ]

    use_cases._spread_group_days(activities, assignments)

    assert [(a.day, a.start) for a in activities] == [("Dilluns", "8:00"), ("Dilluns", "10:00"), ("Dilluns", "12:00")]


def test_groups_are_ordered_as_the_school_wants_in_the_exports():
    from backend.services.group_order import group_sort_key

    names = ["GI", "2n APGI", "Comú", "GP", "PFI", "1r APGI", "Nou", "2n COM", "1r COM"]
    assert sorted(names, key=group_sort_key) == [
        "PFI", "1r COM", "2n COM", "1r APGI", "2n APGI", "Comú", "GP", "GI", "Nou",
    ]


def test_compaction_closes_a_gap_when_nothing_else_is_in_the_way():
    from backend.scheduler_engine.models import Activity

    use_cases = _fresh_use_cases()
    activities = [
        Activity(1, "Ana", "Mat", "1A", "", "Dilluns", "8:00", 4),
        Activity(2, "Bruno", "Hist", "1A", "", "Dilluns", "12:00", 4),
    ]

    result = use_cases._compact_without_conflicts(activities, set())

    assert [(a.start) for a in sorted(result, key=lambda a: a.id)] == ["8:00", "10:00"]


def test_compaction_never_creates_a_teacher_conflict_to_close_a_gap():
    """Bruno ja fa classe (fixa) a 2B a les 10:00: moure-hi la Hist de 1A hi
    xocaria, així que es queda on és (abans això feia descartar TOTA la
    compactació de la proposta)."""
    from backend.scheduler_engine.models import Activity

    use_cases = _fresh_use_cases()
    activities = [
        Activity(1, "Ana", "Mat", "1A", "", "Dilluns", "8:00", 4),
        Activity(2, "Bruno", "Hist", "1A", "", "Dilluns", "12:00", 4),
        Activity(3, "Bruno", "Dibuix", "2B", "", "Dilluns", "10:00", 4, True),
        Activity(4, "Carla", "Musica", "1A", "", "Dimarts", "8:00", 4),
        Activity(5, "Dani", "Plastica", "1A", "", "Dimarts", "11:00", 4),
    ]

    result = use_cases._compact_without_conflicts(activities, set())
    by_id = {a.id: a for a in result}

    assert (by_id[2].day, by_id[2].start) == ("Dilluns", "12:00")  # bloquejada: es queda
    assert by_id[5].start == "10:00"  # la resta de la compactació sí que s'aplica
    assert use_cases._scheduler_engine.validate(use_cases._build_schedule(result)) == []
