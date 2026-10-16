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
