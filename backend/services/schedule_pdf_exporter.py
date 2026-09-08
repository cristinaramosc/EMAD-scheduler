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
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
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

_PAGE_SIZE = landscape(A4)
_MARGIN = 12 * mm
_LOGO_WIDTH = 34 * mm
_ROW_HEIGHT = 5.6 * mm
_HEADER_ROW_HEIGHT = 7 * mm
_HOUR_COL_WIDTH = 16 * mm

_ACTIVITY_BLUE = colors.HexColor("#0071E3")
_HEADER_GREY = colors.HexColor("#F0F0F3")
_GRID_LINE = colors.HexColor("#D9D9D9")
_TEXT_BLACK = colors.HexColor("#1D1D1F")

_TITLE_STYLE = ParagraphStyle(
    "Title", fontName="Helvetica-Bold", fontSize=16, textColor=_TEXT_BLACK, alignment=TA_RIGHT, leading=18
)
_NOTE_STYLE = ParagraphStyle(
    "Note", fontName="Helvetica-Oblique", fontSize=8, textColor=_TEXT_BLACK, alignment=TA_RIGHT, leading=10
)
_HEADER_CELL_STYLE = ParagraphStyle(
    "HeaderCell", fontName="Helvetica-Bold", fontSize=8, textColor=_TEXT_BLACK, alignment=TA_LEFT, leading=10
)
_HOUR_CELL_STYLE = ParagraphStyle(
    "HourCell", fontName="Helvetica-Bold", fontSize=7, textColor=_TEXT_BLACK, alignment=TA_LEFT, leading=8
)
_EMPTY_MESSAGE_STYLE = ParagraphStyle(
    "Empty", fontName="Helvetica-Oblique", fontSize=10, textColor=_TEXT_BLACK, alignment=TA_LEFT
)
_ACTIVITY_SUBJECT_STYLE = ParagraphStyle(
    "ActivitySubject", fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.white, alignment=TA_LEFT, leading=9
)
_ACTIVITY_EXTRA_STYLE = ParagraphStyle(
    "ActivityExtra", fontName="Helvetica", fontSize=6.5, textColor=colors.white, alignment=TA_LEFT, leading=8
)


def _cell_text_parts(activity: Dict[str, Any], sheet_kind: str) -> Tuple[str, str]:
    subject = (activity.get("subject") or "").strip()
    if sheet_kind == "room":
        extra_fields = [activity.get("group"), activity.get("teacher")]
    elif sheet_kind == "teacher":
        extra_fields = [activity.get("group"), activity.get("room")]
    else:
        extra_fields = [activity.get("teacher"), activity.get("room")]
    extra = " · ".join(part for part in extra_fields if part)
    return subject, extra


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


def _build_page_header(sheet_kind: str, display_name: str, notes: List[str], available_width: float):
    label = _HEADER_LABELS.get(sheet_kind, "")
    title_text = f"{label}: {display_name}" if label else display_name

    logo_flowable = _insert_logo_flowable()
    title_paragraph = Paragraph(title_text, _TITLE_STYLE)

    rows = [[logo_flowable, title_paragraph]]
    if notes:
        rows.append(["", Paragraph("<br/>".join(notes), _NOTE_STYLE)])

    header_table = Table(rows, colWidths=[_LOGO_WIDTH + 4 * mm, available_width - _LOGO_WIDTH - 4 * mm])
    style_commands = [
        ("SPAN", (0, 0), (0, len(rows) - 1)),
        ("VALIGN", (0, 0), (0, -1), "TOP"),
        ("VALIGN", (1, 0), (1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    header_table.setStyle(TableStyle(style_commands))
    return header_table


def _build_grid_table(activities: List[Dict[str, Any]], sheet_kind: str, available_width: float):
    days = _WEEKDAYS

    starts = [_minutes(a.get("start")) for a in activities]
    starts = [m for m in starts if m is not None]
    if not starts:
        return None

    ends = []
    for activity in activities:
        start_minutes = _minutes(activity.get("start"))
        if start_minutes is None:
            continue
        duration_blocks = activity.get("duration") or 1
        try:
            duration_blocks = max(int(duration_blocks), 1)
        except (TypeError, ValueError):
            duration_blocks = 1
        ends.append(start_minutes + duration_blocks * 30)

    min_minutes = min(starts)
    max_minutes = max(ends) if ends else min_minutes + 30
    hour_labels = [_minutes_to_label(m) for m in range(min_minutes, max_minutes, 30)]
    hour_row_index = {label: index for index, label in enumerate(hour_labels)}

    # Agrupa les activitats per (dia, hora d'inici) per gestionar el cas
    # (poc habitual) que hi hagi més d'una activitat simultània a la
    # mateixa franja (p.ex. mig grup a cada banda).
    by_slot: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for activity in activities:
        key = (activity.get("day"), activity.get("start"))
        by_slot.setdefault(key, []).append(activity)

    header_row = [Paragraph("Hora", _HEADER_CELL_STYLE)] + [
        Paragraph(day.capitalize(), _HEADER_CELL_STYLE) for day in days
    ]
    data: List[List[Any]] = [header_row]
    for label in hour_labels:
        data.append([Paragraph(label, _HOUR_CELL_STYLE)] + ["" for _ in days])

    hour_col_width = _HOUR_COL_WIDTH
    day_col_width = (available_width - hour_col_width) / max(len(days), 1)
    col_widths = [hour_col_width] + [day_col_width] * len(days)

    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.5, _GRID_LINE),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_GREY),
        ("BACKGROUND", (0, 1), (0, -1), _HEADER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]

    for day_index, day in enumerate(days):
        col = day_index + 1
        for start_label, slot_activities in by_slot.items():
            if start_label[0] != day:
                continue
            start_row_key = start_label[1]
            if start_row_key not in hour_row_index:
                continue
            row_start = 1 + hour_row_index[start_row_key]
            duration_blocks = 1
            for activity in slot_activities:
                try:
                    duration_blocks = max(duration_blocks, int(activity.get("duration") or 1))
                except (TypeError, ValueError):
                    pass
            row_end = min(row_start + duration_blocks - 1, len(data) - 1)

            cell_content = _build_activity_cell(slot_activities, sheet_kind)
            data[row_start][col] = cell_content
            if row_end > row_start:
                style_commands.append(("SPAN", (col, row_start), (col, row_end)))
            style_commands.append(("BACKGROUND", (col, row_start), (col, row_end), _ACTIVITY_BLUE))

    table = Table(data, colWidths=col_widths, rowHeights=[_HEADER_ROW_HEIGHT] + [_ROW_HEIGHT] * len(hour_labels))
    table.setStyle(TableStyle(style_commands))
    return table


def _build_activity_cell(activities: List[Dict[str, Any]], sheet_kind: str):
    if len(activities) == 1:
        subject, extra = _cell_text_parts(activities[0], sheet_kind)
        paragraphs = [Paragraph(subject, _ACTIVITY_SUBJECT_STYLE)]
        if extra:
            paragraphs.append(Paragraph(extra, _ACTIVITY_EXTRA_STYLE))
        return paragraphs

    # Diverses activitats simultànies (p.ex. mig grup cadascuna): es mostren
    # apilades dins la mateixa franja, separades per una línia fina blanca.
    rows = []
    for activity in activities:
        subject, extra = _cell_text_parts(activity, sheet_kind)
        cell_paragraphs = [Paragraph(subject, _ACTIVITY_SUBJECT_STYLE)]
        if extra:
            cell_paragraphs.append(Paragraph(extra, _ACTIVITY_EXTRA_STYLE))
        rows.append([cell_paragraphs])
    nested = Table(rows, colWidths=[None])
    nested.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _ACTIVITY_BLUE),
                ("LINEBELOW", (0, 0), (-1, -2), 0.75, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
        story.append(_build_page_header(sheet_kind, display_name, notes, available_width))
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
