from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.bootstrap import reset_dependencies
from backend.routes.academic_data import academic_data_summary
from backend.routes.academic_workbook import AcademicWorkbookImportRequest, WorkbookFileDTO, import_academic_workbook
from backend.tests.test_excel_workbook_analyzer import _write_xlsx


def _build_templates(tmp_dir: str, include_second_teacher: bool = True) -> list[WorkbookFileDTO]:
    root = Path(tmp_dir)

    workload_rows = [
        ["Teacher", "Subject", "Student Group", "Weekly Hours", "Allowed Session Lengths", "Preferred Room", "Notes"],
        ["Ada", "Disseny", "1A", 2.0, "2", "A-01", ""],
    ]
    if include_second_teacher:
        workload_rows.append(["Alan", "Tipografia", "2B", 1.0, "1", "B-02", ""])

    files = [
        (
            "01_Carrega_docent.xlsx",
            [
                {
                    "name": "Carrega_docent",
                    "rows": workload_rows,
                }
            ],
        ),
        (
            "02_Restriccions_professors.xlsx",
            [
                {
                    "name": "Restriccions_prof",
                    "rows": [
                        ["Teacher", "Unavailable Slots", "Inferred Available Slots", "Editable Notes"],
                        ["Ada", "Dilluns 8:00", 10, ""],
                    ],
                }
            ],
        ),
        (
            "03_Restriccions_grups.xlsx",
            [
                {
                    "name": "Restriccions_grups",
                    "rows": [
                        ["Student Group", "Unavailable Slots", "Fixed Activity Slots", "Future Year Notes", "Future Year Extra Restrictions"],
                        ["1A", "Dimecres 10:00", "Dijous 11:00", "", ""],
                    ],
                }
            ],
        ),
        (
            "04_Aules.xlsx",
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
        ),
    ]

    payload: list[WorkbookFileDTO] = []
    for filename, sheets in files:
        target = root / filename
        _write_xlsx(target, sheets)
        payload.append(
            WorkbookFileDTO(
                name=filename,
                workbook_base64=base64.b64encode(target.read_bytes()).decode("utf-8"),
            )
        )

    return payload


def test_import_academic_workbook_endpoint_and_summary() -> None:
    reset_dependencies()

    with TemporaryDirectory() as tmp_dir:
        request = AcademicWorkbookImportRequest(files=_build_templates(tmp_dir))
        result = import_academic_workbook(request)

    summary = academic_data_summary()

    assert result["ok"] is True
    assert result["summary"]["teachers_imported"] == 2
    assert result["summary"]["groups_imported"] == 2
    assert result["summary"]["subjects_imported"] == 2
    assert result["summary"]["teaching_assignments"] == 2
    assert summary["teachers"] == 2
    assert summary["groups"] == 2
    assert summary["subjects"] == 2
    assert summary["teaching_assignments"] == 2


def test_import_reports_removed_rows_without_silent_deletion() -> None:
    reset_dependencies()

    with TemporaryDirectory() as tmp_dir:
        first = AcademicWorkbookImportRequest(files=_build_templates(tmp_dir, include_second_teacher=True))
        import_academic_workbook(first)

    with TemporaryDirectory() as tmp_dir:
        second = AcademicWorkbookImportRequest(files=_build_templates(tmp_dir, include_second_teacher=False))
        result = import_academic_workbook(second)

    assert result["teachers"]["removed"] == 1
    assert any(item["name"] == "Alan" for item in result["teachers"]["removed_records"])
