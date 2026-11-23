"""Reparació exacta amb CP-SAT (OR-Tools) per als blocs que el voraç no col·loca.

El generador voraç és ràpid però pot deixar blocs sense col·locar encara que
existeixi un horari complet. Aquest mòdul replanteja el problema com a
programació per restriccions i, si hi ha solució, la retorna.

És OPCIONAL: si `ortools` no està instal·lat, `solver_available()` és fals i
el generador continua exactament com abans.

Regles modelades (les mateixes que el col·locador i el validador):
  - disponibilitat de professors i grups, finestra horària dels grups, dia fix
  - un professor / grup no pot fer dues coses alhora (excepte parelles 1Q/2Q)
  - distribucions de sessions permeses per assignatura, en dies diferents
  - màxim de dies per professor i per grup
  - forats de grup (GI/GP: màx. 1 franja buida al dia; la resta: 1 forat)
  - assignatures compartides GI+GP a l'inici o al final del dia
Preferències (el solver les maximitza, però mai a costa de deixar un bloc
sense col·locar):
  - parelles "Consecutiva amb": mateix dia, una darrere l'altra
  - parelles 1Q/2Q del mateix professor que comparteixen grup: mateixa franja
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
from .teacher_utils import teacher_names

# (índex del requeriment, ordre del bloc (1..n), durada en franges, dia, franja d'inici)
SolverPlacement = Tuple[int, int, int, int, int]

_STRICT_GAP_GROUPS = {"gi", "gp"}
_WEIGHT_CONSECUTIVE = 10
_WEIGHT_QUARTER = 3


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
                quarter.append((a, b))
    return consecutive, quarter


def _baseline_score(hint, consecutive, quarter) -> int:
    """Puntuació de preferències que ja té la solució parcial del voraç."""
    score = 0
    for a, b, dur_a, dur_b in consecutive:
        pa, pb = hint.get((a, 1)), hint.get((b, 1))
        if pa and pb and pa[0] == pb[0] and (pa[1] + dur_a == pb[1] or pb[1] + dur_b == pa[1]):
            score += _WEIGHT_CONSECUTIVE
    for a, b in quarter:
        pa, pb = hint.get((a, 1)), hint.get((b, 1))
        if pa and pb and pa == pb:
            score += _WEIGHT_QUARTER
    return score


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
        placements, score, _complete = _solve(requirements, context, limit, pins, consecutive, quarter)
        if placements is None:
            continue
        if best is None or score > best[0]:
            best = (score, placements)
        if score >= baseline:
            break  # ja iguala o millora el voraç: no cal moure més blocs
    return best[1] if best else None


def _solve(requirements, context, time_limit_s, pins, consecutive_pairs, quarter_pairs):
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
            if id(act) in fixed_ids:
                fixed_days[t.casefold()].add(act.day)
        for g in group_names(act.group_id):
            for p in slots:
                group_blocked.add((g, act.day, p))

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
        infos.append({"dists": dists, "teachers": t_names, "groups": g_names})
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

    objective = []
    max_score = 0
    for a_idx, b_idx, dur_a, dur_b in consecutive_pairs:
        day_a, st_a = day_start(a_idx)
        day_b, st_b = day_start(b_idx)
        joined = m.NewBoolVar(f"joined_{a_idx}_{b_idx}")
        order = m.NewBoolVar(f"order_{a_idx}_{b_idx}")
        m.Add(day_a == day_b).OnlyEnforceIf(joined)
        m.Add(st_a + dur_a == st_b).OnlyEnforceIf([joined, order])
        m.Add(st_b + dur_b == st_a).OnlyEnforceIf([joined, order.Not()])
        objective.append(_WEIGHT_CONSECUTIVE * joined)
        max_score += _WEIGHT_CONSECUTIVE

    for a_idx, b_idx in quarter_pairs:
        day_a, st_a = day_start(a_idx)
        day_b, st_b = day_start(b_idx)
        aligned = m.NewBoolVar(f"aligned_{a_idx}_{b_idx}")
        m.Add(day_a == day_b).OnlyEnforceIf(aligned)
        m.Add(st_a == st_b).OnlyEnforceIf(aligned)
        objective.append(_WEIGHT_QUARTER * aligned)
        max_score += _WEIGHT_QUARTER

    if objective:
        m.Maximize(sum(objective))

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
    score = round(solver.ObjectiveValue()) if objective else 0
    return placements, score, (not objective) or score >= max_score


def _slot(context: GenerationContext, day: int, period: int):
    from .models import TimeSlot

    return TimeSlot(day=day, period=period)
