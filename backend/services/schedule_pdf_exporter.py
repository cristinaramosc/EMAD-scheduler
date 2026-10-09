"""Exporta l'horari actiu a un únic PDF vertical (A4) amb una pàgina per a
cada grup, professor i aula, amb l'aspecte de l'horari de professorat d'EMAD:
graella setmanal (dilluns-divendres) de 8:00 a 21:30 i blocs de colors segons
el tipus d'activitat.

Colors:
  - blau Pantone Reflex Blue ... assignatures
  - Reflex Blue al 70 % ........ Tutoria (només a la pàgina del professor; al
                                 grup no ocupa franja, surt a la capçalera
                                 sota el tutor/a)
  - Reflex Blue al 35 % ........ hores de centre (sense text)
  - negre ....................... reunió de claustre
  - gris ........................ coordinació (bloc fix setmanal)
  - taronja ..................... altres hores de coordinació

Reutilitza la lògica d'agrupació (grups combinats per coma, Tutoria) del
mòdul que genera l'Excel, per no duplicar-la.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

if __package__ and __package__.startswith("backend"):
    from backend.scheduler_engine.quarter_utils import parent_and_quarter, strip_quarter_suffix
    from backend.services.contract_hours import contract_hours
    from backend.services.schedule_exporter import (
        _LOGO_PATH,
        _hour_sort_key,
        _is_tutoria,
        _split_group_names,
        _tutoria_note,
    )
else:  # pragma: no cover
    from scheduler_engine.quarter_utils import parent_and_quarter, strip_quarter_suffix
    from services.contract_hours import contract_hours
    from services.schedule_exporter import (
        _LOGO_PATH,
        _hour_sort_key,
        _is_tutoria,
        _split_group_names,
        _tutoria_note,
    )

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT = "Montserrat"
_FONT_BOLD = "Montserrat-Bold"


def _register_fonts() -> None:
    """Registra Montserrat (Regular i Bold). Si els fitxers no hi són,
    es torna a Helvetica per no fer fallar l'exportació."""
    global _FONT, _FONT_BOLD
    try:
        if _FONT == "Montserrat" and "Montserrat" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Montserrat", str(_FONT_DIR / "Montserrat-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("Montserrat-Bold", str(_FONT_DIR / "Montserrat-Bold.ttf")))
    except Exception:  # pragma: no cover - fitxers de tipografia absents
        _FONT, _FONT_BOLD = "Helvetica", "Helvetica-Bold"


_register_fonts()

_WEEKDAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
_COURSE_LABEL = "Curs 26/27"

# Franja horària fixa de la graella (igual que el calendari de l'app).
_GRID_START_MIN = 8 * 60
_GRID_END_MIN = 21 * 60 + 30

# Bloc fix setmanal de Coordinació (vegeu live_schedule_use_cases).
_FIXED_COORDINATION_DAY = "dimecres"
_FIXED_COORDINATION_START = "15:00"

_PAGE_W, _PAGE_H = A4
_MARGIN_X = 26 * mm  # vora esquerra/dreta de la graella (logo i capçalera hi queden alineats)
_MARGIN_Y = 20 * mm
_HOUR_LABEL_W = 9 * mm
_DAY_HEADER_H = 7 * mm
_MAX_ROW_H = 8 * mm  # alçada d'una mitja hora

_INK = colors.HexColor("#1A1A1A")
_HEADER_BG = colors.HexColor("#4D4F4C")
_GRID_FULL = colors.HexColor("#B9BBB6")
_GRID_HALF = colors.HexColor("#DEDFDB")
_FRAME = colors.HexColor("#4D4F4C")

# Pantone Reflex Blue C (valor RGB aproximat; els valors en pantalla varien
# segons la font). Per canviar-lo, només cal tocar aquesta constant.
_REFLEX_BLUE = colors.HexColor("#001489")


def _tint(color, amount: float):
    """Barreja `color` amb blanc: amount=1 és el color pur, 0 és blanc."""
    return colors.Color(
        1 - (1 - color.red) * amount,
        1 - (1 - color.green) * amount,
        1 - (1 - color.blue) * amount,
    )


_KIND_STYLE = {
    # tipus: (color de fons, color del text)
    "subject": (_REFLEX_BLUE, colors.white),
    "tutoria": (_tint(_REFLEX_BLUE, 0.70), colors.white),
    "centre": (_tint(_REFLEX_BLUE, 0.35), colors.white),
    "claustre": (colors.HexColor("#111111"), colors.white),
    "coordination_fixed": (colors.HexColor("#4D4F4C"), colors.white),
    "coordination": (colors.HexColor("#E0903F"), colors.white),
}
_BLOCK_OUTLINE = colors.HexColor("#000A5C")
_INSET = 1.0            # pt, perfil blanc dins de cada bloc (dos blocs que es toquen: 2 pt)
_HALO = 1.0             # pt, perfil blanc fora del bloc (tapa les línies de la graella)
_THIN_SEPARATOR = 0.5   # pt, entre 1Q i 2Q


# ---------------------------------------------------------------------------
# Utilitats
# ---------------------------------------------------------------------------


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


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


def _minutes(hour_label: Any) -> Optional[int]:
    key = _hour_sort_key(hour_label)
    return key[1] if key[0] == 0 else None


def _hhmm(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _duration_blocks(activity: Dict[str, Any]) -> int:
    try:
        return max(int(activity.get("duration") or 1), 1)
    except (TypeError, ValueError):
        return 1


def _format_hours(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def activity_quarter(activity: Dict[str, Any]) -> Optional[str]:
    """'1Q', '2Q' o None (anual), segons el sufix del grup o de l'assignatura."""
    marker = parent_and_quarter(activity.get("group"), activity.get("subject"))[1]
    return marker.upper() if marker else None


def classify_activity(activity: Dict[str, Any]) -> Optional[str]:
    """Retorna el tipus visual d'una activitat, o None si no s'ha de dibuixar."""
    subject = _norm(activity.get("subject"))
    if subject in {"descans"}:
        return None
    if subject in {"reunió", "reunio"} or "claustre" in subject:
        return "claustre"
    if subject in {"hores de centre", "hora de centre"}:
        return "centre"
    if subject in {"coordinació", "coordinacio"} or subject.startswith(("coordinació ", "coordinacio ")):
        is_fixed = (
            subject in {"coordinació", "coordinacio"}
            and _norm(activity.get("day")) == _FIXED_COORDINATION_DAY
            and str(activity.get("start") or "").strip().lstrip("0") == _FIXED_COORDINATION_START
        )
        return "coordination_fixed" if is_fixed else "coordination"
    if _is_tutoria(activity):
        return "tutoria"
    return "subject"


# ---------------------------------------------------------------------------
# Dibuix
# ---------------------------------------------------------------------------


# Marges interns (en px) del PNG del logo respecte de la tinta real.
_LOGO_PX = (1134, 454)
_LOGO_INK = (21, 25, 1107, 418)  # esquerra, dalt, dreta, baix


def _draw_logo(c: canvas.Canvas, x: float, y_top: float, ink_height: float) -> float:
    """Dibuixa el logotip amb la tinta començant a (x, y_top) i amb una
    alçada de tinta `ink_height`; creix cap avall i cap a la dreta. Retorna
    la y de la vora inferior de la tinta."""
    if not _LOGO_PATH.exists():
        return y_top - ink_height
    try:
        image = ImageReader(str(_LOGO_PATH))
        px_w, px_h = _LOGO_PX
        ink_l, ink_t, _ink_r, ink_b = _LOGO_INK
        scale = ink_height / (ink_b - ink_t)
        width, height = px_w * scale, px_h * scale
        c.drawImage(image, x - ink_l * scale, y_top + ink_t * scale - height, width=width, height=height, mask="auto")
    except Exception:
        pass
    return y_top - ink_height


def _draw_dot(c: canvas.Canvas, x: float, y: float, color) -> None:
    c.setFillColor(color)
    c.circle(x, y, 1.6 * mm, stroke=0, fill=1)


_HEADER_LINE_GAP = 15 * mm  # entre la línia del curs/nom i la segona línia
_HEADER_ROW_STEP = 6.5 * mm
_HEADER_TO_GRID_GAP = 13 * mm
_TITLE_SIZE = 14


def _draw_page_header(
    c: canvas.Canvas,
    sheet_kind: str,
    display_name: str,
    activities: Sequence[Dict[str, Any]],
    notes: List[str],
    tutoria_slots: List[str],
    teacher: Optional[Dict[str, Any]] = None,
    show_dni: bool = False,
) -> float:
    """Dibuixa la capçalera i retorna la y on comença la graella.

    El logo té l'alçada de les dues primeres línies de la dreta: la tinta
    comença a l'alçada de la línia "Curs 26/27 … nom" i acaba a la línia de
    base de la segona línia."""
    top = _PAGE_H - _MARGIN_Y
    left = _MARGIN_X
    right = _PAGE_W - _MARGIN_X

    # Dreta: línia "Curs 26/27 ........ nom" amb subratllat.
    block_left = right - 74 * mm
    cap_height = _TITLE_SIZE * 0.70  # alçada de les majúscules de Montserrat
    line_y = top - cap_height
    second_y = line_y - _HEADER_LINE_GAP

    logo_bottom = _draw_logo(c, left, top, top - second_y)

    c.setFillColor(_INK)
    c.setFont(_FONT, 12)
    c.drawString(block_left, line_y, _COURSE_LABEL)
    c.setFont(_FONT_BOLD, _TITLE_SIZE)
    title = f"Aula {display_name}" if sheet_kind == "room" else display_name
    contract = contract_hours((teacher or {}).get("dedication_pct")) if sheet_kind == "teacher" else None
    if contract:
        title = f"{display_name} {_format_hours(contract['pct'])}%"
    c.drawRightString(right, line_y, title)
    c.setStrokeColor(_INK)
    c.setLineWidth(0.8)
    c.line(block_left, line_y - 2 * mm, right, line_y - 2 * mm)

    # La informació puja un renglò: l'última línia queda a la base del logo.
    y = second_y + _HEADER_ROW_STEP
    if sheet_kind == "group":
        _room, _group, tutor, _notes = _page_metadata("group", display_name, activities, notes)
        c.setFont(_FONT, 11)
        c.setFillColor(_INK)
        c.drawString(block_left, y, "Tutor/a: ")
        c.setFont(_FONT_BOLD, 11)
        c.drawString(block_left + c.stringWidth("Tutor/a: ", _FONT, 11), y, tutor)
        y -= _HEADER_ROW_STEP
        c.setFont(_FONT, 11)
        c.drawString(block_left, y, "Tutoria: ")
        c.setFont(_FONT_BOLD, 11)
        c.drawString(block_left + c.stringWidth("Tutoria: ", _FONT, 11), y, "; ".join(tutoria_slots) if tutoria_slots else "—")
    elif sheet_kind == "teacher":
        totals = {"lective": 0.0, "coordination": 0.0, "centre": 0.0}
        for activity in activities:
            kind = classify_activity(activity)
            hours = _duration_blocks(activity) / 2
            if kind in {"subject", "tutoria"}:
                totals["lective"] += hours
            elif kind == "coordination":
                totals["coordination"] += hours
            elif kind in {"centre", "claustre", "coordination_fixed"}:
                totals["centre"] += hours
        if contract:
            # Hores de contracte (segons el % de jornada): les lectives inclouen
            # classes, tutories i coordinacions; es mostren separades com
            # "classes + coordinacions".
            coordination = min(totals["coordination"], contract["lective"])
            lectives = _format_hours(round(contract["lective"] - coordination, 2))
            if coordination:
                lectives += f" + {_format_hours(coordination)}"
            centre_hours, preparation = contract["centre"], contract["preparation"]
        else:
            lectives = _format_hours(totals["lective"])
            if totals["coordination"]:
                lectives += f" + {_format_hours(totals['coordination'])}"
            centre_hours, preparation = totals["centre"], None
        has_coordination = bool(totals["coordination"])
        legend = [
            ([_KIND_STYLE["coordination"][0], _KIND_STYLE["subject"][0]] if has_coordination else [_KIND_STYLE["subject"][0]], f"Hores Lectives: {lectives}"),
            ([_KIND_STYLE["centre"][0]], f"Hores de Centre: {_format_hours(centre_hours)}"),
        ]
        if preparation is not None:
            legend.append(([_KIND_STYLE["claustre"][0]], f"Hores de Preparació: {_format_hours(preparation)}"))
        # El text s'alinea a l'esquerra, tot a la mateixa x; els punts de
        # color s'alineen a la dreta, enganxats al text.
        text_x = block_left + 4 * mm * max(len(dots) for dots, _ in legend) + 1 * mm
        for dots, text in legend:
            for index, dot in enumerate(dots):
                _draw_dot(c, text_x - 3.4 * mm - 4 * mm * (len(dots) - 1 - index), y + 1 * mm, dot)
            c.setFillColor(_INK)
            c.setFont(_FONT, 11)
            c.drawString(text_x, y, text)
            y -= _HEADER_ROW_STEP

    header_bottom = min(logo_bottom, y + _HEADER_ROW_STEP - 3 * mm)  # y ja és sota l'última línia
    dni = str((teacher or {}).get("dni") or "").strip()
    if show_dni and sheet_kind == "teacher" and dni:
        c.setFillColor(_INK)
        c.setFont(_FONT, 11)
        c.drawString(left, logo_bottom - 7 * mm, dni)
        header_bottom = min(header_bottom, logo_bottom - 10 * mm)
    return header_bottom - _HEADER_TO_GRID_GAP


def _layout_columns(items: List[Dict[str, Any]]) -> None:
    """Assigna `_col` i `_ncols` perquè les activitats solapades es dibuixin
    una al costat de l'altra dins del mateix dia."""
    items.sort(key=lambda it: (it["_start"], it["_end"], it.get("_qorder", 2)))
    cluster: List[Dict[str, Any]] = []
    cluster_end = -1
    columns_end: List[int] = []

    def flush() -> None:
        for it in cluster:
            it["_ncols"] = max(len(columns_end), 1)

    for it in items:
        if cluster and it["_start"] >= cluster_end:
            flush()
            cluster = []
            columns_end = []
            cluster_end = -1
        placed = False
        for index, end in enumerate(columns_end):
            if end <= it["_start"]:
                it["_col"] = index
                columns_end[index] = it["_end"]
                placed = True
                break
        if not placed:
            it["_col"] = len(columns_end)
            columns_end.append(it["_end"])
        cluster.append(it)
        cluster_end = max(cluster_end, it["_end"])
    flush()


def _block_texts(sheet_kind: str, kind: str, activity: Dict[str, Any], coordination_names: Dict[str, str]) -> Tuple[str, str]:
    subject = str(activity.get("subject") or "").strip()
    if kind == "subject":
        subject = strip_quarter_suffix(subject) or subject
    group = str(activity.get("group") or "").strip()
    teacher = str(activity.get("teacher") or "").strip()
    room = str(activity.get("room") or "").strip()
    if kind == "centre":
        return "", ""
    if kind == "claustre":
        return "Reunions Claustre", ""
    if kind == "coordination_fixed":
        return "Coordinació", ""
    if kind == "coordination":
        name = coordination_names.get(_norm(teacher), "")
        return name or "Coordinació", ""
    if kind == "tutoria":
        return "TUTORIA", group
    if sheet_kind == "group":
        return subject, teacher
    if sheet_kind == "room":
        return subject, ", ".join(part for part in [group, teacher] if part)
    return subject, group or room


def _draw_block_text(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, subtitle: str, text_color) -> None:
    if not title and not subtitle:
        return
    pad = 1.5 * mm
    avail_w = max(w - 2 * pad, 4 * mm)
    title_size = 9 if h >= 9 * mm and w >= 22 * mm else 7
    sub_size = 7 if title_size == 9 else 6
    # Si una sola paraula no hi cap (p.ex. blocs de mitja amplada 1Q/2Q),
    # es redueix la lletra fins que hi càpiga, amb un mínim de 5 pt.
    longest = max((pdfmetrics.stringWidth(word, _FONT_BOLD, title_size) for word in title.split()), default=0)
    if longest > avail_w:
        title_size = max(5, title_size * avail_w / longest)
        sub_size = min(sub_size, title_size)
    title_lines = simpleSplit(title, _FONT_BOLD, title_size, avail_w) if title else []
    sub_lines = simpleSplit(subtitle, _FONT, sub_size, avail_w) if subtitle else []
    lead_t, lead_s = title_size * 1.15, sub_size * 1.2
    # Si no hi cap tot, es retalla primer el subtítol i després el títol.
    max_h = h - 1 * mm
    while sub_lines and len(title_lines) * lead_t + len(sub_lines) * lead_s > max_h:
        sub_lines = sub_lines[:-1]
    while len(title_lines) > 1 and len(title_lines) * lead_t > max_h:
        title_lines = title_lines[:-1]
    total = len(title_lines) * lead_t + len(sub_lines) * lead_s
    cursor = y + h / 2 + total / 2
    c.setFillColor(text_color)
    c.setFont(_FONT_BOLD, title_size)
    for line in title_lines:
        cursor -= lead_t
        c.drawCentredString(x + w / 2, cursor + lead_t * 0.22, line)
    c.setFont(_FONT, sub_size)
    for line in sub_lines:
        cursor -= lead_s
        c.drawCentredString(x + w / 2, cursor + lead_s * 0.22, line)


def _draw_quarter_tag(c: canvas.Canvas, x: float, y_top: float, quarter: str, block_color) -> None:
    """Petita etiqueta '1Q'/'2Q' blanca a l'angle superior esquerre del bloc."""
    w, h = 6.2 * mm, 3.3 * mm
    tx, ty = x + 1.2 * mm, y_top - 1.2 * mm - h
    c.setFillColor(colors.white)
    c.roundRect(tx, ty, w, h, 0.9 * mm, stroke=0, fill=1)
    c.setFillColor(block_color)
    c.setFont(_FONT_BOLD, 6)
    c.drawCentredString(tx + w / 2, ty + 0.95 * mm, quarter)


def _draw_grid(
    c: canvas.Canvas,
    sheet_kind: str,
    activities: Sequence[Dict[str, Any]],
    grid_top: float,
    coordination_names: Dict[str, str],
) -> None:
    items: List[Dict[str, Any]] = []
    for activity in activities:
        kind = classify_activity(activity)
        start = _minutes(activity.get("start"))
        if kind is None or start is None or activity.get("day") not in _WEEKDAYS:
            continue
        if sheet_kind == "group" and kind == "tutoria":
            continue
        quarter = activity_quarter(activity) if kind == "subject" else None
        items.append({
            "a": activity, "kind": kind, "quarter": quarter,
            "_qorder": {"1Q": 0, "2Q": 1}.get(quarter, 2),
            "_start": start, "_end": start + _duration_blocks(activity) * 30, "_col": 0, "_ncols": 1,
        })

    start_min = min([_GRID_START_MIN] + [it["_start"] for it in items])
    end_min = max([_GRID_END_MIN] + [it["_end"] for it in items])
    start_min = (start_min // 60) * 60
    n_rows = (end_min - start_min + 29) // 30

    left = _MARGIN_X
    right = _PAGE_W - _MARGIN_X
    col_w = (right - left) / len(_WEEKDAYS)
    avail_h = grid_top - _MARGIN_Y - _DAY_HEADER_H
    row_h = min(_MAX_ROW_H, avail_h / n_rows)
    body_top = grid_top - _DAY_HEADER_H
    body_bottom = body_top - n_rows * row_h

    # Capçalera dels dies.
    c.setFillColor(_HEADER_BG)
    c.rect(left, body_top, right - left, _DAY_HEADER_H, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(_FONT_BOLD, 7.5)
    for index, day in enumerate(_WEEKDAYS):
        c.drawCentredString(left + col_w * (index + 0.5), body_top + 2.4 * mm, day.upper())

    # Línies horitzontals i etiquetes d'hora.
    for row in range(n_rows + 1):
        minute = start_min + row * 30
        y = body_top - row * row_h
        is_full = minute % 60 == 0
        c.setStrokeColor(_GRID_FULL if is_full else _GRID_HALF)
        c.setLineWidth(0.6 if is_full else 0.4)
        c.line(left, y, right, y)
        if is_full:
            c.setStrokeColor(_FRAME)
            c.setLineWidth(0.8)
            c.line(left - _HOUR_LABEL_W, y, left, y)
            c.line(right, y, right + _HOUR_LABEL_W, y)
            c.setFillColor(_INK)
            c.setFont(_FONT, 7.5)
            c.drawString(left - _HOUR_LABEL_W + 0.5 * mm, y + 0.8 * mm, str(minute // 60))
            c.drawRightString(right + _HOUR_LABEL_W - 0.5 * mm, y + 0.8 * mm, str(minute // 60))

    # Línies verticals.
    c.setStrokeColor(_GRID_FULL)
    c.setLineWidth(0.4)
    for index in range(1, len(_WEEKDAYS)):
        x = left + col_w * index
        c.line(x, body_top, x, body_bottom)
    c.setStrokeColor(_FRAME)
    c.setLineWidth(1)
    c.line(left, body_top, left, body_bottom)
    c.line(right, body_top, right, body_bottom)

    # Blocs: primer es calcula la geometria de tots, després es dibuixen en
    # passes perquè el perfil blanc sigui igual a tot el contorn.
    drawn: List[Dict[str, Any]] = []
    for day_index, day in enumerate(_WEEKDAYS):
        day_items = [it for it in items if it["a"].get("day") == day]
        if not day_items:
            continue
        _layout_columns(day_items)
        for it in day_items:
            first = max(it["_start"], start_min)
            last = min(it["_end"], start_min + n_rows * 30)
            if last <= first:
                continue
            width = col_w / it["_ncols"]
            x = left + col_w * day_index + width * it["_col"]
            y_top = body_top - (first - start_min) / 30 * row_h
            height = (last - first) / 30 * row_h
            drawn.append({"x": x, "y": y_top - height, "w": width, "h": height, "quarter": it["quarter"], "day": day, "it": it})

    # Passada 1: halo blanc al voltant de cada bloc (tapa les línies de la
    # graella perquè el contorn es vegi), sense sortir de la graella.
    c.setFillColor(colors.white)
    for r in drawn:
        pair_left = any(_quarter_pair(o, r) for o in drawn if o is not r)
        pair_right = any(_quarter_pair(r, o) for o in drawn if o is not r)
        r["pair_left"], r["pair_right"] = pair_left, pair_right
        x0 = max(r["x"] - (0 if pair_left else _HALO), left)
        x1 = min(r["x"] + r["w"] + (0 if pair_right else _HALO), right)
        y0 = max(r["y"] - _HALO, body_bottom)
        y1 = min(r["y"] + r["h"] + _HALO, body_top)
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)

    # Passada 2: el color, replegat cap a dins el mateix gruix a tot el
    # voltant. Entre dues assignatures que es toquen sumen dos perfils
    # (més gruixut); entre 1Q i 2Q que comparteixen franja, només un de fi.
    for r in drawn:
        it = r["it"]
        inset_l = _THIN_SEPARATOR / 2 if r["pair_left"] else _INSET
        inset_r = _THIN_SEPARATOR / 2 if r["pair_right"] else _INSET
        bx, by = r["x"] + inset_l, r["y"] + _INSET
        bw, bh = r["w"] - inset_l - inset_r, r["h"] - 2 * _INSET
        fill, text_color = _KIND_STYLE[it["kind"]]
        c.setFillColor(fill)
        c.rect(bx, by, bw, bh, stroke=0, fill=1)
        title, subtitle = _block_texts(sheet_kind, it["kind"], it["a"], coordination_names)
        quarter = it["quarter"]
        if quarter and bh < 12 * mm:
            title = f"{title} ({quarter})"  # bloc massa baix per a l'etiqueta
        _draw_block_text(c, bx, by, bw, bh, title, subtitle, text_color)
        if quarter and bh >= 12 * mm:
            _draw_quarter_tag(c, bx, by + bh, quarter, fill)

    # El marc vertical es torna a dibuixar al damunt dels halos.
    c.setStrokeColor(_FRAME)
    c.setLineWidth(1)
    c.line(left, body_top, left, body_bottom)
    c.line(right, body_top, right, body_bottom)


def _quarter_pair(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """True si `left` (1Q) i `right` (2Q) són dues meitats d'una mateixa
    franja: el mateix dia, una al costat de l'altra, quadrimestres diferents."""
    return bool(
        left["day"] == right["day"]
        and left["quarter"]
        and right["quarter"]
        and left["quarter"] != right["quarter"]
        and abs((left["x"] + left["w"]) - right["x"]) <= 0.5
    )


def _tutoria_slot_text(activity: Dict[str, Any]) -> str:
    day = str(activity.get("day") or "").strip()
    start = _minutes(activity.get("start"))
    if start is None:
        return day
    end = start + _duration_blocks(activity) * 30
    return f"{day} {_hhmm(start)}–{_hhmm(end)}".strip()


def build_schedule_pdf(
    activities: Sequence[Dict[str, Any]],
    teachers: Optional[Sequence[Dict[str, Any]]] = None,
    show_dni: bool = False,
) -> BytesIO:
    """Retorna un .pdf (com a BytesIO) vertical amb una pàgina per a cada
    grup pare, professor i aula que apareguin a `activities`. Els grups
    combinats (p.ex. 'GI, GP') generen una pàgina per a cada grup
    individual. La Tutoria no ocupa franja a la pàgina del grup (surt a la
    capçalera, amb dia i hora) i és un bloc real a la del professor.

    `teachers` (opcional) aporta el nom de la coordinació de cada professor
    (bloc taronja), el seu % de jornada (que dona les hores de contracte de
    la capçalera) i el DNI, que només s'imprimeix si `show_dni` és True.
    """
    teacher_records = {_norm(t.get("name")): t for t in (teachers or []) if t.get("name")}
    coordination_names = {
        _norm(t.get("name")): str(t.get("coordination_name") or "").strip()
        for t in (teachers or [])
        if t.get("name")
    }

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    by_teacher: Dict[str, List[Dict[str, Any]]] = {}
    by_room: Dict[str, List[Dict[str, Any]]] = {}
    group_notes: Dict[str, List[str]] = {}
    group_tutoria_slots: Dict[str, List[str]] = {}

    for activity in activities:
        is_tutoria = _is_tutoria(activity)
        group_field_names = _split_group_names(activity.get("group") or "")

        if is_tutoria:
            for name in group_field_names:
                group_notes.setdefault(name, []).append(_tutoria_note(activity))
                group_tutoria_slots.setdefault(name, []).append(_tutoria_slot_text(activity))
        else:
            for name in group_field_names:
                by_group.setdefault(name, []).append(activity)

        teacher_text = (activity.get("teacher") or "").strip()
        for teacher in [part.strip() for part in teacher_text.split(",") if part.strip()]:
            by_teacher.setdefault(teacher, []).append(activity)

        room_text = (activity.get("room") or "").strip()
        if room_text:
            by_room.setdefault(room_text, []).append(activity)

    sections: List[Tuple[str, str, List[Dict[str, Any]], List[str], List[str]]] = []
    for group_name in sorted(set(by_group) | set(group_notes)):
        sections.append(("group", group_name, by_group.get(group_name, []), group_notes.get(group_name, []), group_tutoria_slots.get(group_name, [])))
    for teacher_name in sorted(by_teacher):
        sections.append(("teacher", teacher_name, by_teacher[teacher_name], [], []))
    for room_name in sorted(by_room):
        sections.append(("room", room_name, by_room[room_name], [], []))

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Horaris EMAD")

    if not sections:
        _draw_logo(c, _MARGIN_X, _PAGE_H - _MARGIN_Y, 48 * mm)
        c.setFillColor(_INK)
        c.setFont(_FONT, 10)
        c.drawString(_MARGIN_X, _PAGE_H - _MARGIN_Y - 30 * mm, "No hi ha cap activitat programada.")
        c.showPage()

    for sheet_kind, display_name, sheet_activities, notes, tutoria_slots in sections:
        grid_top = _draw_page_header(
            c, sheet_kind, display_name, sheet_activities, notes, tutoria_slots,
            teacher=teacher_records.get(_norm(display_name)) if sheet_kind == "teacher" else None,
            show_dni=show_dni,
        )
        _draw_grid(c, sheet_kind, sheet_activities, grid_top, coordination_names)
        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer
