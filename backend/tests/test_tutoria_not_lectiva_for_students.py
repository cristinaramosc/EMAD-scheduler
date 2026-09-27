"""L'hora de Tutoria no és lectiva per als alumnes (encara que sí per al
professor): no ha de comptar com a conflicte de grup ni com a dia lectiu
pel límit de "màx. dies" del grup, tot i ocupar normalment la franja del
professor que la fa. Aquest criteri ja estava implementat a l'exportació
d'Excel/PDF i al calendari en viu del frontend; aquí es cobreix el motor
de validació (scheduler_engine), que és qui detecta els conflictes que es
mostren a la proposta generada."""

from scheduler_engine.engine import SchedulerEngine
from scheduler_engine.models import Activity, Schedule


def test_tutoria_does_not_conflict_with_the_groups_own_class_at_the_same_slot():
    schedule = Schedule()

    # La classe normal del grup...
    schedule.add(
        Activity(id=1, teacher="Maria", subject="Dibuix", group="1A", room="A2", day="Dilluns", start="10:00", duration=1)
    )
    # ...i la Tutoria del seu tutor, exactament a la mateixa franja. No ha de
    # marcar-se com a conflicte de grup: la Tutoria és només informativa per
    # als alumnes.
    schedule.add(
        Activity(id=2, teacher="Jordi", subject="Tutoria", group="1A", room="", day="Dilluns", start="10:00", duration=1, fixed=True)
    )

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_conflict" for c in conflicts)


def test_tutoria_still_conflicts_with_the_teachers_own_other_class():
    schedule = Schedule()

    # El mateix professor no pot fer Tutoria i una altra classe alhora:
    # això sí que és una franja normal seva.
    schedule.add(
        Activity(id=1, teacher="Jordi", subject="GPP", group="2n COM", room="Taller", day="Dilluns", start="10:00", duration=1)
    )
    schedule.add(
        Activity(id=2, teacher="Jordi", subject="Tutoria", group="1A", room="", day="Dilluns", start="10:00", duration=1, fixed=True)
    )

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert any(c.type == "teacher_conflict" for c in conflicts)


def test_tutoria_day_does_not_count_towards_the_groups_max_days_limit():
    schedule = Schedule()
    schedule.configuration = {
        "day_names": ["Dilluns", "Dimarts", "Dimecres"],
        "group_max_days_constraints": {"1A": 2},
    }

    # El grup 1A ja té classe normal dilluns i dimarts (2 dies, dins del
    # límit). La Tutoria de dimecres no l'hauria de fer saltar el límit.
    schedule.add(Activity(id=1, teacher="Maria", subject="Dibuix", group="1A", room="A2", day="Dilluns", start="10:00", duration=1))
    schedule.add(Activity(id=2, teacher="Maria", subject="Color", group="1A", room="A2", day="Dimarts", start="10:00", duration=1))
    schedule.add(Activity(id=3, teacher="Jordi", subject="Tutoria", group="1A", room="", day="Dimecres", start="10:00", duration=1, fixed=True))

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_max_days" for c in conflicts)


# ---------------------------------------------------------------------------
# Variants reals del nom de l'assignatura: 'PFI Tutoria' (tal com arriba a les
# dades del centre) i 'Tutoria famílies'. Abans només es reconeixia el text
# exacte 'Tutoria', així que aquestes hores sí que ocupaven la graella del
# grup i comptaven com a dies lectius.
# ---------------------------------------------------------------------------


def test_tutoria_with_program_prefix_is_not_lective_for_the_group():
    schedule = Schedule()

    # El grup PFI té la seva classe normal...
    schedule.add(
        Activity(id=1, teacher="Maria", subject="Projectes", group="PFI", room="A1", day="Dimarts", start="9:00", duration=2)
    )
    # ...i a sobre l'hora de tutoria del seu tutor, a la mateixa franja.
    schedule.add(
        Activity(id=2, teacher="Judit", subject="PFI Tutoria", group="PFI", room="", day="Dimarts", start="9:00", duration=2, fixed=True)
    )

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_conflict" for c in conflicts)


def test_family_tutoring_hour_does_not_count_towards_the_groups_max_days_limit():
    schedule = Schedule()
    schedule.configuration = {
        "day_names": ["Dilluns", "Dimarts", "Dimecres"],
        "group_max_days_constraints": {"1A": 2},
    }

    schedule.add(Activity(id=1, teacher="Maria", subject="Dibuix", group="1A", room="A2", day="Dilluns", start="10:00", duration=1))
    schedule.add(Activity(id=2, teacher="Maria", subject="Color", group="1A", room="A2", day="Dimarts", start="10:00", duration=1))
    schedule.add(Activity(id=3, teacher="Jordi", subject="Tutoria famílies", group="1A", room="", day="Dimecres", start="10:00", duration=1, fixed=True))

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert not any(c.type == "group_max_days" for c in conflicts)


def test_family_tutoring_hour_does_not_conflict_with_the_tutors_own_class():
    schedule = Schedule()

    # La tutoria de famílies sí que ocupa la franja del professor: si el
    # tutor ja té classe en aquell moment, ha de sortir el conflicte.
    schedule.add(
        Activity(id=1, teacher="Jordi", subject="Projectes", group="1A", room="A2", day="Dilluns", start="17:00", duration=2)
    )
    schedule.add(
        Activity(id=2, teacher="Jordi", subject="Tutoria famílies", group="1A", room="", day="Dilluns", start="17:00", duration=2, fixed=True)
    )

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert any(c.type == "teacher_conflict" for c in conflicts)


def test_a_normal_subject_is_still_lective_for_the_group():
    schedule = Schedule()

    schedule.add(Activity(id=1, teacher="Maria", subject="Dibuix", group="1A", room="A2", day="Dilluns", start="10:00", duration=1))
    schedule.add(Activity(id=2, teacher="Jordi", subject="Volum", group="1A", room="A3", day="Dilluns", start="10:00", duration=1))

    engine = SchedulerEngine()
    engine.load(schedule)
    conflicts = engine.get_conflicts()

    assert any(c.type == "group_conflict" for c in conflicts)
