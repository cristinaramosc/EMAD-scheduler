"""Eines que l'assistent pot fer servir per consultar i analitzar l'horari.

Principis:
- Les eines de consulta són de només lectura i treballen sobre una còpia de
  l'horari (la proposta oberta o l'horari actiu).
- `check_move` i `find_free_slots` fan proves "en sec": mai modifiquen res.
- Les eines `propose_*` NO apliquen cap canvi: només registren una acció
  pendent. L'acció només s'executa quan la persona prem "Aplica" a la interfície
  (vegeu `AssistantUseCases.apply_action`).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from backend.scheduler_engine.engine import SchedulerEngine
    from backend.scheduler_engine.models.activity import Activity
    from backend.scheduler_engine.models.schedule import Schedule
    from backend.scheduler_engine.quarter_utils import group_names
    from backend.scheduler_engine.teacher_utils import teacher_names
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.engine import SchedulerEngine
    from scheduler_engine.models.activity import Activity
    from scheduler_engine.models.schedule import Schedule
    from scheduler_engine.quarter_utils import group_names
    from scheduler_engine.teacher_utils import teacher_names


MAX_ROWS = 80
PERIODS_PER_DAY = 28  # 8:00 ... 21:30 (franges de 30 min)
DAY_NAMES = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]


def hour_grid() -> List[str]:
    names: List[str] = []
    minutes = 8 * 60
    while len(names) < PERIODS_PER_DAY:
        names.append(f"{minutes // 60}:{minutes % 60:02d}")
        minutes += 30
    return names


@dataclass
class PendingAction:
    id: str
    kind: str  # "move" | "toggle_break"
    payload: Dict[str, Any]
    description: str
    source: str  # "proposal" | "live"
    proposal_id: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "description": self.description}


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "get_overview",
        "description": (
            "Resum general de l'horari: nombre d'activitats, grups, professors, conflictes i "
            "activitats sense col·locar, i hores setmanals per grup i per professor."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_schedule",
        "description": (
            "Llista les activitats de l'horari, filtrables per grup, professor, aula, dia o "
            "assignatura (coincidència parcial, sense distingir majúscules). Cada fila porta l'id "
            "de l'activitat, que cal per moure-la. Un grup combinat com 'GI, GP' coincideix amb GI i GP."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string"},
                "teacher": {"type": "string"},
                "room": {"type": "string"},
                "day": {"type": "string", "description": "Dilluns, Dimarts, Dimecres, Dijous o Divendres"},
                "subject": {"type": "string"},
            },
        },
    },
    {
        "name": "get_problems",
        "description": "Conflictes reals i activitats que no s'han pogut col·locar (amb els seus motius).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_restrictions",
        "description": (
            "Restriccions conegudes d'un professor o d'un grup: franges no disponibles per dia, "
            "màxim de dies i dies amb descans."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"teacher": {"type": "string"}, "group": {"type": "string"}},
        },
    },
    {
        "name": "get_person_summary",
        "description": (
            "Resum de l'horari d'un professor o d'un grup: per dia, hora d'inici, hora de final, "
            "hores de classe i franges buides entre classes; total d'hores i de dies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"teacher": {"type": "string"}, "group": {"type": "string"}},
        },
    },
    {
        "name": "check_move",
        "description": (
            "Comprova SENSE aplicar-ho si moure una activitat a un altre dia/hora és possible: "
            "conflictes nous del motor i franges no disponibles del professor o del grup."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
                "day": {"type": "string"},
                "start": {"type": "string", "description": "Hora d'inici, p.ex. 10:30"},
            },
            "required": ["activity_id", "day", "start"],
        },
    },
    {
        "name": "find_free_slots",
        "description": (
            "Busca franges (dia i hora) on es pot moure una activitat sense conflictes ni franges "
            "no disponibles. Opcionalment només un dia concret."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
                "day": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "propose_move",
        "description": (
            "Proposa moure una activitat. NO s'aplica: la persona usuària veurà un botó 'Aplica'. "
            "Només es registra si la comprovació és correcta; fes servir-la després de check_move o "
            "find_free_slots i explica el motiu del canvi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
                "day": {"type": "string"},
                "start": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["activity_id", "day", "start"],
        },
    },
    {
        "name": "propose_toggle_break",
        "description": (
            "Proposa posar (o treure) el descans d'un grup un dia concret; el descans és un forat "
            "horitzontal que desplaça les classes. NO s'aplica fins que la persona ho confirmi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string"},
                "day": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["group", "day"],
        },
    },
]


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _slots_of(record: Dict[str, Any], key: str = "unavailable_slots") -> List[str]:
    raw = record.get(key)
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            raw = [raw]
    return [str(item) for item in (raw or [])]


def _runs(slots: Sequence[str], hours: List[str]) -> Dict[str, str]:
    """{dia: 'hora..hora (n franges)'} agrupant franges consecutives."""
    by_day: Dict[str, List[int]] = {}
    for slot in slots:
        day, _, label = str(slot).partition(" ")
        if label in hours:
            by_day.setdefault(day, []).append(hours.index(label))
    result: Dict[str, str] = {}
    for day, indexes in by_day.items():
        indexes.sort()
        runs: List[List[int]] = []
        for index in indexes:
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        result[day] = ", ".join(
            f"{hours[run[0]]}-{hours[run[-1]]}" if len(run) > 1 else hours[run[0]] for run in runs
        )
    return result


class AssistantToolbox:
    def __init__(
        self,
        *,
        source: str,
        proposal_id: Optional[str],
        activities: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        unplaced: List[Dict[str, Any]],
        academic_data_repo: Optional[Any],
        register_action: Callable[[PendingAction], None],
        new_action_id: Callable[[], str],
    ) -> None:
        self.source = source
        self.proposal_id = proposal_id
        self._activities = [dict(item) for item in activities]
        self._conflicts = conflicts
        self._unplaced = unplaced
        self._repo = academic_data_repo
        self._register_action = register_action
        self._new_action_id = new_action_id
        self._hours = hour_grid()
        self._baseline_keys: Optional[set] = None

    # ------------------------------------------------------------------ utils
    def definitions(self) -> List[Dict[str, Any]]:
        return TOOL_DEFINITIONS

    def call(self, name: str, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"error": f"eina_desconeguda: {name}"}
        try:
            return handler(**(arguments or {}))
        except TypeError as exc:
            return {"error": f"arguments_invalids: {exc}"}
        except Exception as exc:  # defensiu: una eina no ha de trencar la conversa
            return {"error": f"error_intern: {exc}"}

    def _find(self, activity_id: Any) -> Optional[Dict[str, Any]]:
        for item in self._activities:
            if str(item.get("id")) == str(activity_id):
                return item
        return None

    def _end_label(self, item: Dict[str, Any]) -> str:
        index = self._hours.index(item["start"]) + int(item["duration"]) if item["start"] in self._hours else None
        if index is None:
            return "?"
        return self._hours[index] if index < len(self._hours) else "22:00"

    def _row(self, item: Dict[str, Any]) -> str:
        hours = int(item["duration"]) / 2
        fixed = " [FIX]" if item.get("fixed") else ""
        room = f" | aula {item['room']}" if item.get("room") else ""
        return (
            f"id={item['id']} | {item['day']} {item['start']}-{self._end_label(item)} ({hours:g} h) | "
            f"{item['subject']} | {item['teacher']} | {item['group']}{room}{fixed}"
        )

    def _matches_group(self, item: Dict[str, Any], wanted: str) -> bool:
        wanted_names = {_norm(name) for name in (group_names(wanted) or [wanted])}
        item_names = {_norm(name) for name in (group_names(item.get("group")) or [item.get("group")])}
        return bool(wanted_names & item_names) or _norm(wanted) in _norm(item.get("group"))

    def _matches_teacher(self, item: Dict[str, Any], wanted: str) -> bool:
        wanted_norm = _norm(wanted)
        return any(wanted_norm in _norm(name) for name in (teacher_names(item.get("teacher")) or [item.get("teacher")]))

    def _day_index(self, day: str) -> Optional[int]:
        for index, name in enumerate(DAY_NAMES):
            if _norm(name) == _norm(day):
                return index
        return None

    def _canonical_day(self, day: str) -> Optional[str]:
        index = self._day_index(day)
        return DAY_NAMES[index] if index is not None else None

    def _canonical_hour(self, start: str) -> Optional[str]:
        label = str(start or "").strip()
        if label.count(":") == 1:
            hour, minute = label.split(":")
            if hour.isdigit() and minute.isdigit():
                label = f"{int(hour)}:{int(minute):02d}"
        return label if label in self._hours else None

    # ----------------------------------------------------------------- queries
    def tool_get_overview(self) -> Dict[str, Any]:
        groups: Dict[str, float] = {}
        teachers: Dict[str, float] = {}
        for item in self._activities:
            hours = int(item["duration"]) / 2
            for group in group_names(item.get("group")) or [item.get("group")]:
                groups[group] = groups.get(group, 0) + hours
            for teacher in teacher_names(item.get("teacher")) or [item.get("teacher")]:
                teachers[teacher] = teachers.get(teacher, 0) + hours
        return {
            "origen": "proposta oberta" if self.source == "proposal" else "horari actiu",
            "activitats": len(self._activities),
            "conflictes": len(self._conflicts),
            "activitats_sense_collocar": len(self._unplaced),
            "hores_per_grup": {name: round(value, 1) for name, value in sorted(groups.items())},
            "hores_per_professor": {name: round(value, 1) for name, value in sorted(teachers.items())},
            "nota": "Les hores sumen cada activitat tal com és a l'horari (una parella 1Q/2Q compta dues vegades).",
        }

    def tool_get_schedule(
        self,
        group: Optional[str] = None,
        teacher: Optional[str] = None,
        room: Optional[str] = None,
        day: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected = []
        for item in self._activities:
            if group and not self._matches_group(item, group):
                continue
            if teacher and not self._matches_teacher(item, teacher):
                continue
            if room and _norm(room) not in _norm(item.get("room")):
                continue
            if day and _norm(day) != _norm(item.get("day")):
                continue
            if subject and _norm(subject) not in _norm(item.get("subject")):
                continue
            selected.append(item)

        def order(item: Dict[str, Any]) -> tuple:
            day_index = self._day_index(item.get("day")) if item.get("day") else 9
            start = self._hours.index(item["start"]) if item.get("start") in self._hours else 99
            return (day_index if day_index is not None else 9, start)

        selected.sort(key=order)
        return {
            "total": len(selected),
            "mostrades": min(len(selected), MAX_ROWS),
            "activitats": [self._row(item) for item in selected[:MAX_ROWS]],
        }

    def tool_get_problems(self) -> Dict[str, Any]:
        return {
            "conflictes": [f"[{item.get('type')}] {item.get('message')}" for item in self._conflicts[:40]],
            "sense_collocar": [
                f"{item.get('subject', '')} · {item.get('teacher', '')} · {item.get('group', '')}: "
                f"{'; '.join(item.get('constraints') or []) or item.get('reason', '')}"
                for item in self._unplaced[:40]
                if isinstance(item, dict)
            ],
        }

    def _teacher_records(self) -> List[Dict[str, Any]]:
        try:
            return list(self._repo.list_teacher_restrictions()) if self._repo else []
        except Exception:  # pragma: no cover
            return []

    def _group_records(self) -> List[Dict[str, Any]]:
        try:
            return list(self._repo.list_group_restrictions()) if self._repo else []
        except Exception:  # pragma: no cover
            return []

    def tool_get_restrictions(self, teacher: Optional[str] = None, group: Optional[str] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if teacher:
            found = [r for r in self._teacher_records() if _norm(teacher) in _norm(r.get("teacher"))]
            result["professors"] = [
                {
                    "professor": r.get("teacher"),
                    "no_disponible": _runs(_slots_of(r), self._hours) or "cap",
                    "maxim_de_dies": r.get("max_days"),
                }
                for r in found
            ] or "No hi ha restriccions registrades per a aquest professor."
        if group:
            found = [r for r in self._group_records() if _norm(group) == _norm(r.get("group"))]
            result["grups"] = [
                {
                    "grup": r.get("group"),
                    "no_disponible": _runs(_slots_of(r), self._hours) or "cap",
                    "maxim_de_dies": r.get("max_days"),
                    "dies_amb_descans": r.get("break_days") or [],
                }
                for r in found
            ] or "No hi ha restriccions registrades per a aquest grup."
        if not result:
            return {"error": "Indica un professor o un grup."}
        return result

    def tool_get_person_summary(self, teacher: Optional[str] = None, group: Optional[str] = None) -> Dict[str, Any]:
        if not teacher and not group:
            return {"error": "Indica un professor o un grup."}
        items = [
            item for item in self._activities
            if (teacher and self._matches_teacher(item, teacher)) or (group and self._matches_group(item, group))
        ]
        per_day: Dict[str, List[tuple]] = {}
        for item in items:
            if item.get("start") not in self._hours:
                continue
            start = self._hours.index(item["start"])
            per_day.setdefault(item["day"], []).append((start, start + int(item["duration"])))

        summary: Dict[str, str] = {}
        total_hours = 0.0
        for day in sorted(per_day, key=lambda name: self._day_index(name) if self._day_index(name) is not None else 9):
            merged: List[List[int]] = []
            for start, end in sorted(per_day[day]):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            hours = sum(end - start for start, end in merged) / 2
            gaps = sum(merged[i][0] - merged[i - 1][1] for i in range(1, len(merged)))
            total_hours += hours
            first, last = merged[0][0], merged[-1][1]
            last_label = self._hours[last] if last < len(self._hours) else "22:00"
            summary[day] = f"{self._hours[first]}-{last_label} | {hours:g} h de classe | {gaps} franges buides"
        return {
            "activitats": len(items),
            "dies": len(per_day),
            "hores_totals": round(total_hours, 1),
            "per_dia": summary or "Sense activitats.",
        }

    # ------------------------------------------------------------ move checks
    def _conflict_keys(self, activities: List[Dict[str, Any]]) -> set:
        schedule = Schedule()
        for item in activities:
            schedule.add(
                Activity(
                    id=item["id"], teacher=item["teacher"], subject=item["subject"], group=item["group"],
                    room=item.get("room") or "", day=item["day"], start=item["start"],
                    duration=int(item["duration"]), fixed=bool(item.get("fixed")),
                )
            )
        engine = SchedulerEngine()
        engine.load(schedule)
        return {(conflict.type, conflict.message) for conflict in engine.validate()}

    def _restriction_problems(self, item: Dict[str, Any], day: str, start_index: int) -> List[str]:
        covered = {f"{day} {self._hours[start_index + offset]}" for offset in range(int(item["duration"]))
                   if start_index + offset < len(self._hours)}
        problems: List[str] = []
        for record in self._teacher_records():
            if any(_norm(record.get("teacher")) == _norm(name) for name in (teacher_names(item["teacher"]) or [item["teacher"]])):
                blocked = covered & {slot for slot in _slots_of(record)}
                if blocked:
                    problems.append(f"El professor {record.get('teacher')} no està disponible a {', '.join(sorted(blocked))}.")
        for record in self._group_records():
            if _norm(record.get("group")) in {_norm(name) for name in (group_names(item["group"]) or [item["group"]])}:
                blocked = covered & {slot for slot in _slots_of(record)}
                if blocked:
                    problems.append(f"El grup {record.get('group')} no està disponible a {', '.join(sorted(blocked))}.")
        return problems

    def _gap_slots(self, activities: List[Dict[str, Any]], *, group: Optional[str] = None, teacher: Optional[str] = None) -> int:
        """Franges buides (entre primera i última classe de cada dia) d'un grup
        o d'un professor, sumades per a tota la setmana."""
        per_day: Dict[str, List[tuple]] = {}
        for item in activities:
            if group and not self._matches_group(item, group):
                continue
            if teacher and not self._matches_teacher(item, teacher):
                continue
            if item.get("start") not in self._hours:
                continue
            start = self._hours.index(item["start"])
            per_day.setdefault(item["day"], []).append((start, start + int(item["duration"])))
        total = 0
        for intervals in per_day.values():
            merged: List[List[int]] = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            total += sum(merged[i][0] - merged[i - 1][1] for i in range(1, len(merged)))
        return total

    def _impact(self, before: List[Dict[str, Any]], after: List[Dict[str, Any]], target: Dict[str, Any]) -> Dict[str, Any]:
        group = (group_names(target["group"]) or [target["group"]])[0]
        teacher = (teacher_names(target["teacher"]) or [target["teacher"]])[0]
        return {
            "forats_grup": [self._gap_slots(before, group=group), self._gap_slots(after, group=group)],
            "forats_professor": [self._gap_slots(before, teacher=teacher), self._gap_slots(after, teacher=teacher)],
            "nota": "[abans, després] en franges de 30 min buides entre classes d'un mateix dia",
        }

    def _dry_run(self, activity_id: Any, day: str, start: str) -> Dict[str, Any]:
        target = self._find(activity_id)
        if target is None:
            return {"ok": False, "error": "activitat_no_trobada"}
        canonical_day = self._canonical_day(day)
        canonical_start = self._canonical_hour(start)
        if canonical_day is None or canonical_start is None:
            return {"ok": False, "error": "dia_o_hora_invalids", "dies": DAY_NAMES, "hora_exemple": "10:30"}
        start_index = self._hours.index(canonical_start)
        if start_index + int(target["duration"]) > PERIODS_PER_DAY:
            return {"ok": False, "error": "no_hi_cap_abans_del_final_del_dia"}
        if target.get("fixed"):
            return {"ok": False, "error": "activitat_fixa", "detail": "Aquesta activitat és fixa i no es pot moure."}

        if self._baseline_keys is None:
            self._baseline_keys = self._conflict_keys(self._activities)
        moved = [dict(item) for item in self._activities]
        for item in moved:
            if str(item["id"]) == str(activity_id):
                item["day"], item["start"] = canonical_day, canonical_start
        new_conflicts = sorted(self._conflict_keys(moved) - self._baseline_keys)
        problems = self._restriction_problems(target, canonical_day, start_index)

        if new_conflicts or problems:
            return {
                "ok": False,
                "conflictes_nous": [f"[{kind}] {message}" for kind, message in new_conflicts[:10]],
                "restriccions": problems,
            }
        return {
            "ok": True,
            "day": canonical_day,
            "start": canonical_start,
            "impacte": self._impact(self._activities, moved, target),
        }

    def tool_check_move(self, activity_id: int, day: str, start: str) -> Dict[str, Any]:
        result = self._dry_run(activity_id, day, start)
        target = self._find(activity_id)
        if target is not None:
            result["activitat"] = self._row(target)
        return result

    def tool_find_free_slots(self, activity_id: int, day: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        target = self._find(activity_id)
        if target is None:
            return {"error": "activitat_no_trobada"}
        if target.get("fixed"):
            return {"error": "activitat_fixa"}
        days = [self._canonical_day(day)] if day else DAY_NAMES
        if day and days[0] is None:
            return {"error": "dia_invalid", "dies": DAY_NAMES}

        valid: List[tuple] = []
        for candidate_day in days:
            for index in range(PERIODS_PER_DAY - int(target["duration"]) + 1):
                if candidate_day == target["day"] and self._hours[index] == target["start"]:
                    continue
                check = self._dry_run(activity_id, candidate_day, self._hours[index])
                if check.get("ok"):
                    group_gaps = check["impacte"]["forats_grup"]
                    teacher_gaps = check["impacte"]["forats_professor"]
                    valid.append(
                        (
                            (group_gaps[1] - group_gaps[0], teacher_gaps[1] - teacher_gaps[0]),
                            f"{candidate_day} {self._hours[index]} (forats grup {group_gaps[0]}→{group_gaps[1]}, "
                            f"professor {teacher_gaps[0]}→{teacher_gaps[1]})",
                        )
                    )
        valid.sort(key=lambda entry: entry[0])  # primer les que menys forats afegeixen
        limit = max(1, min(int(limit or 10), 30))
        return {
            "activitat": self._row(target),
            "franges_valides": len(valid),
            "millors": [label for _, label in valid[:limit]],
            "nota": (
                "Vàlida = sense conflictes nous del motor ni franges no disponibles. Ordenades per menys "
                "forats afegits (grup i professor). No valora l'equilibri d'hores ni els 1Q/2Q."
            ),
        }

    # ----------------------------------------------------- proposals (pending)
    def tool_propose_move(self, activity_id: int, day: str, start: str, reason: str = "") -> Dict[str, Any]:
        check = self._dry_run(activity_id, day, start)
        if not check.get("ok"):
            return {"registrada": False, **check}
        target = self._find(activity_id)
        action = PendingAction(
            id=self._new_action_id(),
            kind="move",
            payload={"activity_id": target["id"], "day": check["day"], "start": check["start"]},
            description=(
                f"Moure «{target['subject']}» ({target['group']} · {target['teacher']}) de "
                f"{target['day']} {target['start']} a {check['day']} {check['start']}"
                + (f". Motiu: {reason}" if reason else "")
            ),
            source=self.source,
            proposal_id=self.proposal_id,
        )
        self._register_action(action)
        return {
            "registrada": True,
            "accio": action.public(),
            "nota": "Encara NO s'ha aplicat. La persona usuària ha de prémer 'Aplica'.",
        }

    def tool_propose_toggle_break(self, group: str, day: str, reason: str = "") -> Dict[str, Any]:
        canonical_day = self._canonical_day(day)
        if canonical_day is None:
            return {"registrada": False, "error": "dia_invalid", "dies": DAY_NAMES}
        if not any(self._matches_group(item, group) for item in self._activities):
            return {"registrada": False, "error": "grup_no_trobat"}
        has_break = any(
            _norm(record.get("group")) == _norm(group) and canonical_day in (record.get("break_days") or [])
            for record in self._group_records()
        )
        action = PendingAction(
            id=self._new_action_id(),
            kind="toggle_break",
            payload={"group": group, "day": canonical_day},
            description=(
                f"{'Treure' if has_break else 'Posar'} el descans del grup {group} el {canonical_day}"
                + (f". Motiu: {reason}" if reason else "")
            ),
            source=self.source,
            proposal_id=self.proposal_id,
        )
        self._register_action(action)
        return {
            "registrada": True,
            "accio": action.public(),
            "nota": "Encara NO s'ha aplicat. La persona usuària ha de prémer 'Aplica'.",
        }
