"""Tests de regressió per a les funcionalitats afegides en la sessió de
treball sobre bloqueig d'horari de grup, Tutoria a les exportacions, i
exportació en PDF.

Cadascun d'aquests tests reprodueix el comportament esperat validat
manualment durant el desenvolupament; si algú torna a introduir un bug
relacionat, aquests tests han de fallar per avisar-ho de seguida.
"""

from io import BytesIO

from application.scheduler_use_cases import SchedulerUseCases
from services.schedule_exporter import build_schedule_export
from services.schedule_pdf_exporter import build_schedule_pdf


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
