"""Tests de regressió per a l'exportació/importació del full de càlcul unificat
de dades acadèmiques (/academic-data/spreadsheet/*), que és el fitxer que es
descarrega i es torna a carregar per treballar-hi fora de l'app.

Cobreixen que les columnes visibles a la web (Tutor i Desdoblat als grups,
Capacitat a les aules, Durades de sessió permeses i Consecutiva amb a les
assignacions) es conserven íntegrament en un cicle exporta -> importa.
"""

from openpyxl import load_workbook

from repositories.academic_data_repository import AcademicDataRepository
from routes.academic_workbook_spreadsheet import build_workbook, import_workbook


def _seeded_repo() -> AcademicDataRepository:
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Jordi"})
    repo.create_teacher({"name": "Eli"})
    repo.create_group({"name": "2n COM", "tutor": "Jordi", "is_split": True})
    repo.create_room({"name": "Taller 1", "capacity": 20})
    repo.create_canonical_assignment({
        "teacher": "Jordi",
        "subject": "GPP",
        "group": "2n COM",
        "weekly_hours": 3,
        "allowed_session_lengths": [2, 1],
    })
    repo.create_canonical_assignment({
        "teacher": "Eli",
        "subject": "FOL",
        "group": "2n COM",
        "weekly_hours": 2,
        "consecutive_group": "GPP::Jordi",
    })
    return repo


def test_summary_counts_unique_subjects_from_assignments_when_catalog_is_empty():
    repo = _seeded_repo()
    repo.create_canonical_assignment({
        "teacher": "Eli",
        "subject": "GPP",
        "group": "1r APGI",
        "weekly_hours": 1,
    })

    assert repo.list_subjects() == []
    assert repo.summary()["subjects"] == 2


def test_workbook_headers_include_tutor_split_capacity_lengths_and_consecutive_columns():
    buffer = build_workbook(repo=None, blank=True)
    workbook = load_workbook(buffer)

    group_headers = [cell.value for cell in workbook["Grups"][2]]
    subject_headers = [cell.value for cell in workbook["Assignatures"][2]]
    room_headers = [cell.value for cell in workbook["Aules"][1]]

    assert "Tutor" in group_headers
    assert "Desdoblat (Sí/No)" in group_headers
    assert "Capacitat" in room_headers
    assert any(h.startswith("Durades de sessió permeses") for h in subject_headers)
    assert any(h.startswith("Consecutiva amb - Assignatura") for h in subject_headers)
    assert any(h.startswith("Consecutiva amb - Professor") for h in subject_headers)


def test_workbook_headers_include_teacher_max_days_tutor_of_and_group_max_days():
    buffer = build_workbook(repo=None, blank=True)
    workbook = load_workbook(buffer)

    teacher_headers = [cell.value for cell in workbook["Professors"][2]]
    group_headers = [cell.value for cell in workbook["Grups"][2]]

    assert "Màxim de dies de classe per setmana (opcional)" in teacher_headers
    assert any(h and h.startswith("Tutor/a de") for h in teacher_headers)
    assert "Màxim de dies de classe per setmana (opcional)" in group_headers


def _sheet_records(workbook, title):
    sheet = workbook[title]
    labels = {cell.column: str(cell.value or "") for cell in sheet[2]}
    records = []
    for row in sheet.iter_rows(min_row=3):
        if all(cell.value in (None, "") for cell in row):
            continue
        records.append({labels[cell.column]: cell.value for cell in row if cell.column in labels})
    return records


def test_export_then_import_round_trips_teacher_max_days_and_tutor_groups():
    repo = _seeded_repo()
    repo.upsert_teacher_restriction({"teacher": "Jordi", "max_days": 4, "no_gaps": True})
    repo.upsert_group_restriction({"group": "2n COM", "max_days": 3})

    buffer = build_workbook(repo, blank=False)
    workbook = load_workbook(buffer)

    teacher_row = next(r for r in _sheet_records(workbook, "Professors") if r["Nom"] == "Jordi")
    assert teacher_row["Màxim de dies de classe per setmana (opcional)"] == 4
    assert teacher_row["Tutor/a de (grups, informatiu: es canvia a Grups)"] == "2n COM"

    group_row = next(r for r in _sheet_records(workbook, "Grups") if r["Nom del grup"] == "2n COM")
    assert group_row["Màxim de dies de classe per setmana (opcional)"] == 3

    repo2 = AcademicDataRepository()
    import_workbook(repo2, buffer.getvalue())

    teacher_restriction = next(r for r in repo2.list_teacher_restrictions() if r["teacher"] == "Jordi")
    assert teacher_restriction["max_days"] == 4
    assert teacher_restriction["no_gaps"] is True

    group_restriction = next(r for r in repo2.list_group_restrictions() if r["group"] == "2n COM")
    assert group_restriction["max_days"] == 3


def test_export_then_import_round_trips_tutor_split_capacity_lengths_and_consecutive_group():
    repo = _seeded_repo()

    buffer = build_workbook(repo, blank=False)

    repo2 = AcademicDataRepository()
    result = import_workbook(repo2, buffer.getvalue())

    assert result == {"teachers": 2, "groups": 1, "rooms": 1, "assignments": 2}

    group = next(g for g in repo2.list_groups() if g["name"] == "2n COM")
    assert group["tutor"] == "Jordi"
    assert group["is_split"] is True

    room = next(r for r in repo2.list_rooms() if r["name"] == "Taller 1")
    assert room["capacity"] == 20

    assignments = {a["subject"]: a for a in repo2.active_canonical_assignments()}
    assert assignments["GPP"]["allowed_session_lengths"] == [2.0, 1.0]
    # La forma "Assignatura::Professor" es reconstrueix a partir de les dues
    # columnes llegibles del full de càlcul.
    assert assignments["FOL"]["consecutive_group"] == "GPP::Jordi"


def test_import_still_works_with_an_older_workbook_missing_the_new_columns():
    """Un full exportat abans d'afegir aquestes columnes (o editat a mà sense
    Tutor/Desdoblat/Capacitat/Durades/Consecutiva) s'ha de poder importar
    igualment, simplement sense aquestes dades."""
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Sara"})
    repo.create_group({"name": "1r APGI"})
    repo.create_room({"name": "Aula 1"})
    repo.create_canonical_assignment({
        "teacher": "Sara", "subject": "FOL", "group": "1r APGI", "weekly_hours": 2,
    })

    buffer = build_workbook(repo, blank=False)
    workbook = load_workbook(buffer)

    # Simula un full antic: elimina les columnes noves de Grups i Aules.
    group_sheet = workbook["Grups"]
    for col_index, cell in list(enumerate(group_sheet[2], start=1)):
        if cell.value in ("Tutor", "Desdoblat (Sí/No)"):
            for row in group_sheet.iter_rows(min_row=2, max_col=group_sheet.max_column):
                row[col_index - 1].value = None

    import io
    stripped = io.BytesIO()
    workbook.save(stripped)
    stripped.seek(0)

    repo2 = AcademicDataRepository()
    result = import_workbook(repo2, stripped.getvalue())

    assert result["groups"] == 1
    group = next(g for g in repo2.list_groups() if g["name"] == "1r APGI")
    assert group.get("tutor", "") == ""
    assert not group.get("is_split")
