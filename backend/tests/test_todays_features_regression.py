"""Tests de regressió per a les funcionalitats afegides en la sessió de
treball sobre bloqueig d'horari de grup, Tutoria a les exportacions, i
exportació en PDF.

Cadascun d'aquests tests reprodueix el comportament esperat validat
manualment durant el desenvolupament; si algú torna a introduir un bug
relacionat, aquests tests han de fallar per avisar-ho de seguida.
"""

from io import BytesIO

from application.live_schedule_use_cases import LiveScheduleUseCases
from application.scheduler_use_cases import SchedulerUseCases
from repositories.academic_data_repository import AcademicDataRepository
from scheduler_engine.models import Activity
from services.schedule_exporter import build_schedule_export
from services.schedule_pdf_exporter import build_schedule_pdf


def test_fixed_assignment_accepts_excel_time_with_seconds():
    from repositories.requirement_repository import RequirementRepository
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import SchoolCalendar

    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Joan"})
    repo.create_group({"name": "PFI"})
    repo.create_canonical_assignment({
        "teacher": "Joan",
        "subject": "Taller",
        "group": "PFI",
        "weekly_hours": 1,
        "fixed_day": "Dimarts",
        "fixed_start": "08:30:00",
    })
    day_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    hour_names = [f"{8 + index // 2}:{'00' if index % 2 == 0 else '30'}" for index in range(28)]
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=list(range(5)), periods_per_day=len(hour_names)),
        time_labels={"day_names": day_names, "hour_names": hour_names},
        academic_data_repo=repo,
    )

    result = use_cases.generate_proposals_from_academic_data()
    activities = (result.get("best_proposal") or {}).get("activities") or []

    assert len(activities) == 1
    assert activities[0]["day"] == "Dimarts"
    assert activities[0]["start"] == "8:30"
    assert activities[0]["fixed"] is True


def test_consecutive_assignment_targets_subject_and_teacher():
    from repositories.requirement_repository import RequirementRepository
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import ScheduleProposal, SchoolCalendar

    use_cases = SchedulerUseCases.__new__(SchedulerUseCases)
    use_cases._academic_data_repo = AcademicDataRepository()
    use_cases._time_labels = {
        "day_names": ["Dilluns"],
        "hour_names": [f"{8 + index // 2}:{'00' if index % 2 == 0 else '30'}" for index in range(20)],
    }
    use_cases._school_calendar = SchoolCalendar(days=[0], periods_per_day=20)
    use_cases._scheduler_engine = SchedulerEngine()

    activities = [
        Activity(1, "Eli", "GPP", "2n COM", "", "Dilluns", "10:00", 2),
        Activity(2, "Jordi", "GPP", "2n COM", "", "Dilluns", "13:00", 2),
        Activity(3, "Bego", "FOL", "2n COM", "", "Dilluns", "8:00", 2),
    ]
    proposal = ScheduleProposal(id="consecutive-gpp", activities=activities)
    assignments = [
        {"teacher": "Jordi", "subject": "GPP", "group": "2n COM"},
        {"teacher": "Eli", "subject": "GPP", "group": "2n COM"},
        {"teacher": "Bego", "subject": "FOL", "group": "2n COM", "consecutive_group": "GPP::Jordi"},
    ]

    aligned = use_cases._apply_consecutive_group_preferences(
        proposal, assignments, use_cases._time_labels["hour_names"]
    )
    starts_by_teacher = {activity.teacher: activity.start for activity in aligned.activities}

    assert starts_by_teacher["Jordi"] == "9:00"
    assert starts_by_teacher["Eli"] == "10:00"


def test_allowed_session_lengths_split_pfi_math_and_communication():
    from repositories.requirement_repository import RequirementRepository
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import SchoolCalendar

    repo = AcademicDataRepository()
    repo.create_group({"name": "PFI"})
    for teacher, subject in (("Judit", "PFI M3 Mates"), ("Imma", "MFG1 Comunicació")):
        repo.create_teacher({"name": teacher})
        repo.create_canonical_assignment({
            "teacher": teacher,
            "subject": subject,
            "group": "PFI",
            "weekly_hours": 3.5,
            "allowed_session_lengths": [2.0, 1.5],
        })
    day_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    hour_names = [f"{8 + index // 2}:{'00' if index % 2 == 0 else '30'}" for index in range(28)]
    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=list(range(5)), periods_per_day=len(hour_names)),
        time_labels={"day_names": day_names, "hour_names": hour_names},
        academic_data_repo=repo,
    )

    result = use_cases.generate_proposals_from_academic_data()
    activities = (result.get("best_proposal") or {}).get("activities") or []

    for subject in ("PFI M3 Mates", "MFG1 Comunicació"):
        sessions = [activity for activity in activities if activity["subject"] == subject]
        assert sorted(activity["duration"] for activity in sessions) == [3, 4]
        assert len({activity["day"] for activity in sessions}) == 2


# ---------------------------------------------------------------------------
# Bloqueig d'horari de grup
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, active_schedule):
        self.active_schedule = active_schedule


def _make_use_cases(active_schedule):
    uc = SchedulerUseCases.__new__(SchedulerUseCases)
    uc._working_timetable_repo = object()  # només cal que no sigui None
    uc._load_snapshot = lambda: _FakeSnapshot(active_schedule)
    return uc


def test_locked_group_position_is_found_even_with_combined_groups():
    """Un grup bloquejat ('GI') dins d'un bloc combinat ('GI, GP') a
    l'horari actiu ha de trobar-se correctament."""
    uc = _make_use_cases(
        [
            {
                "id": 1,
                "teacher": "Bego",
                "subject": "Ll. Tec. Audio UF3",
                "group": "GI, GP",
                "room": "A1",
                "day": "Dimarts",
                "start": "10:00",
                "duration": 2,
            }
        ]
    )
    placements = uc._build_locked_placements({"gi"})
    assert placements[("gi", "ll. tec. audio uf3", "bego")] == ("Dimarts", "10:00")


def test_apply_locked_placement_injects_fixed_day_and_start_on_a_copy():
    uc = _make_use_cases([])
    placements = {("gi", "ll. tec. audio uf3", "bego"): ("Dimarts", "10:00")}
    assignment = {"group": "GI, GP", "subject": "Ll. Tec. Audio UF3", "teacher": "Bego", "weekly_hours": 2}

    result = uc._apply_locked_placement(assignment, {"gi"}, placements)

    assert result is not assignment, "ha de retornar una còpia, no mutar l'original"
    assert assignment.get("fixed_day") is None, "l'assignació original no s'ha de tocar"
    assert result["fixed_day"] == "Dimarts"
    assert result["fixed_start"] == "10:00"


def test_apply_locked_placement_leaves_unlocked_assignments_untouched():
    uc = _make_use_cases([])
    assignment = {"group": "1r COM", "subject": "FOL", "teacher": "Carme"}

    result = uc._apply_locked_placement(assignment, {"gi"}, {})

    assert result is assignment


def test_build_locked_placements_is_empty_without_locked_groups():
    uc = _make_use_cases([{"id": 1, "group": "GI", "subject": "X", "teacher": "Y", "day": "Dilluns", "start": "8:00"}])
    assert uc._build_locked_placements(set()) == {}


def test_quarter_pair_alignment_reuses_start_even_with_different_durations():
    uc = _make_use_cases([])
    uc._academic_data_repo = AcademicDataRepository()
    uc._time_labels = {
        "day_names": ["Dilluns"],
        "hour_names": ["8:00", "8:30", "9:00", "9:30"],
    }
    uc._school_calendar = type("Calendar", (), {
        "days": [0],
        "periods_per_day": 4,
        "periods_for_day": lambda self, day: [
            type("Slot", (), {"day": day, "period": period})()
            for period in range(4)
        ],
    })()
    uc._scheduler_engine = __import__("scheduler_engine.engine", fromlist=["SchedulerEngine"]).SchedulerEngine()

    proposal = type("Proposal", (), {
        "id": "quarters",
        "activities": [
            Activity(1, "Ana", "Projecte 1Q", "GI", "", "Dilluns", "8:00", 2),
            Activity(2, "Biel", "Projecte 2Q", "GI", "", "Dilluns", "9:00", 1),
        ],
        "score": 0,
        "warnings": [],
        "conflicts": [],
        "score_breakdown": None,
        "metadata": {},
    })()

    aligned = uc._apply_quarter_pair_alignment(proposal)

    assert aligned.activities[0].start == "9:00"
    assert aligned.activities[1].start == "9:00"


def test_quarter_pair_alignment_does_not_move_fixed_activity():
    uc = _make_use_cases([])
    uc._academic_data_repo = AcademicDataRepository()
    uc._time_labels = {
        "day_names": ["Dilluns"],
        "hour_names": ["8:00", "8:30", "9:00", "9:30", "10:00", "10:30"],
    }
    uc._school_calendar = type("Calendar", (), {
        "days": [0],
        "periods_per_day": 6,
        "periods_for_day": lambda self, day: [
            type("Slot", (), {"day": day, "period": period})() for period in range(6)
        ],
    })()
    uc._scheduler_engine = __import__("scheduler_engine.engine", fromlist=["SchedulerEngine"]).SchedulerEngine()
    fixed_activity = Activity(1, "Joan", "Taller 2Q", "PFI", "", "Dilluns", "10:00", 1, fixed=True)
    flexible_activity = Activity(2, "Marc", "Taller 1Q", "PFI", "", "Dilluns", "8:00", 1)
    proposal = type("Proposal", (), {
        "id": "fixed-quarter",
        "activities": [fixed_activity, flexible_activity],
        "score": 0,
        "warnings": [],
        "conflicts": [],
        "score_breakdown": None,
        "metadata": {},
    })()

    aligned = uc._apply_quarter_pair_alignment(proposal)

    assert fixed_activity.start == "10:00"
    assert flexible_activity.start == "10:00"
    assert aligned.activities[0].start == "10:00"


def test_quarter_pair_alignment_only_matches_opposite_subject_endings():
    uc = _make_use_cases([])
    uc._academic_data_repo = AcademicDataRepository()
    uc._time_labels = {"day_names": ["Dilluns"], "hour_names": ["8:00", "8:30", "9:00"]}
    uc._school_calendar = type("Calendar", (), {
        "days": [0],
        "periods_per_day": 3,
        "periods_for_day": lambda self, day: [
            type("Slot", (), {"day": day, "period": period})() for period in range(3)
        ],
    })()
    uc._scheduler_engine = __import__("scheduler_engine.engine", fromlist=["SchedulerEngine"]).SchedulerEngine()

    def aligned_start(first_subject, second_subject):
        proposal = type("Proposal", (), {
            "id": "quarters",
            "activities": [
                Activity(1, "Ana", first_subject, "GI", "", "Dilluns", "8:00", 1),
                Activity(2, "Biel", second_subject, "GI", "", "Dilluns", "9:00", 1),
            ],
            "score": 0,
            "warnings": [],
            "conflicts": [],
            "score_breakdown": None,
            "metadata": {},
        })()
        result = uc._apply_quarter_pair_alignment(proposal)
        return result.activities[0].start, result.activities[1].start

    assert aligned_start("Projecte 1Q", "Projecte 2Q") == ("9:00", "9:00")
    assert aligned_start("Projecte 1Q", "Projecte 1Q") == ("8:00", "9:00")
    assert aligned_start("Projecte 2Q", "Projecte 2Q") == ("8:00", "9:00")
    assert aligned_start("Projecte", "Projecte 2Q") == ("8:00", "9:00")


def test_quarter_pair_alignment_detects_quarter_in_group_for_gi_programming():
    uc = _make_use_cases([])
    uc._academic_data_repo = AcademicDataRepository()
    uc._time_labels = {"day_names": ["Dilluns"], "hour_names": ["8:00", "8:30", "9:00"]}
    uc._school_calendar = type("Calendar", (), {
        "days": [0],
        "periods_per_day": 3,
        "periods_for_day": lambda self, day: [
            type("Slot", (), {"day": day, "period": period})() for period in range(3)
        ],
    })()
    uc._scheduler_engine = __import__("scheduler_engine.engine", fromlist=["SchedulerEngine"]).SchedulerEngine()

    proposal = type("Proposal", (), {
        "id": "gi-programming",
        "activities": [
            Activity(1, "Inno", "Ll. programació", "GI 1Q", "", "Dilluns", "8:00", 1),
            Activity(2, "Inno", "Ll. programació", "GI 2Q", "", "Dilluns", "9:00", 1),
        ],
        "score": 0,
        "warnings": [],
        "conflicts": [],
        "score_breakdown": None,
        "metadata": {},
    })()

    aligned = uc._apply_quarter_pair_alignment(proposal)

    assert aligned.activities[0].start == "9:00"
    assert aligned.activities[1].start == "9:00"




# ---------------------------------------------------------------------------
# Tutoria a l'exportació Excel: informativa al grup, bloc real al professor
# ---------------------------------------------------------------------------

_TUTORIA_ACTIVITIES = [
    {
        "id": 1,
        "teacher": "Carme",
        "subject": "FOL",
        "group": "1r COM",
        "room": "A2",
        "day": "Dilluns",
        "start": "10:00",
        "duration": 4,
    },
    {
        "id": 2,
        "teacher": "Marta",
        "subject": "Tutoria",
        "group": "1r APGI",
        "room": "",
        "day": "Dimarts",
        "start": "12:00",
        "duration": 2,
    },
]


def test_tutoria_does_not_occupy_a_grid_slot_in_the_group_sheet():
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))

    assert "G-1r APGI" in workbook.sheetnames
    sheet = workbook["G-1r APGI"]
    # No hi ha d'haver cap altra activitat que Tutoria per a aquest grup, i
    # per tant la graella ha de quedar buida (només el missatge "Sense
    # activitats programades.").
    found_grid_text = False
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value and "Tutoria" in str(cell.value) and "—" not in str(cell.value):
                found_grid_text = True
    assert not found_grid_text, "la Tutoria no ha d'aparèixer com a bloc a la graella del grup"


def test_tutoria_appears_as_a_note_under_the_group_title():
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))
    sheet = workbook["G-1r APGI"]

    note_texts = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value]
    assert any("Tutoria: Marta" in text and "Dimarts" in text for text in note_texts)


def test_tutoria_appears_as_a_real_block_on_the_teacher_sheet():
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))

    assert "P-Marta" in workbook.sheetnames
    sheet = workbook["P-Marta"]
    cell_texts = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value]
    assert any("Tutoria" in text and "1r APGI" in text for text in cell_texts)


# ---------------------------------------------------------------------------
# Exportació en PDF: prova de fum
# ---------------------------------------------------------------------------


def test_pdf_export_builds_one_page_per_group_teacher_and_room():
    buffer = build_schedule_pdf(_TUTORIA_ACTIVITIES)
    data = buffer.read()

    assert data[:5] == b"%PDF-"
    real_page_count = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    # 2 grups (1r COM, 1r APGI) + 2 professors (Carme, Marta) + 1 aula (A2)
    assert real_page_count == 5


def test_pdf_export_handles_empty_schedule_without_crashing():
    buffer = build_schedule_pdf([])
    assert buffer.getbuffer().nbytes > 0


# ---------------------------------------------------------------------------
# Compactació d'activitats: grups combinats han de respectar les franges
# no disponibles de cadascun dels seus noms individuals
# ---------------------------------------------------------------------------


class _FakeAcademicDataRepoForCompaction:
    """Només exposa el mínim que `_collect_blocked_slots` necessita."""

    def __init__(self, group_restrictions):
        self._group_restrictions = group_restrictions

    def active_teacher_restrictions(self):
        return []

    def active_group_restrictions(self):
        return self._group_restrictions


def _make_use_cases_for_compaction(group_restrictions, hour_names=None):
    uc = SchedulerUseCases.__new__(SchedulerUseCases)
    uc._time_labels = {
        "day_names": ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"],
        "hour_names": hour_names or ["8:00", "8:30", "9:00", "10:00", "10:30", "11:00", "15:00", "15:30"],
    }
    uc._academic_data_repo = _FakeAcademicDataRepoForCompaction(group_restrictions)
    return uc


def test_combined_group_compaction_respects_each_individual_groups_blocked_slots():
    """Bug real: una activitat de grup combinat ('GI, GP') es compactava
    fins a les 8:00 del matí perquè `_compact_activities` només mirava el
    text exacte 'GI, GP' a les franges bloquejades, que mai coincidia amb
    les restriccions reals (guardades per 'GI' i 'GP' per separat). Ha de
    respectar la unió de les franges bloquejades de tots dos noms."""
    uc = _make_use_cases_for_compaction(
        [
            {"group": "GI", "unavailable_slots": ["Dilluns 8:00", "Dilluns 8:30", "Dilluns 9:00"]},
            {"group": "GP", "unavailable_slots": ["Dilluns 8:00", "Dilluns 8:30", "Dilluns 9:00"]},
        ]
    )
    activities = [
        Activity(
            id=1,
            teacher="Noëlle",
            subject="Foto UF3",
            group="GI, GP",
            room="",
            day="Dilluns",
            start="15:00",
            duration=4,
        )
    ]

    compacted, moved_ids = uc._compact_activities(activities)

    assert compacted[0].start == "15:00"
    assert moved_ids == []


def test_single_group_compaction_still_works_as_before():
    """No-regressió: una activitat de grup individual (no combinat) es
    continua compactant normalment cap a la primera franja lliure."""
    uc = _make_use_cases_for_compaction(
        [{"group": "GI", "unavailable_slots": ["Dilluns 8:00"]}]
    )
    activities = [
        Activity(
            id=1,
            teacher="Marc",
            subject="GPP",
            group="GI",
            room="",
            day="Dilluns",
            start="9:00",
            duration=2,
        )
    ]

    compacted, moved_ids = uc._compact_activities(activities)

    assert compacted[0].start == "8:30"
    assert moved_ids == [1]


def test_compaction_preserves_fixed_activity_and_packs_around_it():
    uc = _make_use_cases_for_compaction(
        [],
        hour_names=[f"{hour}:{minute:02d}" for hour in range(8, 15) for minute in (0, 30)],
    )
    activities = [
        Activity(1, "Joan", "Taller", "PFI", "", "Dilluns", "10:00", 2, fixed=True),
        Activity(2, "Marc", "Projectes", "PFI", "", "Dilluns", "14:00", 2),
    ]

    compacted, moved_ids = uc._compact_activities(activities)
    by_id = {activity.id: activity for activity in compacted}

    assert by_id[1].start == "10:00"
    assert by_id[2].start == "11:00"
    assert moved_ids == [2]


def test_group_compaction_respects_group_daily_start_time():
    """La compactació no ha de forçar el grup a començar a les 8:00 si la
    restricció de grup exigeix començar més tard (p.ex. 10:00)."""
    uc = _make_use_cases_for_compaction(
        [{"group": "GI", "daily_start_time": "10:00"}],
        hour_names=["8:00", "8:30", "9:00", "9:30", "10:00", "10:30", "11:00", "11:30", "15:00", "15:30"],
    )
    activities = [
        Activity(
            id=1,
            teacher="Marc",
            subject="GPP",
            group="GI",
            room="",
            day="Dilluns",
            start="15:00",
            duration=2,
        ),
        Activity(
            id=2,
            teacher="Marc",
            subject="GPP 2",
            group="GI",
            room="",
            day="Dilluns",
            start="15:30",
            duration=1,
        ),
    ]

    compacted, moved_ids = uc._compact_activities(activities)

    assert [activity.start for activity in compacted] == ["10:00", "11:00"]
    assert sorted(moved_ids) == [1, 2]


def test_compaction_merges_transitive_combined_group_components():
    uc = _make_use_cases_for_compaction([])
    activities = [
        Activity(1, "A", "GI", "GI", "", "Dilluns", "8:00", 1),
        Activity(2, "B", "GP", "GP", "", "Dilluns", "10:00", 1),
        Activity(3, "C", "Compartida", "GI, GP", "", "Dilluns", "15:00", 1),
    ]

    compacted, _ = uc._compact_activities(activities)

    assert [activity.start for activity in compacted] == ["8:00", "8:30", "9:00"]

# ---------------------------------------------------------------------------
# Hora de Tutoria del tutor/a (també la dedicada a les famílies) amb les
# variants reals del nom de l'assignatura
# ---------------------------------------------------------------------------

_TUTORIA_FAMILY_ACTIVITIES = [
    {
        "id": 1,
        "teacher": "Maria",
        "subject": "Projectes",
        "group": "PFI",
        "room": "A1",
        "day": "Dimarts",
        "start": "9:00",
        "duration": 2,
    },
    {
        "id": 2,
        "teacher": "Judit",
        "subject": "PFI Tutoria",
        "group": "PFI",
        "room": "",
        "day": "Dimarts",
        "start": "11:00",
        "duration": 2,
    },
]


def test_pfi_tutoria_is_a_block_in_the_group_sheet():
    """La tutoria del PFI és lectiva i apareix com una activitat del grup."""
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_FAMILY_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))
    sheet = workbook["G-PFI"]

    cell_texts = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value]
    assert any("PFI Tutoria" in text and "Judit" in text for text in cell_texts)


def test_pfi_tutoria_is_not_added_as_a_nonlective_group_note():
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_FAMILY_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))
    sheet = workbook["G-PFI"]

    note_texts = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value]
    assert not any("Tutoria: Judit" in text for text in note_texts)


def test_pfi_tutoria_counts_as_lective_when_placing_mandatory_pfi_break():
    repo = AcademicDataRepository()
    repo.create_group({"name": "PFI"})
    uc = SchedulerUseCases.__new__(SchedulerUseCases)
    uc._time_labels = {
        "day_names": ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"],
        "hour_names": [f"{hour}:{minute:02d}" for hour in range(8, 15) for minute in (0, 30)],
    }
    uc._academic_data_repo = repo
    activities = [
        Activity(1, "Judit", "PFI Tutoria", "PFI", "", "Dilluns", "8:00", 2),
        Activity(2, "Imma", "MFG1 Comunicació", "PFI", "", "Dilluns", "9:00", 4),
        Activity(3, "Judit", "PFI M3 Mates", "PFI", "", "Dilluns", "11:00", 4),
    ]

    result = uc._insert_default_group_breaks(activities)

    assert result[0].start == "8:00"
    assert result[1].start == "9:30"
    assert result[2].start == "11:30"


def test_program_prefixed_tutoria_is_a_real_block_on_the_teacher_sheet():
    """Al full del professor, l'hora de tutoria sí que és un bloc de ple dret:
    és la seva franja, i ha de poder veure-la al seu horari."""
    from openpyxl import load_workbook

    buffer = build_schedule_export(_TUTORIA_FAMILY_ACTIVITIES)
    workbook = load_workbook(BytesIO(buffer.read()))
    sheet = workbook["P-Judit"]

    cell_texts = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value]
    assert any("PFI Tutoria" in text and "PFI" in text for text in cell_texts)


class _FakeAcademicRepoForTutorNames:
    """Només exposa el que `export_activities` necessita."""

    def __init__(self, groups):
        self._groups = groups

    def list_groups(self):
        return self._groups


def _make_live_use_cases_for_export(activities, groups):
    uc = LiveScheduleUseCases.__new__(LiveScheduleUseCases)
    uc._academic_data_repo = _FakeAcademicRepoForTutorNames(groups)
    uc.state = lambda: {"activities": activities}
    return uc


def test_export_activities_adds_the_group_tutor_name():
    uc = _make_live_use_cases_for_export(
        [
            {"id": 1, "teacher": "Bet", "subject": "Dx Tècnic", "group": "1r COM", "room": "", "day": "Dilluns", "start": "8:00", "duration": 2},
            {"id": 2, "teacher": "Judit", "subject": "PFI Tutoria", "group": "PFI", "room": "", "day": "Dimarts", "start": "11:00", "duration": 2},
        ],
        [{"name": "1r COM", "tutor": "Jordi"}, {"name": "PFI", "tutor": "Judit"}],
    )

    activities = uc.export_activities()

    assert activities[0]["tutor_name"] == "Jordi"
    assert activities[1]["tutor_name"] == "Judit"


def test_export_activities_resolves_the_tutor_of_combined_groups():
    uc = _make_live_use_cases_for_export(
        [
            {"id": 1, "teacher": "Bego", "subject": "Ll. Tec. Audio", "group": "GI, GP", "room": "", "day": "Dilluns", "start": "8:00", "duration": 2},
        ],
        [{"name": "GI", "tutor": "Bego"}],
    )

    assert uc.export_activities()[0]["tutor_name"] == "Bego"


def test_export_activities_leaves_activities_without_group_tutor_untouched():
    uc = _make_live_use_cases_for_export(
        [
            {"id": 1, "teacher": "Bet", "subject": "Dx Tècnic", "group": "1r COM", "room": "", "day": "Dilluns", "start": "8:00", "duration": 2},
        ],
        [{"name": "1r COM", "tutor": ""}],
    )

    assert "tutor_name" not in uc.export_activities()[0]


def test_export_activities_without_academic_data_returns_the_state_untouched():
    uc = LiveScheduleUseCases.__new__(LiveScheduleUseCases)
    uc._academic_data_repo = None
    uc.state = lambda: {"activities": [{"id": 1, "subject": "Taller", "group": "1r COM"}]}

    assert uc.export_activities() == [{"id": 1, "subject": "Taller", "group": "1r COM"}]


def test_pdf_header_metadata_includes_the_tutor_name():
    """La capçalera del grup ha de dir qui és el tutor/a. Abans sortia sempre
    buida perquè el nom només s'agafava d'una activitat de Tutoria."""
    from services.schedule_pdf_exporter import _page_metadata

    _room, group, tutor, _notes = _page_metadata(
        "group", "PFI", [{"group": "PFI", "tutor_name": "Judit"}], []
    )
    assert group == "PFI"
    assert tutor == "Judit"

    # Quan no hi ha el camp del tutor, la nota de Tutoria ja dona el nom.
    _room, _group, tutor_from_note, _notes = _page_metadata(
        "group", "PFI", [], ["Tutoria: Judit — Dimarts 11:00"]
    )
    assert tutor_from_note == "Judit"


def test_pdf_export_handles_activities_with_tutor_name_without_crashing():
    buffer = build_schedule_pdf(
        [
            {
                "id": 1,
                "teacher": "Judit",
                "subject": "PFI Tutoria",
                "group": "PFI",
                "room": "",
                "day": "Dimarts",
                "start": "11:00",
                "duration": 2,
                "tutor_name": "Judit",
            }
        ]
    )

    assert buffer.read()[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# "Màxim de dies en què es pot repartir" (Taller de 2n COM: 10h, màx. 3 dies)
# ---------------------------------------------------------------------------


def _taller_2n_com_requirement(max_days):
    from models.teaching_requirement import TeachingRequirement

    return TeachingRequirement(
        id="assignment-taller-2n-com",
        group_id="2n COM",
        subject_id="Taller",
        teacher_id="Jordi",
        weekly_hours=10.0,
        min_days=1,
        max_days=max_days,
        min_block_duration=0.5,
        max_consecutive_hours=10.0,
        allow_half_hour_blocks=False,
    )


def _tiny_calendar_context():
    """Context on cap distribució de blocs es pot col·locar sencera (només
    hi cap 1 hora al calendari), per forçar el camí de reserva del generador."""
    from scheduler_engine.models import GenerationContext, SchoolCalendar

    return GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=2),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )


def test_taller_with_max_days_3_keeps_its_sessions_when_nothing_fits_entirely():
    """El Taller de 2n COM són 10h amb "Màxim de dies per repartir" = 3: si
    cap distribució no es pot col·locar sencera, el generador NO ha de caure
    al bloc únic de 10h (que és impossible de col·locar en un horari real),
    sinó mantenir el repartiment en 3 sessions de 3h/3,5h/3,5h."""
    from scheduler_engine.generator import SchedulerGenerator

    blocks = SchedulerGenerator()._build_blocks_from_requirements(
        [_taller_2n_com_requirement(max_days=3)], _tiny_calendar_context()
    )

    assert len(blocks) == 3
    assert sum(block.duration_blocks for block in blocks) == 20
    assert sorted(block.duration_blocks for block in blocks) == [6, 7, 7]


def test_taller_with_max_days_1_still_falls_back_to_a_single_block():
    """Sense repartiment permès (Màx. dies = 1) es manté el comportament
    anterior: tota la càrrega en un sol bloc."""
    from scheduler_engine.generator import SchedulerGenerator

    blocks = SchedulerGenerator()._build_blocks_from_requirements(
        [_taller_2n_com_requirement(max_days=1)], _tiny_calendar_context()
    )

    assert [block.duration_blocks for block in blocks] == [20]


def test_taller_that_does_not_fit_whole_is_still_spread_over_its_days():
    """Si el Taller de 2n COM (10h amb "Màx. dies" = 3) no cap sencer enlloc,
    ha d'arribar a l'horari com a sessions repartides en els dies on sí que
    hi cap, no com un bloc únic de 10h impossible de col·locar (és el que
    passava abans: el generador queia sempre a la distribució més
    concentrada i el Taller quedava sense planificar)."""
    from repositories.requirement_repository import RequirementRepository
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import SchoolCalendar

    day_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    hour_names = [f"{8 + (index // 2)}:{'00' if index % 2 == 0 else '30'}" for index in range(28)]
    # Finestres lliures del grup: 3,5h el dilluns, 3h el dimarts i 2,5h la
    # resta de dies. Cap repartiment sencer del Taller hi cap, però sí que
    # hi caben sessions soltes.
    first_blocked_period = {"Dilluns": 7, "Dimarts": 6, "Dimecres": 5, "Dijous": 5, "Divendres": 5}

    repo = AcademicDataRepository()
    repo.create_group({"name": "2n COM"})
    repo.create_teacher({"name": "Jordi"})
    repo.create_canonical_assignment(
        {
            "teacher": "Jordi",
            "subject": "Taller",
            "group": "2n COM",
            "weekly_hours": 10.0,
            "max_session_days": "3",
        }
    )
    repo.upsert_group_restriction(
        {
            "group": "2n COM",
            "unavailable_slots": [
                f"{day} {hour}"
                for day in day_names
                for hour in hour_names[first_blocked_period[day] :]
            ],
        }
    )

    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=list(range(5)), periods_per_day=len(hour_names)),
        time_labels={"day_names": day_names, "hour_names": hour_names},
        academic_data_repo=repo,
    )

    result = use_cases.generate_proposals_from_academic_data()
    activities = (result.get("best_proposal") or {}).get("activities") or []
    taller = [activity for activity in activities if activity["subject"] == "Taller"]
    unscheduled = [item for item in result.get("unscheduled_activities") or [] if item.get("subject") == "Taller"]

    # El Taller mai no es planteja com un sol bloc de 10h (20 blocs).
    assert all(activity["duration"] < 20 for activity in taller + unscheduled)
    # Les sessions que s'hi col·loquen van repartides en dies diferents (màx. 3).
    assert taller
    assert len(taller) <= 3
    assert len({activity["day"] for activity in taller}) == len(taller)
    # I no es perd càrrega pel camí: el que està col·locat més el que queda
    # pendent suma les 10h de l'assignació.
    assert sum(activity["duration"] for activity in taller) + sum(
        item.get("duration") or 0 for item in unscheduled
    ) == 20

def test_taller_2n_com_10h_with_max_session_days_3_is_spread_across_days():

    """De punta a punta: una assignació de 10h amb `max_session_days` = 3 a
    les dades acadèmiques ha de generar un Taller repartit en 2-3 dies, no un
    únic bloc de 10h en un sol dia."""
    from repositories.requirement_repository import RequirementRepository
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models import SchoolCalendar

    day_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
    hour_names = [f"{8 + (index // 2)}:{'00' if index % 2 == 0 else '30'}" for index in range(28)]

    repo = AcademicDataRepository()
    repo.create_group({"name": "2n COM"})
    repo.create_teacher({"name": "Jordi"})
    repo.create_canonical_assignment(
        {
            "teacher": "Jordi",
            "subject": "Taller",
            "group": "2n COM",
            "weekly_hours": 10.0,
            "max_session_days": "3",
        }
    )

    use_cases = SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=list(range(5)), periods_per_day=len(hour_names)),
        time_labels={"day_names": day_names, "hour_names": hour_names},
        academic_data_repo=repo,
    )

    result = use_cases.generate_proposals_from_academic_data()
    activities = (result.get("best_proposal") or {}).get("activities") or []
    taller = [activity for activity in activities if activity["subject"] == "Taller"]

    assert taller
    assert len(taller) >= 2
    assert len({activity["day"] for activity in taller}) <= 3
    assert sum(activity["duration"] for activity in taller) == 20

