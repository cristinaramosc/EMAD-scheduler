from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from backend.services.excel_workbook_analyzer import ExcelWorkbookAnalyzer


def _write_xlsx(path: Path, sheets: list[dict]) -> None:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}

    def register_shared_string(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    def column_name(index: int) -> str:
        name = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            name = chr(ord("A") + remainder) + name
        return name

    worksheet_payloads: list[tuple[str, str]] = []
    for sheet_number, sheet in enumerate(sheets, start=1):
        row_xml: list[str] = []
        for row_number, row in enumerate(sheet["rows"], start=1):
            cell_xml: list[str] = []
            for column_number, value in enumerate(row, start=1):
                if value is None or value == "":
                    continue
                reference = f"{column_name(column_number)}{row_number}"
                if isinstance(value, (int, float)):
                    cell_xml.append(f'<c r="{reference}"><v>{value}</v></c>')
                else:
                    shared_id = register_shared_string(str(value))
                    cell_xml.append(f'<c r="{reference}" t="s"><v>{shared_id}</v></c>')
            row_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

        worksheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>'
            f'{"".join(row_xml)}'
            '</sheetData>'
            '</worksheet>'
        )
        worksheet_payloads.append((f"xl/worksheets/sheet{sheet_number}.xml", worksheet_xml))

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        + "".join(
            f'<sheet name="{sheet["name"]}" sheetId="{index}" r:id="rId{index}"/>'
            for index, sheet in enumerate(sheets, start=1)
        )
        + '</sheets></workbook>'
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + ('<Relationship Id="rIdShared" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>' if shared_strings else '')
        + '</Relationships>'
    )

    shared_strings_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
        + '</sst>'
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + ('<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' if shared_strings else '')
        + '</Types>'
    )

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        if shared_strings:
            archive.writestr("xl/sharedStrings.xml", shared_strings_xml)
        for worksheet_path, worksheet_xml in worksheet_payloads:
            archive.writestr(worksheet_path, worksheet_xml)


def test_analyzer_detects_entities_and_annual_hours_from_xlsx() -> None:
    with TemporaryDirectory() as tmp_dir:
        workbook_path = Path(tmp_dir) / "emad_workload.xlsx"
        _write_xlsx(
            workbook_path,
            [
                {
                    "name": "Docencia",
                    "rows": [
                        ["Grup", "Professor", "Assignatura", "Hores anuals"],
                        ["1A", "Ada Lovelace", "Disseny", 90],
                        [None, None, "Projectes", 60],
                        ["2B", "Alan Turing", "Tipografia", 75],
                        ["Total", None, None, 225],
                    ],
                },
                {
                    "name": "Notes",
                    "rows": [
                        ["Observacions"],
                        ["Sense impacte en la carrega docent"],
                    ],
                },
            ],
        )

        analysis = ExcelWorkbookAnalyzer().analyze(workbook_path)

        assert analysis.errors == []
        assert analysis.worksheet_names == ["Docencia", "Notes"]
        assert analysis.teachers == ["Ada Lovelace", "Alan Turing"]
        assert analysis.groups == ["1A", "2B"]
        assert analysis.subjects == ["Disseny", "Projectes", "Tipografia"]
        assert len(analysis.teaching_assignments) == 3
        assert analysis.annual_hours_entries == 3
        assert analysis.annual_hours_total == 225.0
        assert analysis.worksheets[0].assignments_detected == 3
        assert analysis.worksheets[0].ignored_rows == 1
        assert any("recognizable teaching-load table" in warning for warning in analysis.warnings)


def test_analyzer_warns_when_required_columns_are_missing() -> None:
    with TemporaryDirectory() as tmp_dir:
        workbook_path = Path(tmp_dir) / "partial_workload.xlsx"
        _write_xlsx(
            workbook_path,
            [
                {
                    "name": "Carrega",
                    "rows": [
                        ["Professor", "Hores anuals"],
                        ["Ada Lovelace", 90],
                    ],
                }
            ],
        )

        analysis = ExcelWorkbookAnalyzer().analyze(workbook_path)

        assert analysis.errors == []
        assert len(analysis.teaching_assignments) == 0
        assert any("missing required columns" in warning for warning in analysis.warnings)
        assert analysis.summary.startswith("Workbook analysed successfully")


def test_analyzer_rejects_unsupported_excel_formats() -> None:
    with TemporaryDirectory() as tmp_dir:
        workbook_path = Path(tmp_dir) / "legacy.xls"
        workbook_path.write_text("not-a-real-xls", encoding="utf-8")

        analysis = ExcelWorkbookAnalyzer().analyze(workbook_path)

        assert analysis.errors
        assert "Unsupported workbook format" in analysis.errors[0]