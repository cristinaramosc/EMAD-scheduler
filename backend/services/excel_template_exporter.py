from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZipFile

try:
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.repositories.school_calendar_repository import SchoolCalendarRepository
except ModuleNotFoundError:  # pragma: no cover
    from repositories.academic_data_repository import AcademicDataRepository
    from repositories.school_calendar_repository import SchoolCalendarRepository


def _col_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _write_single_sheet_xlsx(path: Path, sheet_name: str, rows: list[list[Any]]) -> None:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}

    def register_shared_string(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    row_xml: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cell_xml: list[str] = []
        for column_number, value in enumerate(row, start=1):
            if value is None or value == "":
                continue

            reference = f"{_col_name(column_number)}{row_number}"

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

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        + (
            '<Relationship Id="rIdShared" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
            'Target="sharedStrings.xml"/>'
            if shared_strings
            else ""
        )
        + '</Relationships>'
    )

    shared_strings_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in shared_strings)
        + '</sst>'
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        + (
            '<Override PartName="/xl/sharedStrings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            if shared_strings
            else ""
        )
        + '</Types>'
    )

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        if shared_strings:
            archive.writestr("xl/sharedStrings.xml", shared_strings_xml)


@dataclass
class GeneratedTemplate:
    name: str
    path: str


@dataclass
class TemplateExportResult:
    output_folder: str
    files: list[GeneratedTemplate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_folder": self.output_folder,
            "files": [{"name": file.name, "path": file.path} for file in self.files],
        }


class ExcelTemplateExporter:
    def __init__(
        self,
        academic_data_repo: AcademicDataRepository,
        school_calendar_repo: SchoolCalendarRepository,
        output_root: Path,
    ) -> None:
        self._academic_data_repo = academic_data_repo
        self._school_calendar_repo = school_calendar_repo
        self._output_root = output_root

    def export_templates(self) -> TemplateExportResult:
        settings = self._school_calendar_repo.load_settings()
        day_names = list(settings.day_names)
        hour_names = list(settings.hour_names)

        teacher_records = self._academic_data_repo.list_teachers()
        group_records = self._academic_data_repo.list_groups()
        room_records = self._academic_data_repo.list_rooms()
        assignment_records = self._academic_data_repo.active_canonical_assignments()

        activities: list[dict[str, Any]] = []
        for index, assignment in enumerate(assignment_records, start=1):
            subject = assignment.get("subject", "") or ""
            if subject.strip().lower() in {"descans", "dinar", "pati", "esbarjo"}:
                continue

            teacher = assignment.get("teacher", "") or ""
            group = assignment.get("group", "") or ""
            preferred_room = assignment.get("preferred_room", "") or assignment.get("room", "") or ""
            fixed_slot = ""
            if assignment.get("fixed_day") and assignment.get("fixed_start"):
                fixed_slot = f"{assignment['fixed_day']} {assignment['fixed_start']}"

            weekly_hours = assignment.get("weekly_hours") or 0
            duration = assignment.get("duration") or weekly_hours
            activities.append(
                {
                    "id": assignment.get("id") or index,
                    "teacher": teacher,
                    "subject": subject,
                    "group": group,
                    "duration": duration,
                    "weekly_hours": weekly_hours,
                    "preferred_room": preferred_room,
                    "fixed_slot": fixed_slot,
                }
            )

        teacher_names = {record.get("name", "") for record in teacher_records if record.get("name")}
        teacher_names.update(activity["teacher"] for activity in activities if activity["teacher"])

        group_names = {record.get("name", "") for record in group_records if record.get("name")}
        group_names.update(activity["group"] for activity in activities if activity["group"])

        teacher_unavailable: dict[str, set[str]] = {teacher: set() for teacher in teacher_names}
        for restriction in self._academic_data_repo.list_teacher_restrictions():
            teacher = (restriction.get("teacher") or "").strip()
            if not teacher:
                continue
            teacher_unavailable.setdefault(teacher, set()).update(restriction.get("unavailable_slots") or [])

        group_unavailable: dict[str, set[str]] = {group: set() for group in group_names}
        for restriction in self._academic_data_repo.list_group_restrictions():
            group = (restriction.get("group") or "").strip()
            if not group:
                continue
            group_unavailable.setdefault(group, set()).update(restriction.get("unavailable_slots") or [])

        group_fixed_slots: dict[str, set[str]] = {group: set() for group in group_names}
        for activity in activities:
            if activity["group"] and activity["fixed_slot"]:
                group_fixed_slots.setdefault(activity["group"], set()).add(activity["fixed_slot"])

        room_names = {record.get("name", "") for record in room_records if record.get("name")}
        room_names.update(activity["preferred_room"] for activity in activities if activity["preferred_room"])

        output_folder = self._build_output_folder()

        file_specs = [
            (
                "01_Carrega_docent.xlsx",
                "Carrega_docent",
                [[
                    "Teacher",
                    "Subject",
                    "Student Group",
                    "Weekly Hours",
                    "Allowed Session Lengths",
                    "Preferred Room",
                    "Notes",
                ]]
                + [
                    [
                        activity["teacher"],
                        activity["subject"],
                        activity["group"],
                        activity["weekly_hours"],
                        "",
                        activity["preferred_room"],
                        "",
                    ]
                    for activity in sorted(activities, key=lambda value: (value["teacher"], value["subject"], value["group"], value["id"]))
                ],
            ),
            (
                "02_Restriccions_professors.xlsx",
                "Restriccions_prof",
                [[
                    "Teacher",
                    "Unavailable Slots",
                    "Inferred Available Slots",
                    "Editable Notes",
                ]]
                + [
                    [
                        teacher,
                        "; ".join(sorted(teacher_unavailable.get(teacher, set()))),
                        max(len(day_names) * len(hour_names) - len(teacher_unavailable.get(teacher, set())), 0),
                        "",
                    ]
                    for teacher in sorted(teacher_names)
                ],
            ),
            (
                "03_Restriccions_grups.xlsx",
                "Restriccions_grups",
                [[
                    "Student Group",
                    "Unavailable Slots",
                    "Fixed Activity Slots",
                    "Future Year Notes",
                    "Future Year Extra Restrictions",
                ]]
                + [
                    [
                        group,
                        "; ".join(sorted(group_unavailable.get(group, set()))),
                        "; ".join(sorted(group_fixed_slots.get(group, set()))),
                        "",
                        "",
                    ]
                    for group in sorted(group_names)
                ],
            ),
            (
                "04_Aules.xlsx",
                "Aules",
                [["Room", "Notes"]] + [[room, ""] for room in sorted(room_names)],
            ),
        ]

        generated_files: list[GeneratedTemplate] = []
        for filename, sheet_name, rows in file_specs:
            target = output_folder / filename
            _write_single_sheet_xlsx(target, sheet_name, rows)
            generated_files.append(GeneratedTemplate(name=filename, path=str(target)))

        return TemplateExportResult(output_folder=str(output_folder), files=generated_files)

    def _build_output_folder(self) -> Path:
        self._output_root.mkdir(parents=True, exist_ok=True)
        base_name = datetime.now().strftime("templates_%Y%m%d_%H%M%S")
        candidate = self._output_root / base_name
        suffix = 1
        while candidate.exists():
            candidate = self._output_root / f"{base_name}_{suffix}"
            suffix += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate