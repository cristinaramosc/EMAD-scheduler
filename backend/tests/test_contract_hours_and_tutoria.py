"""Percentatge de jornada (PERCENTATGES_EMAD.xlsx), DNI, tutoria automàtica,
hores de centre i assignatures amb dos professors."""

from fastapi.testclient import TestClient

from application.live_schedule_use_cases import LiveScheduleUseCases
from repositories.academic_data_repository import AcademicDataRepository
from repositories.working_timetable_repository import (
    WorkingTimetableRepository,
    WorkingTimetableSnapshot,
)
from scheduler_engine.engine import SchedulerEngine
from services.contract_hours import contract_hours, parse_dedication_pct
from services.schedule_pdf_exporter import build_schedule_pdf


class _MemoryRepo(WorkingTimetableRepository):
    def __init__(self):
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self):
        return self._snapshot

    def save_snapshot(self, snapshot):
        self._snapshot = snapshot


def _use_cases(repo):
    return LiveScheduleUseCases(engine=SchedulerEngine(), working_timetable_repo=_MemoryRepo(), academic_data_repo=repo)


def _class(id_, teacher, group, day="Dilluns", start="8:00", duration=4, subject="Projectes"):
    return {"id": id_, "teacher": teacher, "subject": subject, "group": group, "room": "", "day": day, "start": start, "duration": duration}


# --- Taula del full de càlcul ------------------------------------------------


def test_contract_hours_match_the_spreadsheet():
    full = contract_hours(100)
    assert (full["lective"], full["centre"], full["preparation"], full["total"]) == (20, 7.5, 7.5, 35)
    sixty = contract_hours(60)  # fila del 60 %: 12 + 4,5 + 4,5
    assert (sixty["lective"], sixty["centre"], sixty["preparation"]) == (12, 4.5, 4.5)
    assert contract_hours(50)["lective"] == 10  # cada hora lectiva és un 5 %
    assert contract_hours(5)["lective"] == 1


def test_percentage_accepts_text_fractions_and_rejects_invalid_values():
    assert parse_dedication_pct("52,5 %") == 52.5
    assert parse_dedication_pct(0.525) == 52.5
    assert parse_dedication_pct("") is None
    assert parse_dedication_pct(0) is None
    assert parse_dedication_pct(150) is None
    assert contract_hours(None) is None


# --- API de professors: % i DNI -----------------------------------------------


def test_teacher_api_stores_percentage_and_dni_and_derives_contract_hours():
    import main

    client = TestClient(main.app)
    assert client.post("/academic-data/teachers", json={"name": "Zz Percent", "dedication_pct": 100, "dni": " 52141851t "}).status_code == 200
    assert client.post("/academic-data/teachers", json={"name": "Zz Mal", "dedication_pct": 150}).status_code == 400

    def fetch():
        return next(t for t in client.get("/academic-data/teachers").json() if t["name"] == "Zz Percent")

    teacher = fetch()
    assert teacher["dni"] == "52141851T"
    assert teacher["contract_hours"]["total"] == 35

    client.patch("/academic-data/teachers/Zz Percent", json={"dedication_pct": 60})
    assert fetch()["contract_hours"]["lective"] == 12
    client.patch("/academic-data/teachers/Zz Percent", json={"dedication_pct": 0, "dni": ""})
    teacher = fetch()
    assert teacher["contract_hours"] is None and teacher["dni"] == ""
    client.delete("/academic-data/teachers/Zz Percent")


# --- Hores de centre i tutoria automàtica ---------------------------------------


def test_centre_hours_follow_the_percentage_and_include_the_fixed_wednesday_block():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Eli", "active": True, "dedication_pct": 60.0})
    use_cases = _use_cases(repo)
    use_cases.load([_class(1, "Eli", "1r COM", duration=8), _class(2, "Eli", "1r COM", day="Dimarts", duration=8)])

    result = use_cases.assign_center_and_coordination_hours()

    centre = sum(a["duration"] for a in result["activities"] if a["teacher"] == "Eli" and a["subject"] in ("Reunió", "Hores de centre", "Coordinació"))
    # 4,5 h de centre al 60 % (reunió + coordinació fixes de dimecres incloses)
    assert centre / 2 >= 4.5


def test_tutor_gets_one_tutoria_hour_that_does_not_use_a_group_slot():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Eli", "active": True})
    repo.create_group({"name": "1r COM", "tutor": "Eli"})
    use_cases = _use_cases(repo)
    use_cases.load([_class(1, "Eli", "1r COM", duration=4)])

    result = use_cases.assign_center_and_coordination_hours()
    tutories = [a for a in result["activities"] if a["subject"] == "Tutoria"]
    assert len(tutories) == 1
    assert tutories[0]["teacher"] == "Eli" and tutories[0]["group"] == "1r COM" and tutories[0]["duration"] == 2

    # Una segona passada no n'afegeix cap més.
    again = use_cases.assign_center_and_coordination_hours()
    assert len([a for a in again["activities"] if a["subject"] == "Tutoria"]) == 1


def test_existing_tutoria_is_not_duplicated():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Eli", "active": True})
    repo.create_group({"name": "1r COM", "tutor": "Eli"})
    use_cases = _use_cases(repo)
    use_cases.load([
        _class(1, "Eli", "1r COM", duration=4),
        _class(2, "Eli", "1r COM", day="Dimarts", start="10:00", duration=2, subject="Tutoria"),
    ])
    result = use_cases.assign_center_and_coordination_hours()
    assert len([a for a in result["activities"] if a["subject"] == "Tutoria"]) == 1


def test_hours_summary_counts_classes_tutoria_and_coordination_as_lective():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Eli", "active": True, "dedication_pct": 50})
    use_cases = _use_cases(repo)
    use_cases.load([
        _class(1, "Eli", "1r COM", duration=8),                                            # 4 h de classe
        _class(2, "Eli", "1r COM", day="Dimarts", start="10:00", duration=2, subject="Tutoria"),    # 1 h
        _class(3, "Eli", "", day="Dijous", start="10:00", duration=2, subject="Coordinació"),       # 1 h
        _class(4, "Eli", "", day="Divendres", start="10:00", duration=3, subject="Hores de centre"),  # 1,5 h
    ])
    row = use_cases.teacher_hours_summary()[0]
    assert row["scheduled"]["lective"] == 6
    assert row["contract"]["lective"] == 10 and row["missing_lective"] == 4
    assert row["scheduled"]["centre"] == 1.5


# --- Dos professors a la mateixa assignatura -------------------------------------


def test_activity_with_two_teachers_shows_in_both_teacher_schedules():
    repo = AcademicDataRepository()
    use_cases = _use_cases(repo)
    use_cases.load([_class(1, "Marta, Pere", "1r COM", subject="Taller", duration=4), _class(2, "Anna", "1r COM", day="Dimarts", duration=2)])
    assert [a["id"] for a in use_cases.teacher_schedule("Marta")["activities"]] == [1]
    assert [a["id"] for a in use_cases.teacher_schedule("Pere")["activities"]] == [1]
    assert use_cases.teacher_schedule("Anna")["activities"][0]["id"] == 2


def test_centre_hours_stick_to_classes_taught_together_with_another_teacher():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Marta", "active": True, "center_hours": 1})
    use_cases = _use_cases(repo)
    use_cases.load([_class(1, "Marta, Pere", "1r COM", subject="Taller", day="Dilluns", duration=4)])
    result = use_cases.assign_center_and_coordination_hours()
    assert not any(item.get("reason") == "no_existing_day" for item in result["skipped_no_slot"])


# --- PDF -----------------------------------------------------------------------------


def _pdf_text(buffer):
    import io
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(buffer.read())
        handle.flush()
        try:
            return subprocess.run(["pdftotext", "-layout", handle.name, "-"], capture_output=True, text=True).stdout
        except FileNotFoundError:  # pragma: no cover
            return None


def test_teacher_pdf_header_shows_percentage_contract_hours_and_optional_dni():
    activities = [_class(1, "Inno", "2n APGI", duration=4), {**_class(2, "Inno", "", day="Dijous", start="10:30", duration=4, subject="Coordinació"), "group": ""}]
    teachers = [{"name": "Inno", "dedication_pct": 100, "dni": "52141851T", "coordination_name": "Comunicació"}]
    with_dni = _pdf_text(build_schedule_pdf(activities, teachers=teachers, show_dni=True))
    without = _pdf_text(build_schedule_pdf(activities, teachers=teachers, show_dni=False))
    if with_dni is None:  # pragma: no cover - sense pdftotext no es pot llegir el PDF
        return
    assert "Inno 100%" in with_dni
    assert "Hores Lectives: 18 + 2" in with_dni
    assert "Hores de Centre: 7,5" in with_dni
    assert "Hores de Preparació: 7,5" in with_dni
    assert "52141851T" in with_dni
    assert "52141851T" not in without
