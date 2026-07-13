from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS, "pkg": PACKAGE_REL_NS}


def _normalize_text(value: object) -> str:
    if value is None:
        return ""

    normalized = unicodedata.normalize("NFKD", str(value).strip().lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _clean_value(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _parse_number(value: object) -> float | None:
    if value is None:
        return None

    text = str(value).strip().replace(",", ".")
    if not text:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    return int(number) if number.is_integer() else number


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


def _relationship_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(base_dir, target))


def _is_total_like_row(values: list[object]) -> bool:
    joined = " ".join(_normalize_text(value) for value in values if value not in (None, ""))
    return any(marker in joined for marker in ("total", "subtotal", "sum", "resum"))


@dataclass
class WorksheetAnalysis:
    name: str
    total_rows: int
    header_row: int | None
    detected_columns: dict[str, str] = field(default_factory=dict)
    assignments_detected: int = 0
    ignored_rows: int = 0
    skipped_rows: int = 0


@dataclass
class TeachingAssignmentDetection:
    worksheet: str
    row_number: int
    teacher: str
    group: str
    subject: str
    annual_hours: float | int | None


@dataclass
class WorkbookAnalysis:
    workbook_path: str
    workbook_type: str
    worksheet_names: list[str]
    worksheets: list[WorksheetAnalysis]
    teachers: list[str]
    groups: list[str]
    subjects: list[str]
    teaching_assignments: list[TeachingAssignmentDetection]
    annual_hours_total: float
    annual_hours_entries: int
    warnings: list[str]
    errors: list[str]

    @property
    def summary(self) -> str:
        status = "Workbook analysed successfully" if not self.errors else "Workbook analysed with errors"
        lines = [
            status,
            f"Worksheets detected: {len(self.worksheet_names)}",
            f"Teachers detected: {len(self.teachers)}",
            f"Groups detected: {len(self.groups)}",
            f"Subjects detected: {len(self.subjects)}",
            f"Teaching assignments detected: {len(self.teaching_assignments)}",
            f"Annual hour entries detected: {self.annual_hours_entries}",
            f"Annual hours total: {self.annual_hours_total}",
        ]

        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)

        if self.errors:
            lines.append("Errors:")
            lines.extend(f"- {error}" for error in self.errors)

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "workbook_path": self.workbook_path,
            "workbook_type": self.workbook_type,
            "worksheet_names": self.worksheet_names,
            "worksheets": [asdict(worksheet) for worksheet in self.worksheets],
            "teachers": self.teachers,
            "groups": self.groups,
            "subjects": self.subjects,
            "teaching_assignments": [asdict(assignment) for assignment in self.teaching_assignments],
            "counts": {
                "worksheets": len(self.worksheet_names),
                "teachers": len(self.teachers),
                "groups": len(self.groups),
                "subjects": len(self.subjects),
                "teaching_assignments": len(self.teaching_assignments),
                "annual_hours_entries": self.annual_hours_entries,
            },
            "annual_hours_total": self.annual_hours_total,
            "warnings": self.warnings,
            "errors": self.errors,
            "summary": self.summary,
        }


class ExcelWorkbookAnalyzer:
    HEADER_PATTERNS = {
        "group": (
            "group",
            "grup",
            "classe",
            "class",
            "curs",
            "course",
            "nivell",
        ),
        "teacher": (
            "teacher",
            "professor",
            "professora",
            "prof",
            "docent",
        ),
        "subject": (
            "subject",
            "assignatura",
            "materia",
            "modul",
            "module",
            "especialitat",
        ),
        "annual_hours": (
            "annual hours",
            "hores anuals",
            "hores totals",
            "total hours",
            "total hores",
            "hores curs",
            "hores any",
            "anual",
        ),
    }

    SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}

    def analyze(self, workbook_path: str | Path) -> WorkbookAnalysis:
        path = Path(workbook_path)
        warnings: list[str] = []
        errors: list[str] = []

        if not path.exists():
            errors.append(f"Workbook file not found: {path}")
            return self._empty_analysis(path, errors=errors)

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            errors.append(
                f"Unsupported workbook format '{path.suffix or '<none>'}'. Supported formats: .xlsx, .xlsm"
            )
            return self._empty_analysis(path, errors=errors)

        try:
            workbook = _XlsxWorkbookReader(path).read()
        except (BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
            errors.append(f"Workbook could not be parsed: {exc}")
            return self._empty_analysis(path, errors=errors)

        worksheet_analyses: list[WorksheetAnalysis] = []
        teachers: set[str] = set()
        groups: set[str] = set()
        subjects: set[str] = set()
        teaching_assignments: list[TeachingAssignmentDetection] = []
        annual_hours_total = 0.0
        annual_hours_entries = 0

        for worksheet in workbook["worksheets"]:
            worksheet_result = self._analyse_worksheet(worksheet)
            worksheet_analyses.append(worksheet_result["worksheet_analysis"])
            warnings.extend(worksheet_result["warnings"])

            for assignment in worksheet_result["assignments"]:
                teachers.add(assignment.teacher)
                groups.add(assignment.group)
                subjects.add(assignment.subject)
                teaching_assignments.append(assignment)

                if assignment.annual_hours is not None:
                    annual_hours_total += float(assignment.annual_hours)
                    annual_hours_entries += 1

        if not teaching_assignments:
            warnings.append(
                "No teaching assignments were detected. The workbook may use different headers or a more complex layout than the current heuristics support."
            )

        return WorkbookAnalysis(
            workbook_path=str(path),
            workbook_type=path.suffix.lower().lstrip("."),
            worksheet_names=[worksheet["name"] for worksheet in workbook["worksheets"]],
            worksheets=worksheet_analyses,
            teachers=sorted(teachers),
            groups=sorted(groups),
            subjects=sorted(subjects),
            teaching_assignments=teaching_assignments,
            annual_hours_total=annual_hours_total,
            annual_hours_entries=annual_hours_entries,
            warnings=warnings,
            errors=errors,
        )

    def _analyse_worksheet(self, worksheet: dict) -> dict:
        name = worksheet["name"]
        rows = worksheet["rows"]
        header_row_number, mapping = self._detect_header_mapping(rows)
        warnings: list[str] = []
        assignments: list[TeachingAssignmentDetection] = []

        worksheet_analysis = WorksheetAnalysis(
            name=name,
            total_rows=len(rows),
            header_row=header_row_number,
        )

        if header_row_number is None or not mapping:
            warnings.append(f"Worksheet '{name}' does not expose a recognizable teaching-load table.")
            return {
                "worksheet_analysis": worksheet_analysis,
                "assignments": assignments,
                "warnings": warnings,
            }

        worksheet_analysis.detected_columns = {
            logical_name: str(rows[header_row_number - 1]["values"][index]).strip()
            for logical_name, index in mapping.items()
        }

        required = {"teacher", "group", "subject"}
        missing_required = sorted(required - set(mapping))
        if missing_required:
            warnings.append(
                f"Worksheet '{name}' is missing required columns for assignments: {', '.join(missing_required)}."
            )
            return {
                "worksheet_analysis": worksheet_analysis,
                "assignments": assignments,
                "warnings": warnings,
            }

        last_seen: dict[str, str] = {}
        skipped_rows = 0
        ignored_rows = 0

        for row in rows:
            if row["row_number"] <= header_row_number:
                continue

            values = row["values"]
            if _is_total_like_row(values):
                ignored_rows += 1
                continue

            raw_record = {key: _clean_value(values[index]) if index < len(values) else None for key, index in mapping.items()}
            populated_raw = {key: value for key, value in raw_record.items() if value}
            if not populated_raw:
                continue

            effective_record: dict[str, str | None] = {}
            for key in ("teacher", "group", "subject"):
                current_value = raw_record.get(key)
                if current_value:
                    last_seen[key] = current_value
                effective_record[key] = current_value or last_seen.get(key)

            annual_hours = _parse_number(raw_record.get("annual_hours"))

            if not all(effective_record.get(field) for field in ("teacher", "group", "subject")):
                skipped_rows += 1
                continue

            assignments.append(
                TeachingAssignmentDetection(
                    worksheet=name,
                    row_number=row["row_number"],
                    teacher=effective_record["teacher"],
                    group=effective_record["group"],
                    subject=effective_record["subject"],
                    annual_hours=annual_hours,
                )
            )

        worksheet_analysis.assignments_detected = len(assignments)
        worksheet_analysis.skipped_rows = skipped_rows
        worksheet_analysis.ignored_rows = ignored_rows

        if skipped_rows:
            warnings.append(
                f"Worksheet '{name}' skipped {skipped_rows} populated rows because at least one of teacher, group or subject could not be resolved."
            )

        if "annual_hours" not in mapping:
            warnings.append(f"Worksheet '{name}' does not expose an annual-hours column.")

        return {
            "worksheet_analysis": worksheet_analysis,
            "assignments": assignments,
            "warnings": warnings,
        }

    def _detect_header_mapping(self, rows: list[dict]) -> tuple[int | None, dict[str, int]]:
        best_row_number: int | None = None
        best_mapping: dict[str, int] = {}
        best_score = -1

        for row in rows[:25]:
            mapping = self._map_header_row(row["values"])
            score = len(mapping)
            if score > best_score:
                best_score = score
                best_row_number = row["row_number"]
                best_mapping = mapping

        if best_score < 2:
            return None, {}

        return best_row_number, best_mapping

    def _map_header_row(self, values: list[object]) -> dict[str, int]:
        mapping: dict[str, int] = {}

        for index, value in enumerate(values):
            normalized = _normalize_text(value)
            if not normalized:
                continue

            for logical_name, patterns in self.HEADER_PATTERNS.items():
                if logical_name in mapping:
                    continue
                if any(pattern == normalized or pattern in normalized for pattern in patterns):
                    mapping[logical_name] = index
                    break

        return mapping

    def _empty_analysis(self, path: Path, errors: list[str]) -> WorkbookAnalysis:
        return WorkbookAnalysis(
            workbook_path=str(path),
            workbook_type=path.suffix.lower().lstrip("."),
            worksheet_names=[],
            worksheets=[],
            teachers=[],
            groups=[],
            subjects=[],
            teaching_assignments=[],
            annual_hours_total=0.0,
            annual_hours_entries=0,
            warnings=[],
            errors=errors,
        )


class _XlsxWorkbookReader:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> dict:
        with ZipFile(self._path) as archive:
            shared_strings = self._read_shared_strings(archive)
            sheet_refs = self._read_sheet_refs(archive)
            worksheets = []
            for name, target in sheet_refs:
                worksheets.append(
                    {
                        "name": name,
                        "rows": self._read_worksheet_rows(archive, target, shared_strings),
                    }
                )
        return {"worksheets": worksheets}

    def _read_shared_strings(self, archive: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []

        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings: list[str] = []
        for item in root.findall("main:si", NS):
            texts = [node.text or "" for node in item.findall(".//main:t", NS)]
            strings.append("".join(texts))
        return strings

    def _read_sheet_refs(self, archive: ZipFile) -> list[tuple[str, str]]:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relations = {
            relation.attrib["Id"]: _relationship_target("xl", relation.attrib["Target"])
            for relation in rel_root.findall("pkg:Relationship", NS)
        }

        sheets: list[tuple[str, str]] = []
        for sheet in workbook_root.findall("main:sheets/main:sheet", NS):
            relation_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            if relation_id is None or relation_id not in relations:
                raise ValueError(f"Worksheet relationship not found for sheet '{sheet.attrib.get('name', '<unknown>')}'")
            sheets.append((sheet.attrib["name"], relations[relation_id]))
        return sheets

    def _read_worksheet_rows(self, archive: ZipFile, worksheet_path: str, shared_strings: list[str]) -> list[dict]:
        worksheet_root = ET.fromstring(archive.read(worksheet_path))
        rows: list[dict] = []

        for row in worksheet_root.findall("main:sheetData/main:row", NS):
            row_number = int(row.attrib.get("r", len(rows) + 1))
            values: list[object] = []
            for cell in row.findall("main:c", NS):
                reference = cell.attrib.get("r")
                if not reference:
                    continue

                cell_index = _column_index(reference)
                while len(values) < cell_index - 1:
                    values.append(None)
                values.append(self._read_cell_value(cell, shared_strings))

            rows.append({"row_number": row_number, "values": values})

        return rows

    def _read_cell_value(self, cell: ET.Element, shared_strings: list[str]) -> object:
        cell_type = cell.attrib.get("t")
        value_node = cell.find("main:v", NS)

        if cell_type == "inlineStr":
            text_nodes = cell.findall("main:is/main:t", NS)
            return "".join(node.text or "" for node in text_nodes)

        if value_node is None:
            return None

        raw_value = value_node.text or ""
        if cell_type == "s":
            return shared_strings[int(raw_value)]
        if cell_type == "b":
            return raw_value == "1"

        if re.fullmatch(r"-?\d+(\.\d+)?", raw_value):
            number = float(raw_value)
            return int(number) if number.is_integer() else number

        return raw_value