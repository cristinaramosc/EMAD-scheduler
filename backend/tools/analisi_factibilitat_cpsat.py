#!/usr/bin/env python3
"""Anàlisi de factibilitat de l'horari amb un solver exacte (OR-Tools CP-SAT).

EINA D'ANÀLISI INDEPENDENT: no modifica l'aplicació ni les seves dades.
Llegeix un Excel amb la mateixa canonada que l'aplicació, captura els
requeriments i el context que arriben al generador i comprova si existeix
alguna solució que compleixi TOTES les restriccions.

Ús (des de backend/):
    pip install ortools
    python3 tools/analisi_factibilitat_cpsat.py /ruta/EMAD-dades-actuals.xlsx
    python3 tools/analisi_factibilitat_cpsat.py dades.xlsx --temps 120 --sortida solucio.txt

Regles modelades (les mateixes que fa servir el motor):
  base      disponibilitat de professors i grups, finestra horària dels grups,
            un professor/grup no pot fer dues coses alhora (excepte parelles
            1Q/2Q), dia fix, distribucions de sessions permeses per
            assignatura, sessions d'una assignatura en dies diferents
  tmax      màxim de dies per professor
  gmax      màxim de dies per grup
  gap       forats: GI/GP com a màxim 1 franja buida al dia; la resta, com a
            màxim 1 forat al dia
  edge      assignatures compartides GI+GP a l'inici o al final del dia
  cons      parelles "Consecutiva amb" (al motor són una preferència; aquí
            es proven com a obligatòries)
NO modelat: descansos de grup que s'insereixen després de la generació i
hores de dinar de professors. Un resultat "factible" aquí és, per tant, una
condició necessària, no una garantia sobre els descansos.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from collections import defaultdict

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

PERIODS = 27  # 8:00 .. 21:00 (la 21:30 només és marcador de final)
DAYS = 5
DAY_NAMES = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
FAMILIES = ["tmax", "gmax", "gap", "edge", "cons"]


def _hhmm(p: int) -> str:
    m = 8 * 60 + 30 * p
    return f"{m // 60}:{m % 60:02d}"


# --------------------------------------------------------------------------
# 1. Captura de les dades reals amb la canonada de l'aplicació
# --------------------------------------------------------------------------
def capture(xlsx_path: str):
    os.environ["EMAD_WORKING_TIMETABLE_FILE"] = os.path.join(tempfile.mkdtemp(), "wt.json")
    from bootstrap import build_dependencies
    from routes.academic_workbook_spreadsheet import import_workbook
    from scheduler_engine.generator import SchedulerGenerator

    captured = {}

    def _stop(self, requirements, context):
        captured["req"], captured["ctx"] = requirements, context
        raise SystemExit

    original = SchedulerGenerator.generate
    SchedulerGenerator.generate = _stop
    try:
        deps = build_dependencies()
        with open(xlsx_path, "rb") as handle:
            import_workbook(deps.academic_data_repo, handle.read())
        try:
            deps.scheduler_use_cases.generate_proposals_from_academic_data()
        except SystemExit:
            pass
    finally:
        SchedulerGenerator.generate = original
    if "req" not in captured:
        raise SystemExit("No s'han pogut capturar els requeriments (Excel buit?).")
    return captured["req"], captured["ctx"]


# --------------------------------------------------------------------------
# 2. Model
# --------------------------------------------------------------------------
class Problem:
    def __init__(self, requirements, context):
        from scheduler_engine.quarter_utils import group_names, normalize_group_name, parent_and_quarter
        from scheduler_engine.teacher_utils import teacher_names
        from services.block_generator import generate_block_distributions

        self.req = list(requirements)
        self.cfg = context.configuration
        self.group_names, self.teacher_names = group_names, teacher_names
        self.norm = normalize_group_name

        self.t_blocked, self.g_blocked = set(), set()
        for act in context.existing_scheduled_activities:
            slots = range(act.start_timeslot.period, act.start_timeslot.period + act.duration)
            for t in teacher_names(act.teacher_id):
                for p in slots:
                    self.t_blocked.add((t, act.day, p))
            for g in group_names(act.group_id):
                for p in slots:
                    self.g_blocked.add((g, act.day, p))

        windows = self.cfg.get("group_time_window_constraints") or {}
        self.windows = {self.norm(k): v["default"] for k, v in windows.items() if v.get("default")}
        self.tmax = {k.casefold(): v for k, v in (self.cfg.get("teacher_max_days_constraints") or {}).items()}
        self.gmax = {self.norm(k): v for k, v in (self.cfg.get("group_max_days_constraints") or {}).items()}

        day_index = {name.casefold(): i for i, name in enumerate(self.cfg.get("day_names") or DAY_NAMES)}
        self.info = []
        for r in self.req:
            dists = generate_block_distributions(r)
            fixed_day = day_index.get(str(r.fixed_day).casefold()) if r.fixed_day else None
            quarter = parent_and_quarter(r.group_id, r.subject_id)[1]
            self.info.append(
                dict(
                    r=r,
                    dists=dists,
                    teachers=teacher_names(r.teacher_id),
                    groups=group_names(r.group_id),
                    quarter=quarter,
                    fixed_day=fixed_day,
                    label=f"{r.subject_id} · {r.teacher_id} · {r.group_id}",
                )
            )

        pair_cfg = self.cfg.get("consecutive_pairs") or []
        self.pairs = []
        index = {(str(i["r"].subject_id).strip(), str(i["r"].group_id).strip(), str(i["r"].teacher_id).strip()): n
                 for n, i in enumerate(self.info)}
        for pair in pair_cfg:
            a, b = index.get(tuple(pair["a"])), index.get(tuple(pair["b"]))
            if a is not None and b is not None:
                self.pairs.append((a, b))

    def start_ok(self, info, dur, d, s, relax_avail=()):
        if s + dur > PERIODS:
            return False
        if info["fixed_day"] is not None and d != info["fixed_day"]:
            return False
        for p in range(s, s + dur):
            minute = 8 * 60 + 30 * p
            for t in info["teachers"]:
                if t not in relax_avail and (t, d, p) in self.t_blocked:
                    return False
            for g in info["groups"]:
                if (g, d, p) in self.g_blocked:
                    return False
                win = self.windows.get(g)
                if win and not (win[0] <= minute < win[1]):
                    return False
        return True


def solve(problem: Problem, families, time_limit, soft=False, relax_avail=(), workers=4, want_solution=False):
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    P = problem
    xs = []  # (idx, k, j, d, s, dur, var)
    dist_lit, placed_lit = {}, {}
    by_req_day = defaultdict(list)
    occ_terms = defaultdict(lambda: {"n": [], "1q": [], "2q": []})  # (kind,name,d,p)
    group_cover = defaultdict(list)  # (g,d,p) -> vars
    tday = defaultdict(list)  # (teacher,d) -> vars
    gday = defaultdict(list)
    block_vars = {}  # (idx,k,j) -> list[(d,s,dur,var)]
    impossible = []

    for idx, info in enumerate(P.info):
        r = info["r"]
        lits = []
        for k, dist in enumerate(info["dists"]):
            lit = m.NewBoolVar(f"dist_{idx}_{k}")
            lits.append(lit)
            dist_lit[(idx, k)] = lit
            for j, dur in enumerate(dist):
                options = []
                for d in range(DAYS):
                    for s in range(PERIODS):
                        if not P.start_ok(info, dur, d, s, relax_avail):
                            continue
                        v = m.NewBoolVar(f"x_{idx}_{k}_{j}_{d}_{s}")
                        options.append((d, s, dur, v))
                        xs.append((idx, k, j, d, s, dur, v))
                        by_req_day[(idx, d)].append(v)
                        q = info["quarter"]
                        cls = "1q" if q == "1q" else "2q" if q == "2q" else "n"
                        for p in range(s, s + dur):
                            for t in info["teachers"]:
                                occ_terms[("t", t, d, p)][cls].append(v)
                                if t in P.tmax:
                                    pass
                            for g in info["groups"]:
                                occ_terms[("g", g, d, p)][cls].append(v)
                                group_cover[(g, d, p)].append(v)
                        for t in info["teachers"]:
                            tday[(t.casefold(), d)].append(v)
                        for g in info["groups"]:
                            gday[(g, d)].append(v)
                block_vars[(idx, k, j)] = options
                if options:
                    m.Add(sum(o[3] for o in options) == 1).OnlyEnforceIf(lit)
                    m.Add(sum(o[3] for o in options) == 0).OnlyEnforceIf(lit.Not())
                else:
                    m.Add(lit == 0)
        if not lits:
            impossible.append(info["label"])
            placed = m.NewConstant(0)
        else:
            placed = m.NewBoolVar(f"placed_{idx}")
            m.Add(sum(lits) == placed)
        placed_lit[idx] = placed
        if not soft:
            m.Add(placed == 1)

    # sessions d'una assignatura en dies diferents
    for (idx, d), vs in by_req_day.items():
        if len(vs) > 1:
            m.Add(sum(vs) <= 1)

    # solapaments (professor i grup), amb excepció 1Q/2Q
    for key, terms in occ_terms.items():
        n, q1, q2 = terms["n"], terms["1q"], terms["2q"]
        if len(n) + max(len(q1), len(q2)) < 2 and len(q1) < 2 and len(q2) < 2 and len(n) < 2:
            continue
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

    # màxim de dies de professor i de grup
    if "tmax" in families:
        for t, limit in P.tmax.items():
            used = []
            for d in range(DAYS):
                vs = tday.get((t, d), [])
                if not vs:
                    continue
                u = m.NewBoolVar(f"tused_{t}_{d}")
                for v in vs:
                    m.AddImplication(v, u)
                used.append(u)
            if len(used) > limit:
                m.Add(sum(used) <= limit)
    if "gmax" in families:
        for g, limit in P.gmax.items():
            used = []
            for d in range(DAYS):
                vs = gday.get((g, d), [])
                if not vs:
                    continue
                u = m.NewBoolVar(f"gused_{g}_{d}")
                for v in vs:
                    m.AddImplication(v, u)
                used.append(u)
            if len(used) > limit:
                m.Add(sum(used) <= limit)

    # ocupació per grup/dia/franja per a forats i vores
    occ, pre, suf = {}, {}, {}
    need_occ = "gap" in families or "edge" in families
    if need_occ:
        groups = sorted({g for info in P.info for g in info["groups"]})
        for g in groups:
            for d in range(DAYS):
                for p in range(PERIODS):
                    vs = group_cover.get((g, d, p), [])
                    o = m.NewBoolVar(f"occ_{g}_{d}_{p}")
                    for v in vs:
                        m.AddImplication(v, o)
                    if vs:
                        m.Add(o <= sum(vs))
                    else:
                        m.Add(o == 0)
                    occ[(g, d, p)] = o
                # pre[p] = alguna franja ocupada abans de p; suf[p] = després de p
                for p in range(PERIODS):
                    a = m.NewBoolVar(f"pre_{g}_{d}_{p}")
                    b = m.NewBoolVar(f"suf_{g}_{d}_{p}")
                    pre[(g, d, p)], suf[(g, d, p)] = a, b
                for p in range(PERIODS):
                    a, b = pre[(g, d, p)], suf[(g, d, p)]
                    if p == 0:
                        m.Add(a == 0)
                    else:
                        prev = pre[(g, d, p - 1)]
                        m.AddImplication(occ[(g, d, p - 1)], a)
                        m.AddImplication(prev, a)
                        m.Add(a <= occ[(g, d, p - 1)] + prev)
                    if p == PERIODS - 1:
                        m.Add(b == 0)
                    else:
                        nxt = suf[(g, d, p + 1)]
                        m.AddImplication(occ[(g, d, p + 1)], b)
                        m.AddImplication(nxt, b)
                        m.Add(b <= occ[(g, d, p + 1)] + nxt)

    if "gap" in families:
        strict = {"gi", "gp"}
        for g in sorted({g for info in P.info for g in info["groups"]}):
            for d in range(DAYS):
                if g in strict:
                    gaps = []
                    for p in range(PERIODS):
                        gp = m.NewBoolVar(f"gap_{g}_{d}_{p}")
                        m.AddBoolOr([occ[(g, d, p)], pre[(g, d, p)].Not(), suf[(g, d, p)].Not(), gp])
                        gaps.append(gp)
                    m.Add(sum(gaps) <= 1)
                else:
                    starts = []
                    for p in range(PERIODS):
                        sp = m.NewBoolVar(f"run_{g}_{d}_{p}")
                        if p == 0:
                            m.AddBoolOr([occ[(g, d, p)].Not(), sp])
                        else:
                            m.AddBoolOr([occ[(g, d, p)].Not(), occ[(g, d, p - 1)], sp])
                        starts.append(sp)
                    m.Add(sum(starts) <= 2)

    if "edge" in families:
        for idx, k, j, d, s, dur, v in xs:
            if set(P.info[idx]["groups"]) != {"gi", "gp"}:
                continue
            for g in ("gi", "gp"):
                m.AddBoolOr([v.Not(), pre[(g, d, s)].Not(), suf[(g, d, s + dur - 1)].Not()])

    if "cons" in families:
        for a, b in P.pairs:
            ia, ib = P.info[a], P.info[b]
            if any(len(x["dists"]) == 0 or any(len(dd) != 1 for dd in x["dists"]) for x in (ia, ib)):
                continue
            da = {dd[0] for dd in ia["dists"]}
            db = {dd[0] for dd in ib["dists"]}
            if len(da) != 1 or len(db) != 1:
                continue
            dur_a, dur_b = da.pop(), db.pop()

            def expr(idx):
                day = sum(d * v for (i, k, j, d, s, du, v) in xs if i == idx)
                start = sum(s * v for (i, k, j, d, s, du, v) in xs if i == idx)
                return day, start

            day_a, start_a = expr(a)
            day_b, start_b = expr(b)
            both = m.NewBoolVar(f"cons_both_{a}_{b}")
            m.Add(both == 1).OnlyEnforceIf([placed_lit[a], placed_lit[b]])
            order = m.NewBoolVar(f"cons_order_{a}_{b}")
            m.Add(day_a == day_b).OnlyEnforceIf(both)
            m.Add(start_a + dur_a == start_b).OnlyEnforceIf([both, order])
            m.Add(start_b + dur_b == start_a).OnlyEnforceIf([both, order.Not()])

    if soft:
        m.Maximize(sum(placed_lit[i] for i in range(len(P.info))))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(m)
    name = solver.StatusName(status)
    result = {"status": name, "impossible": impossible, "vars": len(xs)}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        placed = [i for i in range(len(P.info)) if solver.Value(placed_lit[i])]
        result["placed"] = len(placed)
        result["unplaced"] = [P.info[i]["label"] for i in range(len(P.info)) if i not in set(placed)]
        if want_solution:
            sol = []
            for idx, k, j, d, s, dur, v in xs:
                if solver.Value(v):
                    sol.append((idx, d, s, dur))
            result["solution"] = sol
    return result


def write_solution(problem: Problem, solution, path):
    by_group = defaultdict(list)
    for idx, d, s, dur in solution:
        info = problem.info[idx]
        for g in info["groups"]:
            by_group[g].append((d, s, dur, info["label"]))
    with open(path, "w", encoding="utf-8") as out:
        for g in sorted(by_group):
            out.write(f"\n=== Grup {g.upper()} ===\n")
            for d, s, dur, label in sorted(by_group[g]):
                out.write(f"{DAY_NAMES[d]:10s} {_hhmm(s)}-{_hhmm(s + dur)}  {label}\n")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx")
    ap.add_argument("--temps", type=int, default=90, help="segons màxims per cada resolució (per defecte 90)")
    ap.add_argument("--sortida", default="solucio_cpsat.txt")
    ap.add_argument("--treballadors", type=int, default=4)
    args = ap.parse_args()

    req, ctx = capture(args.xlsx)
    problem = Problem(req, ctx)
    print(f"Requeriments: {len(req)} | parelles consecutives: {len(problem.pairs)}")
    zero = [i["label"] for i in problem.info if not i["dists"]]
    if zero:
        print("AVÍS: assignatures sense cap distribució de sessions possible:", zero)

    def run(label, fams, soft=False, relax=(), solution=False):
        t = time.perf_counter()
        res = solve(problem, fams, args.temps, soft=soft, relax_avail=relax, workers=args.treballadors, want_solution=solution)
        extra = ""
        if "placed" in res:
            extra = f" col·locades {res['placed']}/{len(req)}"
            if res["unplaced"]:
                extra += f" | sense col·locar: {res['unplaced']}"
        print(f"[{time.perf_counter() - t:5.1f}s] {label:45s} -> {res['status']}{extra}", flush=True)
        return res

    print("\n== Totes les restriccions, obligatòries ==")
    full = run("base + " + " + ".join(FAMILIES), FAMILIES, solution=True)
    if full["status"] in ("OPTIMAL", "FEASIBLE"):
        write_solution(problem, full["solution"], args.sortida)
        print(f"\nHi ha solució amb TOTES les restriccions. Escrita a {args.sortida}")
        return

    print("\n== Afegint restriccions de mica en mica ==")
    acc = []
    for fam in FAMILIES:
        acc.append(fam)
        res = run("base + " + " + ".join(acc), list(acc))
        if res["status"] == "INFEASIBLE":
            print(f"   >>> amb '{fam}' deixa de ser possible")
            break

    print("\n== Màxim de col·locables si cal renunciar a alguna cosa (totes les regles) ==")
    run("maximitzar assignatures col·locades", FAMILIES, soft=True)

    print("\n== Quina restricció cal relaxar? (traient-ne una cada cop) ==")
    for fam in FAMILIES:
        run(f"sense '{fam}'", [f for f in FAMILIES if f != fam])
    teachers = sorted({t for i in problem.info for t in i["teachers"]})
    for t in teachers:
        if any(key[0] == t for key in problem.t_blocked):
            run(f"sense la indisponibilitat de '{t}'", FAMILIES, relax=(t,))


if __name__ == "__main__":
    main()
