"""Reunions de coordinació conjuntes.

Una reunió conjunta és una hora de coordinació que fan junts un coordinador/a
(p. ex. el de Gràfic, PFI o COM) i uns participants fixos (p. ex. Eli i
Cristina). Es defineix a les dades acadèmiques (full "Coordinacions" de
l'Excel o /academic-data/coordination-meetings) perquè es pugui canviar el
coordinador/a, la durada o l'horari sense tocar codi.

Camp d'una reunió:
  name          nom de la reunió (p. ex. "Gràfic")
  coordinator   professor/a que coordina
  participants  llista de professors que hi assisteixen
  hours         durada en hores (per defecte 1)
  preferred_day dia preferit (per defecte Dimecres)
  window_start  inici de la franja preferida (per defecte 8:00)
  window_end    final de la franja preferida (per defecte 14:00, exclòs)
  series        reunions amb el mateix nom de sèrie s'intenten posar
                seguides, una darrere l'altra (per defecte buit = soles)
  active        si és fals s'ignora

Aquest mòdul només planifica: rep les franges on cada professor NO és
disponible i retorna on posar cada reunió. No toca res més.
"""
from __future__ import annotations

from itertools import permutations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

SUBJECT_PREFIX = "Coordinació conjunta"
DEFAULT_PREFERRED_DAY = "Dimecres"
DEFAULT_WINDOW_START = "8:00"
DEFAULT_WINDOW_END = "14:00"
_MAX_PERMUTED_SERIES = 4

Slot = Tuple[int, int]  # (índex de dia, índex de franja)


def meeting_subject(name: Any) -> str:
    """Assignatura amb què apareix la reunió a l'horari."""
    return f"{SUBJECT_PREFIX} · {str(name or '').strip()}"


def is_joint_coordination_subject(subject: Any) -> bool:
    return str(subject or "").strip().casefold().startswith(SUBJECT_PREFIX.casefold())


def _names(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    result: List[str] = []
    for part in parts:
        text = " ".join(str(part).split())
        if text and text.casefold() not in {item.casefold() for item in result}:
            result.append(text)
    return result


def _hours(value: Any, default: float = 1.0) -> float:
    if value in (None, ""):
        return default
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return default
    return number if number > 0 else default


def normalize_meeting(record: Dict[str, Any]) -> Dict[str, Any]:
    """Omple els valors per defecte i neteja els textos d'una reunió."""
    active = record.get("active", True)
    if isinstance(active, str):
        active = active.strip().casefold() in {"sí", "si", "s", "yes", "true", "1", "x"}
    return {
        "name": " ".join(str(record.get("name") or "").split()),
        "active": bool(active),
        "coordinator": " ".join(str(record.get("coordinator") or "").split()),
        "participants": _names(record.get("participants")),
        "hours": _hours(record.get("hours")),
        "preferred_day": " ".join(str(record.get("preferred_day") or DEFAULT_PREFERRED_DAY).split()),
        "window_start": str(record.get("window_start") or DEFAULT_WINDOW_START).strip(),
        "window_end": str(record.get("window_end") or DEFAULT_WINDOW_END).strip(),
        "series": " ".join(str(record.get("series") or "").split()),
    }


def meeting_members(meeting: Dict[str, Any]) -> List[str]:
    """Coordinador/a i participants, sense repetits."""
    return _names([meeting.get("coordinator"), *(meeting.get("participants") or [])])


def _minutes(label: Any) -> Optional[int]:
    text = str(label or "").strip()
    hour, separator, minute = text.partition(":")
    if not separator:
        return None
    try:
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


class _Grid:
    def __init__(self, day_names: Sequence[str], hour_names: Sequence[str]) -> None:
        self.day_names = list(day_names)
        self.hour_names = list(hour_names)
        # L'última etiqueta (21:30) només marca el final de la jornada.
        self.periods = max(len(self.hour_names) - 1, 0)
        self._minutes = [_minutes(label) for label in self.hour_names]

    def day_index(self, name: Any) -> Optional[int]:
        wanted = str(name or "").strip().casefold()
        for index, day in enumerate(self.day_names):
            if str(day).strip().casefold() == wanted:
                return index
        return None

    def window(self, start: Any, end: Any) -> Tuple[int, int]:
        first, last = _minutes(start), _minutes(end)
        begin = 0
        stop = self.periods
        if first is not None:
            begin = next((i for i, m in enumerate(self._minutes[: self.periods]) if m is not None and m >= first), self.periods)
        if last is not None:
            stop = next((i for i, m in enumerate(self._minutes) if m is not None and m >= last), self.periods)
        return begin, min(max(stop, begin), self.periods)


def plan_meetings(
    meetings: Iterable[Dict[str, Any]],
    blocked_by_teacher: Dict[str, Set[Slot]],
    day_names: Sequence[str],
    hour_names: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Decideix dia i hora de cada reunió.

    `blocked_by_teacher` és {nom en minúscules: {(dia, franja), ...}} amb les
    franges on aquell professor no és disponible. Retorna `(planificades,
    sense_lloc)`.

    Ordre de preferència, per a cada sèrie de reunions:
      1. totes seguides, el dia i dins la franja preferits;
      2. cada reunió soleta, el dia i dins la franja preferits;
      3. el dia preferit, a qualsevol hora;
      4. un altre dia, dins la franja preferida;
      5. un altre dia, a qualsevol hora.
    Mai no es posa una reunió on algun dels assistents no és disponible, ni
    dues reunions amb algun assistent comú a la mateixa franja.
    """
    grid = _Grid(day_names, hour_names)
    busy: Dict[str, Set[Slot]] = {name.casefold(): set(slots) for name, slots in blocked_by_teacher.items()}
    planned: List[Dict[str, Any]] = []
    unplanned: List[Dict[str, Any]] = []

    series_order: List[str] = []
    series_members: Dict[str, List[Dict[str, Any]]] = {}
    for meeting in meetings:
        meeting = normalize_meeting(meeting)
        if not meeting["active"] or not meeting["name"]:
            continue
        key = meeting["series"].casefold() or f"__sola__{meeting['name'].casefold()}"
        if key not in series_members:
            series_order.append(key)
            series_members[key] = []
        series_members[key].append(meeting)

    def blocks_of(meeting: Dict[str, Any]) -> int:
        return max(int(round(meeting["hours"] * 2)), 1)

    def fits(meeting: Dict[str, Any], day: int, start: int, window: Tuple[int, int], *, in_window: bool) -> bool:
        end = start + blocks_of(meeting)
        if start < 0 or end > grid.periods:
            return False
        if in_window and (start < window[0] or end > window[1]):
            return False
        return all(
            (day, period) not in busy.get(member.casefold(), ())
            for member in meeting_members(meeting)
            for period in range(start, end)
        )

    def commit(meeting: Dict[str, Any], day: int, start: int, window: Tuple[int, int], consecutive: bool) -> None:
        blocks = blocks_of(meeting)
        members = meeting_members(meeting)
        for member in members:
            busy.setdefault(member.casefold(), set()).update((day, p) for p in range(start, start + blocks))
        planned.append(
            {
                "name": meeting["name"],
                "subject": meeting_subject(meeting["name"]),
                "members": members,
                "day": grid.day_names[day],
                "day_index": day,
                "start": grid.hour_names[start],
                "start_index": start,
                "blocks": blocks,
                "hours": meeting["hours"],
                "within_preferred_window": window[0] <= start and start + blocks <= window[1],
                "consecutive_series": consecutive,
            }
        )

    for key in series_order:
        series = series_members[key]
        first = series[0]
        window = grid.window(first["window_start"], first["window_end"])
        preferred_day = grid.day_index(first["preferred_day"])
        days_pref = [preferred_day] if preferred_day is not None else []
        days_other = [d for d in range(len(grid.day_names)) if d not in days_pref]

        # 1) tota la sèrie seguida, el dia i dins la franja preferits
        if len(series) > 1:
            orders: Iterable[Sequence[Dict[str, Any]]] = (
                permutations(series) if len(series) <= _MAX_PERMUTED_SERIES else [tuple(series)]
            )
            orders = list(orders)
            done = False
            for day in days_pref or range(len(grid.day_names)):
                for start in range(window[0], window[1]):
                    for order in orders:
                        cursor, placements = start, []
                        for meeting in order:
                            if not fits(meeting, day, cursor, window, in_window=True):
                                placements = []
                                break
                            placements.append((meeting, cursor))
                            cursor += blocks_of(meeting)
                        if placements:
                            for meeting, begin in placements:
                                commit(meeting, day, begin, window, True)
                            done = True
                            break
                    if done:
                        break
                if done:
                    break
            if done:
                continue

        # 2..5) reunions una per una
        for meeting in series:
            m_window = grid.window(meeting["window_start"], meeting["window_end"])
            m_pref = grid.day_index(meeting["preferred_day"])
            m_days_pref = [m_pref] if m_pref is not None else []
            m_days_other = [d for d in range(len(grid.day_names)) if d not in m_days_pref]
            options = [
                (m_days_pref, True),
                (m_days_pref, False),
                (m_days_other, True),
                (m_days_other, False),
            ]
            found = None
            for days, in_window in options:
                for day in days:
                    for start in range(0, grid.periods):
                        if fits(meeting, day, start, m_window, in_window=in_window):
                            found = (day, start)
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                commit(meeting, found[0], found[1], m_window, False)
            else:
                unplanned.append(
                    {"name": meeting["name"], "members": meeting_members(meeting), "reason": "no_common_slot"}
                )

    return planned, unplanned
