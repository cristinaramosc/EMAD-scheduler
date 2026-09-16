"""Exporta l'horari actiu a un únic PDF amb una pàgina per a cada grup,
professor i aula, amb un aspecte visual proper al calendari del frontend:
graella per mitges hores i blocs blaus per a les activitats (text blanc a
dins). La resta d'informació del document (títol, capçaleres, hores) es
mostra en negre.

Reutilitza la lògica d'agrupació (grups combinats per coma, Tutoria) del
mateix mòdul que genera l'Excel, per no duplicar-la.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if __package__ and __package__.startswith("backend"):
    from backend.services.schedule_exporter import (
        _LOGO_PATH,
        _day_sort_key,
        _hour_sort_key,
        _is_tutoria,
        _split_group_names,
        _tutoria_note,
    )
else:  # pragma: no cover
    from services.schedule_exporter import (
        _LOGO_PATH,
        _day_sort_key,
        _hour_sort_key,
        _is_tutoria,
        _split_group_names,
        _tutoria_note,
    )

_HEADER_LABELS = {"group": "Grup", "teacher": "Professor", "room": "Aula"}
_WEEKDAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]

_PAGE_SIZE = A4
_MARGIN = 14 * mm
_LOGO_WIDTH = 28 * mm
_ROW_HEIGHT = 14 * mm
_HEADER_ROW_HEIGHT = 9 * mm
_HOUR_COL_WIDTH = 18 * mm

_NAVY = colors.HexColor("#2D3561")
_TITLE_LILAC = colors.HexColor("#9AA0C8")
_TEXT = colors.HexColor("#1A1A2E")
_GRID_LINE = colors.HexColor("#D9DCE8")
_GRID_BACKGROUND = colors.HexColor("#FCFCFE")

_TITLE_STYLE = ParagraphStyle(
    "Title", fontName="Helvetica-Bold", fontSize=28, textColor=_TITLE_LILAC, alignment=TA_LEFT, leading=30
)
_YEAR_STYLE = ParagraphStyle(
    "Year", fontName="Helvetica-Bold", fontSize=13, textColor=_TITLE_LILAC, alignment=TA_LEFT, leading=15
)
_HEADER_CELL_STYLE = ParagraphStyle(
    "HeaderCell", fontName="Helvetica-Bold", fontSize=9, textColor=_TEXT, alignment=TA_CENTER, leading=11
)
_HOUR_CELL_STYLE = ParagraphStyle(
    "HourCell", fontName="Helvetica", fontSize=8.5, textColor=_TEXT, alignment=TA_RIGHT, leading=10
)
_EMPTY_MESSAGE_STYLE = ParagraphStyle(
    "Empty", fontName="Helvetica-Oblique", fontSize=10, textColor=_TEXT, alignment=TA_LEFT
)
_ACTIVITY_SUBJECT_STYLE = ParagraphStyle(
    "ActivitySubject", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, alignment=TA_LEFT, leading=10
)
_ACTIVITY_TEACHER_STYLE = ParagraphStyle(
    "ActivityTeacher", fontName="Helvetica", fontSize=7.5, textColor=colors.white, alignment=TA_RIGHT, leading=9
)
_META_STYLE = ParagraphStyle(
    "Meta", fontName="Helvetica", fontSize=9, textColor=_TEXT, alignment=TA_LEFT, leading=12
)


def _clean_text(value: Any) -> str:
    from xml.sax.saxutils import escape

    return escape(str(value or "").strip())


def _is_tutor_activity(activity: Dict[str, Any]) -> bool:
    return bool(activity.get("is_tutor") or activity.get("tutor"))


def _tutor_name(activity: Dict[str, Any]) -> str:
    explicit = activity.get("tutor_name") or activity.get("tutor")
    if isinstance(explicit, str) and explicit.strip() and explicit.strip().casefold() not in {"true", "false"}:
        return explicit.strip()
    if _is_tutor_activity(activity):
        return (activity.get("teacher") or "").strip()
    return ""


def _page_metadata(sheet_kind: str, display_name: str, activities: Sequence[Dict[str, Any]], notes: List[str]) -> Tuple[str, str, str, str]:
    group = display_name if sheet_kind == "group" else next((str(a.get("group") or "").strip() for a in activities if a.get("group")), "")
    rooms = sorted({str(a.get("room") or "").strip() for a in activities if str(a.get("room") or "").strip()})
    tutor = next((_tutor_name(a) for a in activities if _tutor_name(a)), "")
    if not tutor:
        tutor_note = next((note for note in notes if note.startswith("Tutoria:")), "")
        tutor = tutor_note.removeprefix("Tutoria:").split(" — ", 1)[0].strip()
    return ", ".join(rooms) or "—", group or "—", tutor or "—", "; ".join(notes)


def _minutes(hour_label: str) -> int | None:
    key = _hour_sort_key(hour_label)
    return key[1] if key[0] == 0 else None


def _minutes_to_label(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _insert_logo_flowable():
    if not _LOGO_PATH.exists():
        return Spacer(_LOGO_WIDTH, 1)
    try:
        from PIL import Image as PILImage

        with PILImage.open(_LOGO_PATH) as im:
            original_width, original_height = im.size
        logo_height = _LOGO_WIDTH * original_height / original_width
        return Image(str(_LOGO_PATH), width=_LOGO_WIDTH, height=logo_height)
    except Exception:
        return Spacer(_LOGO_WIDTH, 1)


def _build_page_header(sheet_kind: str, display_name: str, activities: Sequence[Dict[str, Any]], notes: List[str], available_width: float):
    room, group, tutor, notes_text = _page_metadata(sheet_kind, display_name, activities, notes)
    title_table = Table(
        [[Paragraph(_clean_text(display_name), _TITLE_STYLE)], [Paragraph("Curs acadèmic 26 / 27", _YEAR_STYLE)]],
        colWidths=[available_width],
    )
    metadata = Table(
        [[Paragraph(f"<b>Aula:</b> {_clean_text(room)}", _META_STYLE), Paragraph(f"<b>Grup:</b> {_clean_text(group)}", _META_STYLE), Paragraph(f"<b>Tutor/a del grup:</b> {_clean_text(tutor)}", _META_STYLE)]],
        colWidths=[available_width / 3] * 3,
    )
    rows = [[title_table], [metadata]]
    if notes_text:
        rows.append([Paragraph(_clean_text(notes_text), _META_STYLE)])
    header_table = Table(rows, colWidths=[available_width])
    style_commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    header_table.setStyle(TableStyle(style_commands))
    return header_table


def _build_grid_table(activities: List[Dict[str, Any]], sheet_kind: str, available_width: float):
    starts = [_minutes(a.get("start")) for a in activities if _minutes(a.get("start")) is not None]
    if not starts:
        return None

    ends: List[int] = []
    for activity in activities:
        start_minutes = _minutes(activity.get("start"))
        if start_minutes is None:
            continue
        try:
            duration_blocks = max(int(activity.get("duration") or 1), 1)
        except (TypeError, ValueError):
            duration_blocks = 1
        ends.append(start_minutes + duration_blocks * 30)

    first_hour = (min(starts) // 60) * 60
    last_hour = ((max(ends) + 59) // 60) * 60
    hour_labels = [_minutes_to_label(m) for m in range(first_hour, max(last_hour, first_hour + 60), 60)]
    hour_row_index = {label: index for index, label in enumerate(hour_labels)}
    by_slot: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for activity in activities:
        start_minutes = _minutes(activity.get("start"))
        if start_minutes is None:
            continue
        key = (activity.get("day"), _minutes_to_label((start_minutes // 60) * 60))
        by_slot.setdefault(key, []).append(activity)

    header_row = [Paragraph("Hora", _HEADER_CELL_STYLE)] + [Paragraph(day, _HEADER_CELL_STYLE) for day in _WEEKDAYS]
    data: List[List[Any]] = [header_row]
    for label in hour_labels:
        data.append([Paragraph(label, _HOUR_CELL_STYLE)] + ["" for _ in _WEEKDAYS])

    hour_col_width = _HOUR_COL_WIDTH
    day_col_width = (available_width - hour_col_width) / len(_WEEKDAYS)
    col_widths = [hour_col_width] + [day_col_width] * len(_WEEKDAYS)

    style_commands = [
        ("BACKGROUND", (0, 1), (-1, -1), _GRID_BACKGROUND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, _GRID_LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, _GRID_LINE),
        ("LINEAFTER", (0, 0), (-1, -1), 0.35, _GRID_LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]

    for day_index, day in enumerate(_WEEKDAYS):
        col = day_index + 1
        for (slot_day, start_label), slot_activities in by_slot.items():
            if slot_day != day or start_label not in hour_row_index:
                continue
            row_start = 1 + hour_row_index[start_label]
            duration_rows = 1
            for activity in slot_activities:
                try:
                    duration_rows = max(duration_rows, (int(activity.get("duration") or 1) + 1) // 2)
                except (TypeError, ValueError):
                    pass
            row_end = min(row_start + duration_rows - 1, len(data) - 1)

            cell_content = _build_activity_cell(slot_activities, sheet_kind)
            data[row_start][col] = cell_content
            if row_end > row_start:
                style_commands.append(("SPAN", (col, row_start), (col, row_end)))
            style_commands.append(("BACKGROUND", (col, row_start), (col, row_end), _NAVY))
            style_commands.append(("LINEBELOW", (col, row_end), (col, row_end), 2.5, colors.white))

    table = Table(data, colWidths=col_widths, rowHeights=[_HEADER_ROW_HEIGHT] + [_ROW_HEIGHT] * len(hour_labels))
    table.setStyle(TableStyle(style_commands))
    return table


def _build_activity_cell(activities: List[Dict[str, Any]], sheet_kind: str):
    columns = []
    for activity in activities:
        subject = _clean_text(activity.get("subject"))
        teacher = _clean_text(activity.get("teacher"))
        tutor_tag = "<font backColor='#FFFFFF' color='#2D3561' size='6'><b>TUTOR/A</b></font><br/>" if _is_tutor_activity(activity) else ""
        columns.append([Paragraph(f"{tutor_tag}{subject}", _ACTIVITY_SUBJECT_STYLE), Paragraph(teacher, _ACTIVITY_TEACHER_STYLE)])

    nested = Table([columns], colWidths=[None] * len(columns))
    nested.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return nested


def build_schedule_pdf(activities: Sequence[Dict[str, Any]]) -> BytesIO:
    """Retorna un .pdf (com a BytesIO) amb una pàgina per a cada grup
    pare, professor i aula que apareguin a `activities`, en un format
    visual de calendari (graella per mitges hores, blocs blaus per a les
    activitats). Els grups combinats (p.ex. 'GI, GP') generen una pàgina
    per a cada grup individual. La Tutoria es tracta igual que a
    l'exportació Excel: nota informativa al grup, bloc real al professor.
    """
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    by_teacher: Dict[str, List[Dict[str, Any]]] = {}
    by_room: Dict[str, List[Dict[str, Any]]] = {}
    group_notes: Dict[str, List[str]] = {}

    for activity in activities:
        is_tutoria = _is_tutoria(activity)
        group_field_names = _split_group_names(activity.get("group") or "")

        if is_tutoria:
            for name in group_field_names:
                group_notes.setdefault(name, []).append(_tutoria_note(activity))
        else:
            for name in group_field_names:
                by_group.setdefault(name, []).append(activity)

        teacher_text = (activity.get("teacher") or "").strip()
        for teacher in [part.strip() for part in teacher_text.split(",") if part.strip()]:
            by_teacher.setdefault(teacher, []).append(activity)

        room_text = (activity.get("room") or "").strip()
        if room_text:
            by_room.setdefault(room_text, []).append(activity)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title="Horaris EMAD",
    )
    available_width = _PAGE_SIZE[0] - 2 * _MARGIN

    sections: List[Tuple[str, str, List[Dict[str, Any]], List[str]]] = []
    all_group_names = sorted(set(by_group) | set(group_notes))
    for group_name in all_group_names:
        sections.append(("group", group_name, by_group.get(group_name, []), group_notes.get(group_name, [])))
    for teacher_name in sorted(by_teacher):
        sections.append(("teacher", teacher_name, by_teacher[teacher_name], []))
    for room_name in sorted(by_room):
        sections.append(("room", room_name, by_room[room_name], []))

    story: List[Any] = []
    if not sections:
        story.append(_insert_logo_flowable())
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("No hi ha cap activitat programada.", _EMPTY_MESSAGE_STYLE))
    for index, (sheet_kind, display_name, sheet_activities, notes) in enumerate(sections):
        story.append(_build_page_header(sheet_kind, display_name, sheet_activities, notes, available_width))
        story.append(Spacer(1, 4 * mm))
        grid_table = _build_grid_table(sheet_activities, sheet_kind, available_width)
        if grid_table is not None:
            story.append(grid_table)
        else:
            story.append(Paragraph("Sense activitats programades.", _EMPTY_MESSAGE_STYLE))
        if index < len(sections) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer
