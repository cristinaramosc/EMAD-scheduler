from openpyxl import load_workbook

from backend.services.academic_workbook_spreadsheet import build_workbook


def test_academic_workbook_teacher_and_group_columns_match_expected_model():
    buffer = build_workbook(repo=None, blank=True)
    workbook = load_workbook(buffer)

    teacher_headers = [cell.value for cell in workbook["Professors"][2]]
    group_headers = [cell.value for cell in workbook["Grups"][2]]

    assert "Nom" in teacher_headers
    assert "Hores de centre" in teacher_headers
    assert "Coordinació (nom)" in teacher_headers
    assert "Coordinació (hores)" in teacher_headers
    assert "Disponibilitat preferida (franges separades per comes)" not in teacher_headers

    assert "Nom del grup" in group_headers
    assert "Mínim d'hores diàries" in group_headers
    assert "Disponibilitat preferida (franges separades per comes)" in group_headers
