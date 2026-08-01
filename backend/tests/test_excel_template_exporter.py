from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.repositories.school_calendar_repository import SchoolCalendarRepository, SchoolCalendarSettings
from backend.services.excel_template_exporter import ExcelTemplateExporter


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _column_index(cell_reference: str) -> int:
    letters = ""
    for char in cell_reference:
        if char.isalpha():
            letters += char.upper()
        else:
            break

    total = 0
    for char in letters:
        total = total * 26 + (ord(char) - ord("A") + 1)
    return total


def _read_rows(path: Path) -> list[list[str]]:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", NS):
                text_nodes = item.findall(".//main:t", NS)
                shared_strings.append("".join(node.text or "" for node in text_nodes))

        worksheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in worksheet_root.findall("main:sheetData/main:row", NS):
            values: list[str] = []
            for cell in row.findall("main:c", NS):
                reference = cell.attrib.get("r")
                if not reference:
                    continue
                column = _column_index(reference)
                while len(values) < column - 1:
                    values.append("")

                cell_type = cell.attrib.get("t")
                value_node = cell.find("main:v", NS)
                if value_node is None:
                    values.append("")
                    continue
                raw = value_node.text or ""
                if cell_type == "s":
                    values.append(shared_strings[int(raw)])
                else:
                    values.append(raw)
            rows.append(values)
    return rows


def _build_repositories(tmp_path: Path) -> tuple[AcademicDataRepository, SchoolCalendarRepository]:
    academic_data_repo = AcademicDataRepository()
    academic_data_repo.apply_snapshot(
        {
            "teachers": [{"name": "Ada"}, {"name": "Alan"}],
            "groups": [{"name": "1A"}, {"name": "2B"}],
            "subjects": [{"name": "Disseny"}, {"name": "Tipografia"}],
            "rooms": [{"name": "A-01"}, {"name": "B-02"}],
            "teaching_assignments": [
                {
                    "id": "assignment-1",
                    "teacher": "Ada",
                    "subject": "Disseny",
                    "group": "1A",
                    "weekly_hours": 2.0,
                    "preferred_room": "A-01",
                    "fixed_day": "Dilluns",
                    "fixed_start": "8:00",
                },
                {
                    "id": "assignment-2",
                    "teacher": "Alan",
                    "subject": "Tipografia",
                    "group": "2B",
                    "weekly_hours": 1.0,
                    "preferred_room": "B-02",
                },
            ],
            "teacher_restrictions": [
                {
                    "teacher": "Ada",
                    "unavailable_slots": ["Dimarts 8:30"],
                }
            ],
            "group_restrictions": [
                {
                    "group": "1A",
                    "unavailable_slots": ["Dilluns 8:30"],
                }
            ],
        }
    )

    calendar_file = tmp_path / "school_calendar.json"
    school_calendar_repo = SchoolCalendarRepository(calendar_file)
    school_calendar_repo.save_settings(
        SchoolCalendarSettings(
            day_names=["Dilluns", "Dimarts"],
            hour_names=["8:00", "8:30"],
        )
    )

    return academic_data_repo, school_calendar_repo


def test_exporter_generates_all_excel_templates_from_repositories(tmp_path: Path) -> None:
    academic_data_repo, school_calendar_repo = _build_repositories(tmp_path)

    exporter = ExcelTemplateExporter(
        academic_data_repo=academic_data_repo,
        school_calendar_repo=school_calendar_repo,
        output_root=tmp_path / "exports",
    )
    result = exporter.export_templates()

    generated_names = sorted(file.name for file in result.files)
    assert generated_names == [
        "01_Carrega_docent.xlsx",
        "02_Restriccions_professors.xlsx",
        "03_Restriccions_grups.xlsx",
        "04_Aules.xlsx",
    ]

    workbook_map = {file.name: Path(file.path) for file in result.files}

    load_rows = _read_rows(workbook_map["01_Carrega_docent.xlsx"])
    assert load_rows[0] == [
        "Teacher",
        "Subject",
        "Student Group",
        "Weekly Hours",
        "Allowed Session Lengths",
        "Preferred Room",
        "Notes",
    ]
    assert any(row[:3] == ["Ada", "Disseny", "1A"] for row in load_rows[1:])
    assert any(row[:3] == ["Alan", "Tipografia", "2B"] for row in load_rows[1:])

    teacher_rows = _read_rows(workbook_map["02_Restriccions_professors.xlsx"])
    teachers = {row[0] for row in teacher_rows[1:]}
    assert teachers == {"Ada", "Alan"}
    assert any("Dimarts 8:30" in row[1] for row in teacher_rows[1:] if row[0] == "Ada")

    group_rows = _read_rows(workbook_map["03_Restriccions_grups.xlsx"])
    groups = {row[0] for row in group_rows[1:]}
    assert {"1A", "2B"}.issubset(groups)
    assert any("Dilluns 8:30" in row[1] for row in group_rows[1:] if row[0] == "1A")
    assert any("Dilluns 8:00" in row[2] for row in group_rows[1:] if row[0] == "1A")

    room_rows = _read_rows(workbook_map["04_Aules.xlsx"])
    rooms = {row[0] for row in room_rows[1:]}
    assert rooms == {"A-01", "B-02"}


def test_exported_templates_match_repository_contents(tmp_path: Path) -> None:
    academic_data_repo, school_calendar_repo = _build_repositories(tmp_path)

    exporter = ExcelTemplateExporter(
        academic_data_repo=academic_data_repo,
        school_calendar_repo=school_calendar_repo,
        output_root=tmp_path / "exports",
    )
    result = exporter.export_templates()
    workbook_map = {file.name: Path(file.path) for file in result.files}

    load_rows = _read_rows(workbook_map["01_Carrega_docent.xlsx"])
    exported_teachers = {row[0] for row in load_rows[1:] if row and row[0]}
    exported_subjects = {row[1] for row in load_rows[1:] if len(row) > 1 and row[1]}
    exported_groups = {row[2] for row in load_rows[1:] if len(row) > 2 and row[2]}

    room_rows = _read_rows(workbook_map["04_Aules.xlsx"])
    exported_rooms = {row[0] for row in room_rows[1:] if row and row[0]}

    assert exported_teachers == {teacher["name"] for teacher in academic_data_repo.list_teachers()}
    assert exported_subjects == {subject["name"] for subject in academic_data_repo.list_subjects()}
    assert exported_groups == {group["name"] for group in academic_data_repo.list_groups()}
    assert exported_rooms == {room["name"] for room in academic_data_repo.list_rooms()}
