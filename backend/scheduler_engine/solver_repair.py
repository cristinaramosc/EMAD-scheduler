"""Reparació exacta amb CP-SAT (OR-Tools) per als blocs que el voraç no col·loca.

El generador voraç és ràpid però pot deixar blocs sense col·locar encara que
existeixi un horari complet. Aquest mòdul replanteja el problema com a
programació per restriccions i, si hi ha solució, la retorna.

És OPCIONAL: si `ortools` no està instal·lat, `solver_available()` és fals i
el generador continua exactament com abans.

Regles modelades (les mateixes que el col·locador i el validador):
  - disponibilitat de professors i grups, finestra horària dels grups, dia fix
  - un professor / grup no pot fer dues coses alhora (excepte parelles 1Q/2Q)
  - una aula no pot acollir dues activitats alhora
  - distribucions de sessions permeses per assignatura, en dies diferents
  - màxim de dies per professor i per grup
  - forats de grup (GI/GP: màx. 1 franja buida al dia; la resta: 1 forat)
  - assignatures compartides GI+GP a l'inici o al final del dia
Preferències (el solver les maximitza, però mai a costa de deixar un bloc
sense col·locar), per ordre d'importància:
  - parelles "Consecutiva amb": mateix dia, una darrere l'altra
  - parelles 1Q/2Q del mateix professor que comparteixen grup: mateixa hora d'inici o
    d'acabament (així una de 4 h i una de 3 h poden anar juntes i acabar a la vegada)
  - començar com més aviat millor, i que cada grup comenci aviat a CADA quadrimestre
    (les assignatures de tot el curs abans que les d'un sol quadrimestre)
No modela els descansos de grup: s'afegeixen després i, si no hi cap forat,
simplement se salten.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from backend.models.teaching_block import TeachingBlock
    from backend.services.block_generator import generate_block_distributions
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
    from services.block_generator import generate_block_distributions

from .models import GenerationContext
from .placement_strategy import GreedyPlacementStrategy
from .quarter_utils import group_names, is_valid_quarter_pair, parent_and_quarter
from .subject_utils import is_non_class_subject
from .teacher_utils import teacher_names

# (índex del requeriment, ordre del bloc (1..n), durada en franges, dia, franja d'inici)
SolverPlacement = Tuple[int, int, int, int, int]

_STRICT_GAP_GROUPS = {"gi", "gp"}
# Les parelles pesen molt més que l'hora: primer unir, després començar aviat.
_WEIGHT_CONSECUTIVE = 1000
_WEIGHT_QUARTER = 3000
_WEIGHT_SEMESTER_START = 10  # per franja de 30 min que un grup tarda a començar, en cada quadrimestre
_WEIGHT_LATENESS = 1  # per franja de 30 min d'inici tardà, per bloc
_POLISH_TIME_S = 3.0  # temps màxim de la passada que avança l'hora d'inici
_IMPROVE_TIME_S = 10.0  # temps màxim per millorar les parelles que han quedat sense complir
_IMPROVE_STEP_S = 4.0


def solver_available() -> bool:
    try:
        import ortools.sat.python.cp_model  # noqa: F401
    except Exception:  # pragma: no cover
        return False
    return True


def _single_duration(dists) -> Optional[int]:
    if not dists or any(len(x) != 1 for x in dists) or len({x[0] for x in dists}) != 1:
        return None
    return dists[0][0]


def _preference_pairs(requirements, pairs):
    """Parelles que el solver intenta complir: (consecutives, 1Q/2Q).

    Només es modelen els requeriments amb una sola sessió de durada fixa
    (la resta se salten: no es poden alinear sense triar distribució)."""
    durations = [_single_duration(generate_block_distributions(r)) for r in requirements]
    consecutive = [
        (a, b, durations[a], durations[b])
        for a, b in pairs
        if durations[a] is not None and durations[b] is not None
    ]
    teachers = [set(teacher_names(r.teacher_id)) for r in requirements]
    quarter = []
    for a in range(len(requirements)):
        for b in range(a + 1, len(requirements)):
            if durations[a] is None or durations[b] is None or not (teachers[a] & teachers[b]):
                continue
            ra, rb = requirements[a], requirements[b]
            if is_valid_quarter_pair(ra.group_id, ra.subject_id, rb.group_id, rb.subject_id):
                quarter.append((a, b, durations[a], durations[b]))
    return consecutive, quarter


def _quarter_aligned(pa, pb, dur_a, dur_b) -> bool:
    """Mateix dia i mateixa hora d'inici o d'acabament."""
    return bool(pa and pb and pa[0] == pb[0] and (pa[1] == pb[1] or pa[1] + dur_a == pb[1] + dur_b))


def _unsatisfied_pairs(positions, consecutive, quarter):
    """Parelles que NO es compleixen amb les posicions donades.

    `positions` és {(índex requeriment, ordre bloc): (dia, franja)}. Retorna
    (consecutives_no_unides, quarters_no_alineades), amb parelles d'índexs."""
    bad_consecutive = []
    for a, b, dur_a, dur_b in consecutive:
        pa, pb = positions.get((a, 1)), positions.get((b, 1))
        joined = bool(pa and pb and pa[0] == pb[0] and (pa[1] + dur_a == pb[1] or pb[1] + dur_b == pa[1]))
        if not joined:
            bad_consecutive.append((a, b))
    bad_quarter = [
        (a, b) for a, b, dur_a, dur_b in quarter
        if not _quarter_aligned(positions.get((a, 1)), positions.get((b, 1)), dur_a, dur_b)
    ]
    return bad_consecutive, bad_quarter


def _baseline_score(hint, consecutive, quarter) -> int:
    """Puntuació de preferències que ja té la solució parcial del voraç."""
    bad_consecutive, bad_quarter = _unsatisfied_pairs(hint, consecutive, quarter)
    placed = lambda a, b: bool(hint.get((a, 1)) and hint.get((b, 1)))
    good_consecutive = sum(1 for a, b, _da, _db in consecutive if placed(a, b) and (a, b) not in bad_consecutive)
    good_quarter = sum(1 for a, b, _da, _db in quarter if placed(a, b) and (a, b) not in bad_quarter)
    return _WEIGHT_CONSECUTIVE * good_consecutive + _WEIGHT_QUARTER * good_quarter


def solve_requirements(
    requirements: Sequence,
    context: GenerationContext,
    *,
    time_limit_s: float = 20.0,
    hint: Optional[Dict[Tuple[int, int], Tuple[int, int]]] = None,
    consecutive_pairs: Optional[Sequence[Tuple[int, int]]] = None,
) -> Optional[List[SolverPlacement]]:
    """Intenta col·locar TOTS els requeriments. Retorna les col·locacions o None.

    `hint` és {(índex requeriment, ordre bloc): (dia, franja)}: la solució
    parcial del voraç. Es conserva tant com sigui possible: primer es fixa tot
    el que el voraç ha col·locat i només es resolen els blocs que han fallat;
    si així no s'aconsegueix unir totes les parelles, s'allibera per capes el
    que comparteix professor o grup, i l'última capa ho allibera tot. Es
    retorna la millor solució completa (més parelles unides; en cas d'empat,
    la que mou menys blocs).
    `consecutive_pairs` són parelles d'índexs de requeriment que haurien d'anar
    seguides el mateix dia.
    """
    if not solver_available():
        return None
    import time

    pairs = list(consecutive_pairs or [])
    hint = dict(hint or {})
    deadline = time.perf_counter() + float(time_limit_s)

    resources = []
    unplaced = set()
    for index, requirement in enumerate(requirements):
        resources.append(set(teacher_names(requirement.teacher_id)) | set(group_names(requirement.group_id)))
        placed_blocks = sum(1 for (i, _order) in hint if i == index)
        counts = {len(dist) for dist in generate_block_distributions(requirement)}
        if placed_blocks not in counts:
            unplaced.add(index)

    # capes: conjunt de requeriments alliberats a cada intent
    freed = set(unplaced)
    layers = [set(freed)]
    for _ in range(2):
        used = set().union(*(resources[i] for i in freed)) if freed else set()
        freed = freed | {i for i, res in enumerate(resources) if res & used}
        layers.append(set(freed))
    layers.append(None)  # tot lliure

    consecutive, quarter = _preference_pairs(requirements, pairs)
    baseline = _baseline_score(hint, consecutive, quarter)

    best = None  # (puntuació, placements)
    best_from_free_layer = False
    seen = []
    for layer in layers:
        if layer is not None and layer in seen:
            continue
        seen.append(layer)
        remaining = deadline - time.perf_counter()
        if remaining <= 0.5:
            break
        last = layer is None
        pins = {} if last else {key: value for key, value in hint.items() if key[0] not in layer}
        limit = remaining if last else min(4.0, remaining)
        placements, score, _complete = _solve(
            requirements, context, limit, pins, consecutive, quarter,
            polish_from_score=baseline, polish_limit_s=min(_POLISH_TIME_S, max(deadline - time.perf_counter(), 0.0)),
        )
        if placements is None:
            continue
        if best is None or score > best[0]:
            best = (score, placements)
            best_from_free_layer = last
        if score >= baseline:
            break  # ja iguala o millora el voraç: no cal moure més blocs
    if best is None:
        return None
    if best_from_free_layer:
        return best[1]  # ja s'ha cercat amb tot lliure: alliberar més no hi afegiria res

    # Millora dirigida: es llibera només el voltant de les parelles que encara
    # no es compleixen (primer els propis requeriments, després els que
    # comparteixen professor o grup), fixant la resta a la solució actual.
    max_score = _WEIGHT_CONSECUTIVE * len(consecutive) + _WEIGHT_QUARTER * len(quarter)
    improve_deadline = min(deadline + _IMPROVE_TIME_S, time.perf_counter() + _IMPROVE_TIME_S)
    score, placements = best
    while score < max_score and improve_deadline - time.perf_counter() > 0.5:
        positions = {(i, o): (d, st) for (i, o, _du, d, st) in placements}
        bad_consecutive, bad_quarter = _unsatisfied_pairs(positions, consecutive, quarter)
        seeds = {index for pair in (*bad_consecutive, *bad_quarter) for index in pair}
        if not seeds:
            break
        improved = False
        freed = set(seeds)
        for radius in range(3):
            if radius:
                used = set().union(*(resources[i] for i in freed))
                freed = freed | {i for i, res in enumerate(resources) if res & used}
            remaining = improve_deadline - time.perf_counter()
            if remaining <= 0.5:
                break
            pins = {key: value for key, value in positions.items() if key[0] not in freed}
            candidate, new_score, _ = _solve(
                requirements, context, min(_IMPROVE_STEP_S, remaining), pins, consecutive, quarter,
                polish_from_score=score, polish_limit_s=min(2.0, max(improve_deadline - time.perf_counter(), 0.0)),
            )
            if candidate is not None and new_score > score:
                score, placements, improved = new_score, candidate, True
                break
        if not improved:
            break
    return placements


def _solve(requirements, context, time_limit_s, pins, consecutive_pairs, quarter_pairs,
           polish_from_score=None, polish_limit_s=0.0):
    from ortools.sat.python import cp_model

    calendar = context.school_calendar
    periods = int(calendar.periods_per_day)
    days = len(calendar.days)
    config = context.configuration or {}
    day_names = config.get("day_names") or []
    hour_names = config.get("hour_names") or []
    day_index = {str(n).strip().casefold(): i for i, n in enumerate(day_names)}

    # --- disponibilitat (activitats sintètiques i fixes del context) ---------
    teacher_blocked, group_blocked = set(), set()
    fixed_days: Dict[str, set] = defaultdict(set)
    fixed_ids = {id(a) for a in context.fixed_activities}
    for act in context.existing_scheduled_activities:
        slots = range(act.start_timeslot.period, act.start_timeslot.period + act.duration)
        for t in teacher_names(act.teacher_id):
            for p in slots:
                teacher_blocked.add((t, act.day, p))
            # Les coordinacions, reunions i hores de centre fixes no compten
            # com a dia de classe del professor (igual que al validador).
            if id(act) in fixed_ids and not is_non_class_subject((act.teaching_block.metadata or {}).get("subject")):
                fixed_days[t.casefold()].add(act.day)
        for g in group_names(act.group_id):
            for p in slots:
                group_blocked.add((g, act.day, p))

    rooms_enabled = bool(config.get("room_constraints_enabled", True))
    room_blocked = set()
    if rooms_enabled:
        for act in context.existing_scheduled_activities:
            room = str(act.room_id or "").strip().casefold()
            if room:
                for p in range(act.start_timeslot.period, act.start_timeslot.period + act.duration):
                    room_blocked.add((room, act.day, p))

    teacher_max = {str(k).casefold(): int(v) for k, v in (config.get("teacher_max_days_constraints") or {}).items()}
    group_max = {}
    for key, value in (config.get("group_max_days_constraints") or {}).items():
        for name in group_names(key) or (str(key).casefold(),):
            group_max[name] = int(value)

    strategy = GreedyPlacementStrategy()

    def fixed_period(requirement) -> Optional[int]:
        text = str(requirement.fixed_start or "").strip()
        if not text or text not in hour_names:
            return None
        return hour_names.index(text)

    m = cp_model.CpModel()
    infos = []
    xs = []  # (idx, k, j, d, s, dur, var)
    dist_lit: Dict[Tuple[int, int], object] = {}
    by_req_day = defaultdict(list)
    cover = defaultdict(lambda: {"n": [], "1q": [], "2q": []})
    room_cover = defaultdict(list)
    group_cover = defaultdict(list)
    teacher_day = defaultdict(list)
    group_day = defaultdict(list)
    placed_total = []

    for idx, requirement in enumerate(requirements):
        dists = generate_block_distributions(requirement)
        t_names = teacher_names(requirement.teacher_id)
        g_names = group_names(requirement.group_id)
        quarter = parent_and_quarter(requirement.group_id, requirement.subject_id)[1]
        klass = "1q" if quarter == "1q" else "2q" if quarter == "2q" else "n"
        fixed_day = day_index.get(str(requirement.fixed_day).strip().casefold()) if requirement.fixed_day else None
        pinned_start = fixed_period(requirement) if fixed_day is not None else None
        room = ""
        if rooms_enabled and getattr(requirement, "preferred_rooms", None):
            room = str(requirement.preferred_rooms[0] or "").strip().casefold()
        infos.append({"dists": dists, "teachers": t_names, "groups": g_names, "klass": klass})
        if not dists:
            return None, 0, False
        lits = []
        for k, dist in enumerate(dists):
            lit = m.NewBoolVar(f"d_{idx}_{k}")
            lits.append(lit)
            dist_lit[(idx, k)] = lit
            for j, dur in enumerate(dist):
                probe = TeachingBlock(
                    id=f"probe-{idx}-{k}-{j}",
                    duration=0.5,
                    order=j + 1,
                    duration_blocks=dur,
                    metadata={"group_id": requirement.group_id, "group": str(requirement.group_id)},
                )
                options = []
                for d in range(days):
                    if fixed_day is not None and d != fixed_day:
                        continue
                    for s in range(periods - dur + 1):
                        if pinned_start is not None and s != pinned_start:
                            continue
                        slots = range(s, s + dur)
                        if any((t, d, p) in teacher_blocked for t in t_names for p in slots):
                            continue
                        if any((g, d, p) in group_blocked for g in g_names for p in slots):
                            continue
                        if strategy._group_time_window_conflict_exists(
                            probe, _slot(context, d, s), context
                        ):
                            continue
                        if room and any((room, d, p) in room_blocked for p in slots):
                            continue
                        v = m.NewBoolVar(f"x_{idx}_{k}_{j}_{d}_{s}")
                        options.append(v)
                        xs.append((idx, k, j, d, s, dur, v))
                        by_req_day[(idx, d)].append(v)
                        for p in slots:
                            for t in t_names:
                                cover[("t", t, d, p)][klass].append(v)
                            for g in g_names:
                                cover[("g", g, d, p)][klass].append(v)
                                group_cover[(g, d, p)].append(v)
                        if room:
                            for p in slots:
                                room_cover[(room, d, p)].append(v)
                        for t in t_names:
                            teacher_day[(t.casefold(), d)].append(v)
                        for g in g_names:
                            group_day[(g, d)].append(v)
                if options:
                    m.Add(sum(options) == 1).OnlyEnforceIf(lit)
                    m.Add(sum(options) == 0).OnlyEnforceIf(lit.Not())
                else:
                    m.Add(lit == 0)
        m.Add(sum(lits) == 1)

    for (idx, d), vs in by_req_day.items():
        if len(vs) > 1:
            m.Add(sum(vs) <= 1)

    for terms in cover.values():
        n, q1, q2 = terms["n"], terms["1q"], terms["2q"]
        if len(n) > 1:
            m.Add(sum(n) <= 1)
        if len(q1) > 1:
            m.Add(sum(q1) <= 1)
        if len(q2) > 1:
            m.Add(sum(q2) <= 1)
        if n and q1:
            m.Add(sum(n) + sum(q1) <= 1)
        if n and q2:
            m.Add(sum(n) + sum(q2) <= 1)

    for variables in room_cover.values():
        if len(variables) > 1:
            m.Add(sum(variables) <= 1)

    def add_max_days(day_vars, name, limit, preset_days=()):
        used = []
        for d in range(days):
            if d in preset_days:
                continue
            vs = day_vars.get((name, d), [])
            if not vs:
                continue
            u = m.NewBoolVar(f"used_{name}_{d}")
            for v in vs:
                m.AddImplication(v, u)
            used.append(u)
        free = limit - len(preset_days)
        if free < len(used):
            m.Add(sum(used) <= max(free, 0))

    for name, limit in teacher_max.items():
        add_max_days(teacher_day, name, limit, fixed_days.get(name, set()))
    for name, limit in group_max.items():
        add_max_days(group_day, name, limit)

    # --- ocupació per grup/dia/franja: forats i vora del dia ------------------
    all_groups = sorted({g for info in infos for g in info["groups"]})
    occ, pre, suf = {}, {}, {}
    for g in all_groups:
        for d in range(days):
            for p in range(periods):
                vs = group_cover.get((g, d, p), [])
                o = m.NewBoolVar(f"o_{g}_{d}_{p}")
                for v in vs:
                    m.AddImplication(v, o)
                m.Add(o <= sum(vs)) if vs else m.Add(o == 0)
                occ[(g, d, p)] = o
                pre[(g, d, p)] = m.NewBoolVar(f"pre_{g}_{d}_{p}")
                suf[(g, d, p)] = m.NewBoolVar(f"suf_{g}_{d}_{p}")
            for p in range(periods):
                a, b = pre[(g, d, p)], suf[(g, d, p)]
                if p == 0:
                    m.Add(a == 0)
                else:
                    m.AddImplication(occ[(g, d, p - 1)], a)
                    m.AddImplication(pre[(g, d, p - 1)], a)
                    m.Add(a <= occ[(g, d, p - 1)] + pre[(g, d, p - 1)])
                if p == periods - 1:
                    m.Add(b == 0)
                else:
                    m.AddImplication(occ[(g, d, p + 1)], b)
                    m.AddImplication(suf[(g, d, p + 1)], b)
                    m.Add(b <= occ[(g, d, p + 1)] + suf[(g, d, p + 1)])
            if g in _STRICT_GAP_GROUPS:
                gaps = []
                for p in range(periods):
                    gp = m.NewBoolVar(f"gap_{g}_{d}_{p}")
                    m.AddBoolOr([occ[(g, d, p)], pre[(g, d, p)].Not(), suf[(g, d, p)].Not(), gp])
                    gaps.append(gp)
                m.Add(sum(gaps) <= 1)
            else:
                runs = []
                for p in range(periods):
                    sp = m.NewBoolVar(f"run_{g}_{d}_{p}")
                    if p == 0:
                        m.AddBoolOr([occ[(g, d, p)].Not(), sp])
                    else:
                        m.AddBoolOr([occ[(g, d, p)].Not(), occ[(g, d, p - 1)], sp])
                    runs.append(sp)
                m.Add(sum(runs) <= 2)

    for idx, k, j, d, s, dur, v in xs:
        if set(infos[idx]["groups"]) == _STRICT_GAP_GROUPS:
            for g in _STRICT_GAP_GROUPS:
                m.AddBoolOr([v.Not(), pre[(g, d, s)].Not(), suf[(g, d, s + dur - 1)].Not()])

    # --- preferències: consecutives i 1Q/2Q a la mateixa franja ------------------
    def day_start(idx):
        day = sum(d * v for (i, _k, _j, d, _s, _du, v) in xs if i == idx)
        start = sum(s_ * v for (i, _k, _j, _d, s_, _du, v) in xs if i == idx)
        return day, start

    pair_terms = []
    for a_idx, b_idx, dur_a, dur_b in consecutive_pairs:
        day_a, st_a = day_start(a_idx)
        day_b, st_b = day_start(b_idx)
        joined = m.NewBoolVar(f"joined_{a_idx}_{b_idx}")
        order = m.NewBoolVar(f"order_{a_idx}_{b_idx}")
        m.Add(day_a == day_b).OnlyEnforceIf(joined)
        m.Add(st_a + dur_a == st_b).OnlyEnforceIf([joined, order])
        m.Add(st_b + dur_b == st_a).OnlyEnforceIf([joined, order.Not()])
        pair_terms.append(_WEIGHT_CONSECUTIVE * joined)

    for a_idx, b_idx, dur_a, dur_b in quarter_pairs:
        day_a, st_a = day_start(a_idx)
        day_b, st_b = day_start(b_idx)
        aligned = m.NewBoolVar(f"aligned_{a_idx}_{b_idx}")
        same_start = m.NewBoolVar(f"same_start_{a_idx}_{b_idx}")
        same_end = m.NewBoolVar(f"same_end_{a_idx}_{b_idx}")
        m.Add(day_a == day_b).OnlyEnforceIf(aligned)
        m.AddBoolOr([same_start, same_end]).OnlyEnforceIf(aligned)
        m.Add(st_a == st_b).OnlyEnforceIf(same_start)
        m.Add(st_a + dur_a == st_b + dur_b).OnlyEnforceIf(same_end)
        pair_terms.append(_WEIGHT_QUARTER * aligned)

    late_terms = [_WEIGHT_LATENESS * s_ * v for (_i, _k, _j, _d, s_, _du, v) in xs if s_ > 0]
    if pair_terms:
        m.Maximize(sum(pair_terms))

    # --- blocs fixats a la posició que ja tenien al voraç -------------------------
    by_block = defaultdict(list)
    for idx, k, j, d, s, dur, v in xs:
        by_block[(idx, j + 1)].append((d, s, v))
    for (idx, order), (day, start) in pins.items():
        candidates = [v for d, s, v in by_block.get((idx, order), []) if d == day and s == start]
        if candidates:
            m.Add(sum(candidates) == 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_workers = max(1, min(4, os.cpu_count() or 1))
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, 0, False
    placements = [
        (idx, j + 1, dur, d, s_)
        for idx, k, j, d, s_, dur, v in xs
        if solver.Value(v)
    ]
    score = sum(solver.Value(term) for term in pair_terms)

    # Fase 2: amb la solució trobada com a punt de partida, s'intenta que els
    # blocs comencin més aviat sense perdre cap parella unida.
    if late_terms and polish_limit_s > 0.5 and (polish_from_score is None or score >= polish_from_score):
        for _i, _k, _j, _d, _s, _du, v in xs:
            m.AddHint(v, solver.Value(v))
        if pair_terms:
            m.Add(sum(pair_terms) >= score)
        start_terms = _semester_start_terms(m, xs, infos, periods, days)
        m.Minimize(sum(late_terms) + _WEIGHT_SEMESTER_START * sum(start_terms))
        solver2 = cp_model.CpSolver()
        solver2.parameters.max_time_in_seconds = float(polish_limit_s)
        solver2.parameters.num_workers = solver.parameters.num_workers
        if solver2.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            placements = [
                (idx, j + 1, dur, d, s_)
                for idx, k, j, d, s_, dur, v in xs
                if solver2.Value(v)
            ]
            score = sum(solver2.Value(term) for term in pair_terms)
    return placements, score, True


def _semester_start_terms(m, xs, infos, periods, days):
    """Per a cada grup, dia i quadrimestre: franges buides abans de la primera
    classe d'aquell quadrimestre (les assignatures de tot el curs compten als
    dos). Minimitzar-ho fa que cap grup comenci tard a cap quadrimestre, és a
    dir, que una assignatura d'un sol quadrimestre no vagi abans de les de
    tot el curs."""
    cover = defaultdict(list)
    for idx, _k, _j, d, s_, dur, v in xs:
        klass = infos[idx]["klass"]
        semesters = ("1q", "2q") if klass == "n" else (klass,)
        for group in infos[idx]["groups"]:
            for p in range(s_, s_ + dur):
                for semester in semesters:
                    cover[(group, d, p, semester)].append(v)
    terms = []
    groups = sorted({g for info in infos for g in info["groups"]})
    for group in groups:
        for semester in ("1q", "2q"):
            for d in range(days):
                if not any(cover.get((group, d, p, semester)) for p in range(periods)):
                    continue
                prefix = []
                for p in range(periods):
                    here = cover.get((group, d, p, semester), [])
                    reached = m.NewBoolVar(f"sem_{group}_{semester}_{d}_{p}")
                    for v in here:
                        m.AddImplication(v, reached)
                    if prefix:
                        m.AddImplication(prefix[-1], reached)
                        m.Add(reached <= sum(here) + prefix[-1])
                    else:
                        m.Add(reached <= sum(here)) if here else m.Add(reached == 0)
                    prefix.append(reached)
                # franges buides abans de la primera classe (0 si el dia és buit)
                terms.append(periods * prefix[-1] - sum(prefix))
    return terms


def _slot(context: GenerationContext, day: int, period: int):
    from .models import TimeSlot

    return TimeSlot(day=day, period=period)
