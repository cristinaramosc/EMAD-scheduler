from __future__ import annotations

from dataclasses import dataclass
import base64
from pathlib import PurePosixPath
import posixpath
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

if __package__ and __package__.startswith("backend"):
    from backend.repositories.academic_data_repository import AcademicDataRepository, AcademicImportReport
    from backend.services.session_decomposer import SessionDecomposer, SessionDecompositionError
else:  # pragma: no cover
    from repositories.academic_data_repository import AcademicDataRepository, AcademicImportReport
    from services.session_decomposer import SessionDecomposer, SessionDecompositionError


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS, "pkg": PACKAGE_REL_NS}


EXPECTED_FILES = {
    "01_Carrega_docent.xlsx",
    "02_Restriccions_professors.xlsx",
    "03_Restriccions_grups.xlsx",
    "04_Aules.xlsx",
}


@dataclass
class ValidationIssue:
    worksheet: str
    row: int
    column: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worksheet": self.worksheet,
            "row": self.row,
            "column": self.column,
            "message": self.message,
        }


class AcademicWorkbookImportError(Exception):
    def __init__(self, issues: List[ValidationIssue]):
        super().__init__("academic_workbook_validation_failed")
        self.issues = issues


class AcademicWorkbookImporter:
    def __init__(self, academic_data_repo: AcademicDataRepository):
        self._academic_data_repo = academic_data_repo

    def import_base64_files(self, files: List[Dict[str, str]]) -> AcademicImportReport:
        decoded_files: List[Tuple[str, bytes]] = []
        issues: List[ValidationIssue] = []

        for item in files:
            name = item.get("name", "")
            payload = item.get("workbook_base64", "")
            if not name:
                issues.append(ValidationIssue(worksheet="<request>", row=1, column="A", message="missing_file_name"))
                continue
            if not payload:
                issues.append(
                    ValidationIssue(
                        worksheet=name,
                        row=1,
                        column="A",
                        message="missing_workbook_base64_payload",
                    )
                )
                continue

            try:
                decoded = base64.b64decode(payload)
            except Exception:
                issues.append(ValidationIssue(worksheet=name, row=1, column="A", message="invalid_base64_payload"))
                continue

            decoded_files.append((name, decoded))

        if issues:
            raise AcademicWorkbookImportError(issues)

        return self.import_files(decoded_files)

    def import_files(self, files: List[Tuple[str, bytes]]) -> AcademicImportReport:
        issues: List[ValidationIssue] = []
        rows_by_file: Dict[str, List[Dict[str, Any]]] = {}
        warnings: List[str] = []

        provided_names = {name for name, _ in files}
        missing = sorted(EXPECTED_FILES - provided_names)
        extra = sorted(provided_names - EXPECTED_FILES)

        for name in missing:
            issues.append(
                ValidationIssue(
                    worksheet=name,
                    row=1,
                    column="A",
                    message="required_template_file_is_missing",
                )
            )

        for name in extra:
            warnings.append(f"ignored_non_template_file:{name}")

        for name, content in files:
            if name not in EXPECTED_FILES:
                continue
            try:
                rows_by_file[name] = self._read_first_sheet_rows(content)
            except (BadZipFile, KeyError, ET.ParseError, ValueError):
                issues.append(
                    ValidationIssue(
                        worksheet=name,
                        row=1,
                        column="A",
                        message="invalid_xlsx_file_for_academic_import",
                    )
                )

        snapshot = {
            "teachers": [],
            "groups": [],
            "subjects": [],
            "teaching_assignments": [],
            "rooms": [],
            "teacher_restrictions": [],
            "group_restrictions": [],
        }

        decomposer = SessionDecomposer()

        if "01_Carrega_docent.xlsx" in rows_by_file:
            parsed = self._parse_workload(rows_by_file["01_Carrega_docent.xlsx"], issues)
            # decompose assignments into sessions
            decomposed_assignments = []
            for assignment in parsed["assignments"]:
                weekly = assignment.get("weekly_hours")
                allowed = assignment.get("allowed_session_lengths") or []
                try:
                    sessions = decomposer.decompose(weekly, allowed)
                except SessionDecompositionError:
                    # keep as single assignment if decomposition fails (validation handled earlier)
                    sessions = [weekly]

                # produce one assignment per session so scheduler receives them as separate teaching loads
                for session_length in sessions:
                    new = dict(assignment)
                    new["weekly_hours"] = session_length
                    # indicate this is a decomposed session (for traceability)
                    new["decomposed_from_weekly"] = weekly
                    decomposed_assignments.append(new)

            snapshot["teaching_assignments"] = decomposed_assignments
            snapshot["teachers"].extend({"name": teacher} for teacher in sorted(parsed["teachers"]))
            snapshot["groups"].extend({"name": group} for group in sorted(parsed["groups"]))
            # subjects will be enriched with allowed session lengths from assignments
            snapshot["subjects"].extend({"name": subject} for subject in sorted(parsed["subjects"]))
            snapshot["rooms"].extend({"name": room} for room in sorted(parsed["rooms"]))

        if "02_Restriccions_professors.xlsx" in rows_by_file:
            parsed = self._parse_teacher_restrictions(rows_by_file["02_Restriccions_professors.xlsx"], issues)
            snapshot["teacher_restrictions"] = parsed
            snapshot["teachers"].extend({"name": record["teacher"]} for record in parsed)

        if "03_Restriccions_grups.xlsx" in rows_by_file:
            parsed = self._parse_group_restrictions(rows_by_file["03_Restriccions_grups.xlsx"], issues)
            snapshot["group_restrictions"] = parsed
            snapshot["groups"].extend({"name": record["group"]} for record in parsed)

        if "04_Aules.xlsx" in rows_by_file:
            parsed = self._parse_rooms(rows_by_file["04_Aules.xlsx"], issues)
            snapshot["rooms"].extend({"name": room} for room in sorted(parsed))

        if issues:
            raise AcademicWorkbookImportError(issues)

        snapshot["teachers"] = self._dedupe_name_records(snapshot["teachers"])
        snapshot["groups"] = self._dedupe_name_records(snapshot["groups"])
        # merge subject-level allowed session lengths from assignments
        snapshot = self._merge_subject_allowed_lengths(snapshot)
        snapshot["subjects"] = self._dedupe_name_records(snapshot["subjects"])
        snapshot["rooms"] = self._dedupe_name_records(snapshot["rooms"])

        return self._academic_data_repo.apply_snapshot(snapshot, warnings=warnings)

    def _parse_workload(self, rows: List[Dict[str, Any]], issues: List[ValidationIssue]) -> Dict[str, Any]:
        worksheet = "01_Carrega_docent.xlsx"
        header_map = self._expect_headers(
            worksheet,
            rows,
            issues,
            [
                "Teacher",
                "Subject",
                "Student Group",
                "Weekly Hours",
                "Allowed Session Lengths",
                "Preferred Room",
                "Notes",
            ],
        )
        if header_map is None:
            return {"assignments": [], "teachers": set(), "groups": set(), "subjects": set(), "rooms": set()}

        assignments: List[Dict[str, Any]] = []
        teachers: set[str] = set()
        groups: set[str] = set()
        subjects: set[str] = set()
        rooms: set[str] = set()

        for row in rows[1:]:
            values = row["values"]
            row_number = row["row_number"]
            teacher = self._cell(values, header_map, "Teacher")
            subject = self._cell(values, header_map, "Subject")
            group = self._cell(values, header_map, "Student Group")
            weekly_hours_raw = self._cell(values, header_map, "Weekly Hours")
            allowed_sessions_raw = self._cell(values, header_map, "Allowed Session Lengths")
            preferred_room = self._cell(values, header_map, "Preferred Room")

            if not any([teacher, subject, group, weekly_hours_raw, allowed_sessions_raw, preferred_room]):
                continue

            if not teacher:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Teacher"] + 1), message="teacher_is_required"))
            if not subject:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Subject"] + 1), message="subject_is_required"))
            if not group:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Student Group"] + 1), message="student_group_is_required"))

            weekly_hours = self._parse_float(weekly_hours_raw)
            if weekly_hours is None or weekly_hours <= 0:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Weekly Hours"] + 1), message="weekly_hours_must_be_a_positive_number"))

            allowed_sessions = self._parse_allowed_session_lengths(allowed_sessions_raw)
            if allowed_sessions is None:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Allowed Session Lengths"] + 1), message="invalid_allowed_session_lengths"))

            if not teacher or not subject or not group or weekly_hours is None:
                continue
            assignments.append(
                {
                    "teacher": teacher,
                    "subject": subject,
                    "group": group,
                    "weekly_hours": weekly_hours,
                    "allowed_session_lengths": allowed_sessions,
                    "preferred_room": preferred_room,
                }
            )
            teachers.add(teacher)
            groups.add(group)
            subjects.add(subject)
            if preferred_room:
                rooms.add(preferred_room)

        return {
            "assignments": assignments,
            "teachers": teachers,
            "groups": groups,
            "subjects": subjects,
            "rooms": rooms,
        }

    def _parse_teacher_restrictions(self, rows: List[Dict[str, Any]], issues: List[ValidationIssue]) -> List[Dict[str, Any]]:
        worksheet = "02_Restriccions_professors.xlsx"
        header_map = self._expect_headers(
            worksheet,
            rows,
            issues,
            ["Teacher", "Unavailable Slots", "Inferred Available Slots", "Editable Notes"],
        )
        if header_map is None:
            return []

        parsed: List[Dict[str, Any]] = []
        for row in rows[1:]:
            values = row["values"]
            row_number = row["row_number"]
            teacher = self._cell(values, header_map, "Teacher")
            unavailable = self._cell(values, header_map, "Unavailable Slots")

            if not teacher and not unavailable:
                continue
            if not teacher:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Teacher"] + 1), message="teacher_is_required"))
                continue

            parsed.append(
                {
                    "teacher": teacher,
                    "unavailable_slots": self._parse_slots(unavailable),
                }
            )
        return parsed

    def _parse_group_restrictions(self, rows: List[Dict[str, Any]], issues: List[ValidationIssue]) -> List[Dict[str, Any]]:
        worksheet = "03_Restriccions_grups.xlsx"
        header_map = self._expect_headers(
            worksheet,
            rows,
            issues,
            [
                "Student Group",
                "Unavailable Slots",
                "Fixed Activity Slots",
                "Future Year Notes",
                "Future Year Extra Restrictions",
            ],
        )
        if header_map is None:
            return []

        parsed: List[Dict[str, Any]] = []
        for row in rows[1:]:
            values = row["values"]
            row_number = row["row_number"]
            group = self._cell(values, header_map, "Student Group")
            unavailable = self._cell(values, header_map, "Unavailable Slots")
            fixed_slots = self._cell(values, header_map, "Fixed Activity Slots")

            if not group and not unavailable and not fixed_slots:
                continue
            if not group:
                issues.append(ValidationIssue(worksheet=worksheet, row=row_number, column=self._column_name(header_map["Student Group"] + 1), message="student_group_is_required"))
                continue

            parsed.append(
                {
                    "group": group,
                    "unavailable_slots": self._parse_slots(unavailable),
                    "fixed_slots": self._parse_slots(fixed_slots),
                }
            )

        return parsed

    def _parse_rooms(self, rows: List[Dict[str, Any]], issues: List[ValidationIssue]) -> set[str]:
        worksheet = "04_Aules.xlsx"
        header_map = self._expect_headers(worksheet, rows, issues, ["Room", "Notes"])
        if header_map is None:
            return set()

        rooms: set[str] = set()
        for row in rows[1:]:
            values = row["values"]
            room = self._cell(values, header_map, "Room")
            if room:
                rooms.add(room)
        return rooms

    def _expect_headers(
        self,
        worksheet: str,
        rows: List[Dict[str, Any]],
        issues: List[ValidationIssue],
        expected: List[str],
    ) -> Dict[str, int] | None:
        if not rows:
            issues.append(ValidationIssue(worksheet=worksheet, row=1, column="A", message="worksheet_is_empty"))
            return None

        header_values = [str(value).strip() for value in rows[0]["values"]]
        mapping: Dict[str, int] = {}
        for expected_name in expected:
            try:
                mapping[expected_name] = header_values.index(expected_name)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        worksheet=worksheet,
                        row=1,
                        column="A",
                        message=f"missing_expected_header:{expected_name}",
                    )
                )

        if any(issue.worksheet == worksheet and issue.row == 1 for issue in issues):
            return None
        return mapping

    def _read_first_sheet_rows(self, workbook_bytes: bytes) -> List[Dict[str, Any]]:
        with ZipFile(self._bytes_to_io(workbook_bytes)) as archive:
            shared_strings = self._read_shared_strings(archive)
            worksheet_path = self._first_worksheet_path(archive)
            root = ET.fromstring(archive.read(worksheet_path))
            rows: List[Dict[str, Any]] = []

            for row in root.findall("main:sheetData/main:row", NS):
                row_number = int(row.attrib.get("r", len(rows) + 1))
                values: List[Any] = []

                for cell in row.findall("main:c", NS):
                    reference = cell.attrib.get("r")
                    if not reference:
                        continue
                    column_index = self._column_index(reference)
                    while len(values) < column_index - 1:
                        values.append("")
                    values.append(self._read_cell_value(cell, shared_strings))

                rows.append({"row_number": row_number, "values": values})
        return rows

    def _read_shared_strings(self, archive: ZipFile) -> List[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []

        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings: List[str] = []
        for item in root.findall("main:si", NS):
            text_nodes = item.findall(".//main:t", NS)
            strings.append("".join(node.text or "" for node in text_nodes))
        return strings

    def _dedupe_name_records(self, rows: List[Record]) -> List[Record]:
        seen = {}
        for row in rows:
            key = row["name"].strip().lower()
            if not key:
                continue
            existing = seen.get(key)
            if existing is None:
                seen[key] = dict(row)
                # ensure name is stripped
                seen[key]["name"] = row["name"].strip()
                # normalize allowed_session_lengths to list if present
                if "allowed_session_lengths" in seen[key] and seen[key]["allowed_session_lengths"] is None:
                    seen[key]["allowed_session_lengths"] = []
            else:
                # merge allowed_session_lengths if present
                a = existing.get("allowed_session_lengths") or []
                b = row.get("allowed_session_lengths") or []
                merged = sorted({float(x) for x in list(a) + list(b)}) if (a or b) else []
                if merged:
                    existing["allowed_session_lengths"] = merged

                existing_weekly = existing.get("weekly_hours")
                incoming_weekly = row.get("weekly_hours")
                if incoming_weekly is not None:
                    if existing_weekly is None:
                        existing["weekly_hours"] = float(incoming_weekly)
                    else:
                        existing["weekly_hours"] = round(float(existing_weekly) + float(incoming_weekly), 2)

        output = list(sorted(seen.values(), key=lambda r: r["name"]))
        return output

    def _parse_allowed_session_lengths(self, value: str) -> List[float] | None:
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        parts = [p.strip() for p in text.split(",") if p.strip()]
        result: List[float] = []
        for part in parts:
            try:
                num = float(str(part).strip())
            except ValueError:
                return None
            if num <= 0:
                return None
            result.append(num)
        return result

    def _merge_subject_allowed_lengths(self, snapshot: Dict[str, List[Record]]) -> Dict[str, List[Record]]:
        # build mapping from subject name -> allowed lengths and weekly hours from assignments
        subject_lengths: Dict[str, List[float]] = {}
        subject_hours: Dict[str, float] = {}
        for assignment in snapshot.get("teaching_assignments", []):
            subj = assignment.get("subject")
            lengths = assignment.get("allowed_session_lengths") or []
            weekly = assignment.get("weekly_hours")
            if subj:
                key = subj.strip().lower()
                existing_lengths = subject_lengths.get(key) or []
                subject_lengths[key] = sorted({*existing_lengths, *([float(x) for x in lengths] if lengths else [])})
                if weekly is not None:
                    try:
                        subject_hours[key] = round(subject_hours.get(key, 0.0) + float(weekly), 2)
                    except (TypeError, ValueError):
                        pass

        # enrich subject records
        enriched_subjects: List[Record] = []
        for subj in snapshot.get("subjects", []):
            name = subj.get("name", "").strip()
            key = name.lower()
            record = {"name": name}
            if key in subject_lengths and subject_lengths[key]:
                record["allowed_session_lengths"] = subject_lengths[key]
            if key in subject_hours and subject_hours[key] > 0:
                record["weekly_hours"] = subject_hours[key]
            elif subj.get("weekly_hours") is not None:
                record["weekly_hours"] = subj["weekly_hours"]
            enriched_subjects.append(record)

        snapshot["subjects"] = enriched_subjects
        return snapshot

    def _first_worksheet_path(self, archive: ZipFile) -> str:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

        relations = {
            relation.attrib["Id"]: self._relationship_target("xl", relation.attrib["Target"])
            for relation in rels.findall("pkg:Relationship", NS)
        }

        sheets = workbook.findall("main:sheets/main:sheet", NS)
        if not sheets:
            raise ValueError("no_worksheets_found")

        first = sheets[0]
        relation_id = first.attrib.get(f"{{{REL_NS}}}id")
        if relation_id is None or relation_id not in relations:
            raise ValueError("worksheet_relationship_not_found")

        return relations[relation_id]

    def _relationship_target(self, base_dir: str, target: str) -> str:
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join(base_dir, target))

    def _read_cell_value(self, cell: ET.Element, shared_strings: List[str]) -> Any:
        cell_type = cell.attrib.get("t")
        value_node = cell.find("main:v", NS)

        if cell_type == "inlineStr":
            text_nodes = cell.findall("main:is/main:t", NS)
            return "".join(node.text or "" for node in text_nodes)

        if value_node is None:
            return ""

        raw_value = value_node.text or ""
        if cell_type == "s":
            return shared_strings[int(raw_value)]

        return raw_value

    def _column_index(self, cell_reference: str) -> int:
        letters = ""
        for character in cell_reference:
            if character.isalpha():
                letters += character.upper()
            else:
                break

        total = 0
        for character in letters:
            total = total * 26 + (ord(character) - ord("A") + 1)
        return total

    def _column_name(self, index: int) -> str:
        name = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            name = chr(ord("A") + remainder) + name
        return name

    def _cell(self, values: List[Any], header_map: Dict[str, int], header_name: str) -> str:
        index = header_map[header_name]
        if index >= len(values):
            return ""
        return str(values[index]).strip()

    def _parse_float(self, value: str) -> float | None:
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_int(self, value: str) -> int | None:
        number = self._parse_float(value)
        if number is None:
            return None
        if not number.is_integer():
            return None
        return int(number)

    def _parse_slots(self, value: str) -> List[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(";") if item.strip()]

    def _dedupe_name_records(self, rows: List[Record]) -> List[Record]:
        seen = {}
        for row in rows:
            key = row["name"].strip().lower()
            if not key:
                continue
            existing = seen.get(key)
            if existing is None:
                seen[key] = dict(row)
                # ensure name is stripped
                seen[key]["name"] = row["name"].strip()
                # normalize allowed_session_lengths to list if present
                if "allowed_session_lengths" in seen[key] and seen[key]["allowed_session_lengths"] is None:
                    seen[key]["allowed_session_lengths"] = []
            else:
                # merge allowed_session_lengths if present
                a = existing.get("allowed_session_lengths") or []
                b = row.get("allowed_session_lengths") or []
                merged = sorted({float(x) for x in list(a) + list(b)}) if (a or b) else []
                if merged:
                    existing["allowed_session_lengths"] = merged

                existing_weekly = existing.get("weekly_hours")
                incoming_weekly = row.get("weekly_hours")
                if incoming_weekly is not None:
                    if existing_weekly is None:
                        existing["weekly_hours"] = float(incoming_weekly)
                    else:
                        existing["weekly_hours"] = round(float(existing_weekly) + float(incoming_weekly), 2)

        output = list(sorted(seen.values(), key=lambda r: r["name"]))
        return output

    def _bytes_to_io(self, payload: bytes):
        try:
            from io import BytesIO

            return BytesIO(payload)
        except Exception as exc:  # pragma: no cover
            raise ValueError("unable_to_read_xlsx_payload") from exc
