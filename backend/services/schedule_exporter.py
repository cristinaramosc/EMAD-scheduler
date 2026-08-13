"""Exporta l'horari actiu (o una proposta) a un únic fitxer Excel amb una
pestanya per a cada grup, professor i aula.

No depèn de cap repositori de calendari: dedueix l'ordre dels dies a partir
d'una llista coneguda de noms en català, i l'ordre de les hores parsejant
directament el text ("8:00", "8:30"...). Si algun dia/hora no coincideix amb
el format esperat, simplement es col·loca al final, ordenat alfabèticament,
en lloc de fallar.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

def _split_group_names(group_text: str) -> List[str]:
    """Separa un camp de grup que pot contenir diversos grups per coma
    (p.ex. 'GI, GP'), preservant el text original (majúscules incloses)
    per mostrar-lo bé al nom de la pestanya."""
    if not group_text:
        return []
    parts = [part.strip() for part in str(group_text).split(",")]
    unique: List[str] = []
    seen = set()
    for part in parts:
        key = part.casefold()
        if part and key not in seen:
            seen.add(key)
            unique.append(part)
    return unique

_DAY_ORDER = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]

_HEADER_FILL = PatternFill(start_color="FF2F3B52", end_color="FF2F3B52", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)
_CELL_FONT = Font(size=10)
_CELL_BORDER = Border(*(Side(style="thin", color="FFD9D9D9"),) * 4)
_WRAP = Alignment(wrap_text=True, vertical="top", horizontal="left")
_CENTER = Alignment(horizontal="center", vertical="center")


def _day_sort_key(day_name: str):
    normalized = str(day_name or "").strip().lower()
    try:
        return (0, _DAY_ORDER.index(normalized))
    except ValueError:
        return (1, normalized)


def _hour_sort_key(hour_label: str):
    match = re.match(r"\s*(\d+):(\d+)", str(hour_label or ""))
    if match:
        return (0, int(match.group(1)) * 60 + int(match.group(2)))
    return (1, str(hour_label or ""))


def _cell_text(activity: Dict[str, Any]) -> str:
    parts = [activity.get("subject") or ""]
    extra = " · ".join(part for part in [activity.get("teacher"), activity.get("room")] if part)
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def _collect_axes(activities: Sequence[Dict[str, Any]]) -> tuple[List[str], List[str]]:
    days = sorted({a.get("day") for a in activities if a.get("day")}, key=_day_sort_key)
    hours = sorted({a.get("start") for a in activities if a.get("start")}, key=_hour_sort_key)
    return days, hours


def _write_grid_sheet(workbook: Workbook, title: str, activities: List[Dict[str, Any]]) -> None:
    # Els noms de fulla d'Excel no poden superar 31 caràcters ni contenir
    # certs símbols; es netegen per evitar que openpyxl exploti.
    safe_title = re.sub(r"[\\/*?:\[\]]", " ", title).strip()[:31] or "Horari"
    base_title = safe_title
    suffix = 1
    existing_titles = {sheet.title for sheet in workbook.worksheets}
    while safe_title in existing_titles:
        suffix += 1
        safe_title = f"{base_title[:28]} ({suffix})"

    sheet = workbook.create_sheet(title=safe_title)

    days, hours = _collect_axes(activities)
    if not days or not hours:
        sheet.cell(row=1, column=1, value="Sense activitats programades.")
        return

    sheet.cell(row=1, column=1, value="Hora")
    for col_index, day in enumerate(days, start=2):
        cell = sheet.cell(row=1, column=col_index, value=day.capitalize())
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
    sheet.cell(row=1, column=1).fill = _HEADER_FILL
    sheet.cell(row=1, column=1).font = _HEADER_FONT
    sheet.cell(row=1, column=1).alignment = _CENTER

    grid: Dict[tuple, List[str]] = {}
    for activity in activities:
        key = (activity.get("day"), activity.get("start"))
        grid.setdefault(key, []).append(_cell_text(activity))

    for row_index, hour in enumerate(hours, start=2):
        hour_cell = sheet.cell(row=row_index, column=1, value=hour)
        hour_cell.font = Font(bold=True, size=10)
        hour_cell.alignment = _CENTER
        hour_cell.border = _CELL_BORDER

        for col_index, day in enumerate(days, start=2):
            texts = grid.get((day, hour), [])
            cell = sheet.cell(row=row_index, column=col_index, value="\n\n".join(texts) if texts else "")
            cell.font = _CELL_FONT
            cell.alignment = _WRAP
            cell.border = _CELL_BORDER

    sheet.column_dimensions["A"].width = 9
    for col_index in range(2, len(days) + 2):
        sheet.column_dimensions[get_column_letter(col_index)].width = 26
    for row_index in range(2, len(hours) + 2):
        sheet.row_dimensions[row_index].height = 42
    sheet.freeze_panes = "B2"


def build_schedule_export(activities: Sequence[Dict[str, Any]]) -> BytesIO:
    """Retorna un .xlsx (com a BytesIO) amb una pestanya per a cada grup
    pare, professor i aula que apareguin a `activities`. Els grups
    combinats (p.ex. 'GI, GP') generen una pestanya per a cada grup
    individual, amb les mateixes activitats repetides a totes dues."""
    workbook = Workbook()
    workbook.remove(workbook.active)

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    by_teacher: Dict[str, List[Dict[str, Any]]] = {}
    by_room: Dict[str, List[Dict[str, Any]]] = {}

    for activity in activities:
        for name in _split_group_names(activity.get("group") or ""):
            by_group.setdefault(name, []).append(activity)

        teacher_text = (activity.get("teacher") or "").strip()
        for teacher in [part.strip() for part in teacher_text.split(",") if part.strip()]:
            by_teacher.setdefault(teacher, []).append(activity)

        room_text = (activity.get("room") or "").strip()
        if room_text:
            by_room.setdefault(room_text, []).append(activity)

    for group_name in sorted(by_group):
        _write_grid_sheet(workbook, f"G-{group_name}", by_group[group_name])
    for teacher_name in sorted(by_teacher):
        _write_grid_sheet(workbook, f"P-{teacher_name}", by_teacher[teacher_name])
    for room_name in sorted(by_room):
        _write_grid_sheet(workbook, f"A-{room_name}", by_room[room_name])

    if not workbook.worksheets:
        workbook.create_sheet(title="Horari").cell(row=1, column=1, value="No hi ha cap activitat programada.")

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer
