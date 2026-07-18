from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from backend.services.excel_template_exporter import ExcelTemplateExporter
from backend.services.fet_importer import load_activities


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


def test_exporter_generates_all_excel_templates_from_fet(tmp_path: Path) -> None:
    fet_path = tmp_path / "sample.fet"
    fet_path.write_text(
        """<?xml version='1.0' encoding='UTF-8'?>
<fet>
  <Days_List>
    <Number_of_Days>2</Number_of_Days>
    <Day><Name>Dilluns</Name></Day>
    <Day><Name>Dimarts</Name></Day>
  </Days_List>
  <Hours_List>
    <Number_of_Hours>2</Number_of_Hours>
    <Hour><Name>8:00</Name></Hour>
    <Hour><Name>8:30</Name></Hour>
  </Hours_List>
  <Teachers_List>
    <Teacher><Name>Ada</Name></Teacher>
    <Teacher><Name>Alan</Name></Teacher>
  </Teachers_List>
  <Rooms_List>
    <Room><Name>A-01</Name></Room>
    <Room><Name>B-02</Name></Room>
  </Rooms_List>
  <Activities_List>
    <Activity>
      <Teacher>Ada</Teacher>
      <Subject>Disseny</Subject>
      <Students>1A</Students>
      <Duration>2</Duration>
      <Total_Duration>2</Total_Duration>
      <Id>10</Id>
      <Activity_Group_Id>0</Activity_Group_Id>
      <Active>true</Active>
    </Activity>
    <Activity>
      <Teacher>Alan</Teacher>
      <Subject>Tipografia</Subject>
      <Students>2B</Students>
      <Duration>1</Duration>
      <Total_Duration>1</Total_Duration>
      <Id>11</Id>
      <Activity_Group_Id>0</Activity_Group_Id>
      <Active>true</Active>
    </Activity>
  </Activities_List>
  <Time_Constraints_List>
    <ConstraintActivityPreferredStartingTime>
      <Weight_Percentage>100</Weight_Percentage>
      <Activity_Id>10</Activity_Id>
      <Preferred_Day>Dilluns</Preferred_Day>
      <Preferred_Hour>8:00</Preferred_Hour>
      <Permanently_Locked>true</Permanently_Locked>
      <Active>true</Active>
      <Day>Dilluns</Day>
      <Hour>8:00</Hour>
    </ConstraintActivityPreferredStartingTime>
    <ConstraintActivityPreferredRoom>
      <Weight_Percentage>100</Weight_Percentage>
      <Activity_Id>10</Activity_Id>
      <Room>A-01</Room>
      <Permanently_Locked>true</Permanently_Locked>
      <Active>true</Active>
    </ConstraintActivityPreferredRoom>
    <ConstraintTeacherNotAvailableTimes>
      <Weight_Percentage>100</Weight_Percentage>
      <Teacher>Ada</Teacher>
      <Number_of_Not_Available_Times>1</Number_of_Not_Available_Times>
      <Not_Available_Time>
        <Day>Dimarts</Day>
        <Hour>8:30</Hour>
      </Not_Available_Time>
      <Active>true</Active>
    </ConstraintTeacherNotAvailableTimes>
    <ConstraintStudentsSetNotAvailableTimes>
      <Weight_Percentage>100</Weight_Percentage>
      <Students>1A</Students>
      <Number_of_Not_Available_Times>1</Number_of_Not_Available_Times>
      <Not_Available_Time>
        <Day>Dilluns</Day>
        <Hour>8:30</Hour>
      </Not_Available_Time>
      <Active>true</Active>
    </ConstraintStudentsSetNotAvailableTimes>
  </Time_Constraints_List>
</fet>
""",
        encoding="utf-8",
    )

    exporter = ExcelTemplateExporter(fet_file=fet_path, output_root=tmp_path / "exports")
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

    group_rows = _read_rows(workbook_map["03_Restriccions_grups.xlsx"])
    groups = {row[0] for row in group_rows[1:]}
    assert {"1A", "2B"}.issubset(groups)

    room_rows = _read_rows(workbook_map["04_Aules.xlsx"])
    rooms = {row[0] for row in room_rows[1:]}
    assert rooms == {"A-01", "B-02"}


def test_exported_templates_match_official_fet_entities(tmp_path: Path) -> None:
    fet_path = Path(__file__).resolve().parents[2] / "EMAD_2627_.fet"

    exporter = ExcelTemplateExporter(fet_file=fet_path, output_root=tmp_path / "exports")
    result = exporter.export_templates()
    workbook_map = {file.name: Path(file.path) for file in result.files}

    activities = load_activities(fet_path)
    expected_teachers = {item["teacher"] for item in activities if item["teacher"]}
    expected_subjects = {item["subject"] for item in activities if item["subject"]}
    expected_groups = {item["group_name"] for item in activities if item["group_name"]}

    fet_root = ET.parse(fet_path).getroot()
    expected_rooms = {
        room
        for room in (node.findtext("Name") for node in fet_root.findall("./Rooms_List/Room"))
        if room
    }

    load_rows = _read_rows(workbook_map["01_Carrega_docent.xlsx"])
    exported_teachers = {row[0] for row in load_rows[1:] if row and row[0]}
    exported_subjects = {row[1] for row in load_rows[1:] if len(row) > 1 and row[1]}
    exported_groups = {row[2] for row in load_rows[1:] if len(row) > 2 and row[2]}

    room_rows = _read_rows(workbook_map["04_Aules.xlsx"])
    exported_rooms = {row[0] for row in room_rows[1:] if row and row[0]}

    assert exported_teachers == expected_teachers
    assert exported_subjects == expected_subjects
    assert exported_groups == expected_groups
    assert exported_rooms == expected_rooms
