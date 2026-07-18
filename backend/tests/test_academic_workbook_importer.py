from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.services.academic_workbook_importer import AcademicWorkbookImportError, AcademicWorkbookImporter
from backend.tests.test_excel_workbook_analyzer import _write_xlsx


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _build_valid_templates(tmp_dir: str) -> list[tuple[str, bytes]]:
    root = Path(tmp_dir)

    workload = root / "01_Carrega_docent.xlsx"
    _write_xlsx(
        workload,
        [
            {
                    "name": "Carrega_docent",
                    "rows": [
                    ["Teacher", "Subject", "Student Group", "Weekly Hours", "Allowed Session Lengths", "Preferred Room", "Notes"],
                    ["Ada", "Disseny", "1A", 2.0, "2", "A-01", ""],
                    ["Alan", "Tipografia", "2B", 1.0, "1", "B-02", ""],
                ],
            }
        ],
    )

    teacher_restrictions = root / "02_Restriccions_professors.xlsx"
    _write_xlsx(
        teacher_restrictions,
        [
            {
                "name": "Restriccions_prof",
                "rows": [
                    ["Teacher", "Unavailable Slots", "Inferred Available Slots", "Editable Notes"],
                    ["Ada", "Dilluns 8:00; Dimarts 9:00", 10, ""],
                ],
            }
        ],
    )

    group_restrictions = root / "03_Restriccions_grups.xlsx"
    _write_xlsx(
        group_restrictions,
        [
            {
                "name": "Restriccions_grups",
                "rows": [
                    ["Student Group", "Unavailable Slots", "Fixed Activity Slots", "Future Year Notes", "Future Year Extra Restrictions"],
                    ["1A", "Dimecres 10:00", "Dijous 11:00", "", ""],
                ],
            }
        ],
    )

    rooms = root / "04_Aules.xlsx"
    _write_xlsx(
        rooms,
        [
            {
                "name": "Aules",
                "rows": [
                    ["Room", "Notes"],
                    ["A-01", ""],
                    ["B-02", ""],
                ],
            }
        ],
    )

    return [
        ("01_Carrega_docent.xlsx", _read_bytes(workload)),
        ("02_Restriccions_professors.xlsx", _read_bytes(teacher_restrictions)),
        ("03_Restriccions_grups.xlsx", _read_bytes(group_restrictions)),
        ("04_Aules.xlsx", _read_bytes(rooms)),
    ]


def test_importer_reads_generated_templates_and_updates_academic_repository() -> None:
    repo = AcademicDataRepository()
    importer = AcademicWorkbookImporter(repo)

    with TemporaryDirectory() as tmp_dir:
        payload = _build_valid_templates(tmp_dir)
        report = importer.import_files(payload)

    summary = repo.summary()
    assert report.teachers.imported == 2
    assert report.groups.imported == 2
    assert report.subjects.imported == 2
    assert report.teaching_assignments.imported == 2
    assert summary["teachers"] == 2
    assert summary["groups"] == 2
    assert summary["subjects"] == 2
    assert summary["teaching_assignments"] == 2
    assert summary["weekly_teaching_hours"] == 3.0
    assert summary["restrictions"] == 2


def test_importer_persists_subject_weekly_hours_from_assignments() -> None:
    repo = AcademicDataRepository()
    importer = AcademicWorkbookImporter(repo)

    with TemporaryDirectory() as tmp_dir:
        payload = _build_valid_templates(tmp_dir)
        importer.import_files(payload)

    subjects = sorted(repo.list_subjects(), key=lambda s: s["name"])
    assert subjects[0]["name"] == "Disseny"
    assert subjects[0]["weekly_hours"] == 2.0
    assert subjects[1]["name"] == "Tipografia"
    assert subjects[1]["weekly_hours"] == 1.0


def test_importer_reports_validation_issues_with_worksheet_row_and_column() -> None:
    repo = AcademicDataRepository()
    importer = AcademicWorkbookImporter(repo)

    with TemporaryDirectory() as tmp_dir:
        payload = _build_valid_templates(tmp_dir)

        invalid_workload_path = Path(tmp_dir) / "01_Carrega_docent.xlsx"
        _write_xlsx(
            invalid_workload_path,
            [
                {
                    "name": "Carrega_docent",
                    "rows": [
                        ["Teacher", "Subject", "Student Group", "Weekly Hours", "Allowed Session Lengths", "Preferred Room", "Notes"],
                        ["Ada", "Disseny", "1A", "", "2", "A-01", ""],
                    ],
                }
            ],
        )

        payload[0] = ("01_Carrega_docent.xlsx", invalid_workload_path.read_bytes())

        try:
            importer.import_files(payload)
            assert False, "Expected validation error"
        except AcademicWorkbookImportError as exc:
            issues = [issue.to_dict() for issue in exc.issues]

    assert any(
        issue["worksheet"] == "01_Carrega_docent.xlsx"
        and issue["row"] == 2
        and issue["column"] == "D"
        and issue["message"] == "weekly_hours_must_be_a_positive_number"
        for issue in issues
    )
