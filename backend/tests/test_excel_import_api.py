from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import HTTPException

from backend.routes.excel_import import WorkbookAnalyzeRequest, analyze_workbook
from backend.tests.test_excel_workbook_analyzer import _write_xlsx


def test_analyze_workbook_endpoint_returns_summary_payload() -> None:
    with TemporaryDirectory() as tmp_dir:
        workbook_path = Path(tmp_dir) / "api_workload.xlsx"
        _write_xlsx(
            workbook_path,
            [
                {
                    "name": "Docencia",
                    "rows": [
                        ["Grup", "Professor", "Assignatura", "Hores anuals"],
                        ["1A", "Ada Lovelace", "Disseny", 90],
                    ],
                }
            ],
        )

        payload = analyze_workbook(WorkbookAnalyzeRequest(workbook_path=str(workbook_path)))

        assert payload["counts"]["teachers"] == 1
        assert payload["counts"]["teaching_assignments"] == 1
        assert payload["annual_hours_total"] == 90.0
        assert payload["summary"].startswith("Workbook analysed successfully")


def test_analyze_workbook_endpoint_returns_400_for_invalid_workbooks() -> None:
    with pytest.raises(HTTPException) as excinfo:
        analyze_workbook(WorkbookAnalyzeRequest(workbook_path="/missing/workbook.xlsx"))

    assert excinfo.value.status_code == 400
    assert "Workbook file not found" in excinfo.value.detail["errors"][0]