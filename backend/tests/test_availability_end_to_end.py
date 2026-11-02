"""Auditoria d'extrem a extrem de les franges no disponibles.

Carrega una escola fictícia (`synthetic_school.py`, sense cap Excel ni dades reals dins del
projecte), genera propostes, accepta la millor i assigna les hores de centre i de
coordinació, i comprova amb un verificador PROPI (que no fa servir el motor de validació) que cap activitat cau en
una franja no disponible del professor ni del grup.

Si algú toca un pas posterior a la generació (compactació, alineació, repartiment,
descansos, hores de centre...) i deixa una classe en una franja bloquejada, aquest test
ho detecta, tot i que el motor de validació no ho vegi.
"""

import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.bootstrap import reset_dependencies
from backend.main import app
from backend.tests.synthetic_school import build_workbook

HOURS = [f"{hour}:{minute}" for hour in range(8, 22) for minute in ("00", "30")]
INDEX = {name: position for position, name in enumerate(HOURS)}
NON_CLASS = ("Hores de centre", "Coordinació", "Reunió", "Descans", "Tutoria")
FIXED_MEETINGS = {("Reunió", "14:00"), ("Coordinació", "15:00")}


def _blocked(record):
    blocked = set()
    for text in record.get("unavailable_slots") or []:
        match = re.match(r"^(\S+?)[\s-]+(\d+:\d+)$", str(text).strip())
        if match:
            blocked.add((match.group(1), match.group(2)))
    return blocked


def _split(text):
    return [item.strip() for item in str(text or "").split(",") if item.strip()]


def _violations(activities, teacher_blocked, group_blocked):
    found = []
    for activity in activities:
        if activity["start"] not in INDEX:
            continue
        # Reunió i coordinació fixes del dimecres: el seu bloc ja consta com a no disponible.
        if activity["day"] == "Dimecres" and (activity["subject"], activity["start"]) in FIXED_MEETINGS:
            continue
        first = INDEX[activity["start"]]
        covered = [(activity["day"], HOURS[i]) for i in range(first, min(first + activity["duration"], len(HOURS)))]
        for teacher in _split(activity["teacher"]):
            if any(slot in teacher_blocked.get(teacher, set()) for slot in covered):
                found.append(("professor", teacher, activity["subject"], activity["group"], activity["day"], activity["start"]))
        if activity["subject"] in NON_CLASS:
            continue  # no ocupa la franja del grup
        for group in _split(activity["group"]):
            if any(slot in group_blocked.get(group, set()) for slot in covered):
                found.append(("grup", group, activity["subject"], activity["teacher"], activity["day"], activity["start"]))
    return found


def test_no_class_or_center_hour_lands_in_an_unavailable_slot_of_a_teacher_or_group():
    # Per defecte, l'escola fictícia. Per auditar les dades reals, indiqueu l'Excel (que ha de
    # ser FORA del projecte) amb la variable EMAD_AUDIT_XLSX.
    external = os.environ.get("EMAD_AUDIT_XLSX")
    reset_dependencies()
    client = TestClient(app)
    if external:
        workbook_bytes = Path(external).expanduser().read_bytes()
    else:
        workbook_bytes = build_workbook(client.get("/academic-data/spreadsheet/blank").content)
    response = client.post(
        "/academic-data/spreadsheet/import",
        files={"file": ("dades.xlsx", workbook_bytes, "application/octet-stream")},
    )
    assert response.status_code == 200

    teachers = [item["name"] for item in client.get("/academic-data/teachers").json()]
    groups = [item["name"] for item in client.get("/academic-data/groups").json()]
    teacher_blocked = {
        name: _blocked(client.get(f"/academic-data/teachers/{name}/restrictions").json()) for name in teachers
    }
    group_blocked = {
        name: _blocked(client.get(f"/academic-data/groups/{name}/restrictions").json()) for name in groups
    }
    assert any(teacher_blocked.values()) and any(group_blocked.values()), "l'Excel hauria de portar restriccions"

    result = client.post("/scheduler/generate", json={"requirement_ids": []}).json()
    assert result["proposals"]

    for number, proposal in enumerate(result["proposals"], start=1):
        assert _violations(proposal["activities"], teacher_blocked, group_blocked) == [], f"proposta {number}"

    best = result["best_proposal"]
    assert client.post(f"/scheduler/proposal/{best['id']}/accept").status_code == 200
    live = client.get("/scheduler/state").json()["activities"]
    assert _violations(live, teacher_blocked, group_blocked) == [], "horari actiu després d'acceptar"

    assert client.post("/scheduler/center-coordination-hours/assign").status_code == 200
    live = client.get("/scheduler/state").json()["activities"]
    assert _violations(live, teacher_blocked, group_blocked) == [], "horari actiu amb hores de centre"

    # Cap classe d'un grup de tarda abans de les 15:00.
    for activity in live:
        if activity["subject"] in NON_CLASS:
            continue
        if any(group in ("Comú", "GP", "GI") for group in _split(activity["group"])):
            assert INDEX[activity["start"]] >= INDEX["15:00"], activity


def test_the_validation_also_checks_the_time_window_of_each_group_of_a_combined_class():
    from backend.dependencies import get_scheduler_use_cases
    from backend.scheduler_engine.models import Activity

    reset_dependencies()
    use_cases = get_scheduler_use_cases()
    morning = [Activity(1, "Noëlle", "Foto UF3", "GI, GP", "", "Dimarts", "8:00", 4)]
    types = [c.type for c in use_cases._scheduler_engine.validate(use_cases._build_schedule(morning))]
    assert "group_time_window" in types

    afternoon = [Activity(1, "Noëlle", "Foto UF3", "GI, GP", "", "Dimarts", "15:00", 4)]
    assert "group_time_window" not in [
        c.type for c in use_cases._scheduler_engine.validate(use_cases._build_schedule(afternoon))
    ]
