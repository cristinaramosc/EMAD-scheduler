"""Reunions de coordinació conjuntes: planificació, dades acadèmiques, Excel,
API, generació de l'horari i comptatge d'hores de coordinació."""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.application.live_schedule_use_cases import LiveScheduleUseCases
from backend.application.scheduler_use_cases import SchedulerUseCases
from backend.bootstrap import reset_dependencies
from backend.main import app
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.repositories.requirement_repository import RequirementRepository
from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
from backend.routes.academic_workbook_spreadsheet import build_workbook, import_workbook
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import SchoolCalendar
from backend.services.coordination_meetings import is_joint_coordination_subject, meeting_subject, plan_meetings

DAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
HOURS = [f"{8 + index // 2}:{'00' if index % 2 == 0 else '30'}" for index in range(28)]  # 8:00 .. 21:30
WEDNESDAY = DAYS.index("Dimecres")


def _meetings(series="Dimecres matí"):
    return [
        {"name": "Gràfic", "coordinator": "Sònia", "participants": ["Eli", "Cristina"], "series": series},
        {"name": "PFI", "coordinator": "Joan Carles", "participants": ["Eli", "Cristina"], "series": series},
        {"name": "COM", "coordinator": "Jordi", "participants": ["Eli", "Cristina"], "series": series},
    ]


def _block(teacher, day, first, last):
    return {teacher.casefold(): {(DAYS.index(day), period) for period in range(first, last)}}


def _merge(*maps):
    merged = {}
    for item in maps:
        for key, slots in item.items():
            merged.setdefault(key, set()).update(slots)
    return merged


# ---------------------------------------------------------------- planificador
def test_the_three_meetings_go_one_after_the_other_on_wednesday_morning():
    # La Sònia i el Jordi no poden a les 8:00 de dimecres: la primera hora és per a PFI.
    blocked = _merge(_block("Sònia", "Dimecres", 0, 1), _block("Jordi", "Dimecres", 0, 1))

    planned, unplanned = plan_meetings(_meetings(), blocked, DAYS, HOURS)

    assert unplanned == []
    by_start = sorted((item["start_index"], item["name"]) for item in planned)
    assert by_start == [(0, "PFI"), (2, "Gràfic"), (4, "COM")]
    assert {item["day"] for item in planned} == {"Dimecres"}
    assert all(item["consecutive_series"] and item["within_preferred_window"] for item in planned)
    for item in planned:
        assert {"Eli", "Cristina"} <= set(item["members"])


def test_a_meeting_is_never_planned_where_an_attendee_is_unavailable():
    blocked = _block("Eli", "Dimecres", 0, 6)  # Eli: dimecres de 8:00 a 11:00 no pot

    planned, _ = plan_meetings(_meetings(), blocked, DAYS, HOURS)

    assert planned
    for item in planned:
        if "Eli" in item["members"] and item["day_index"] == WEDNESDAY:
            assert item["start_index"] >= 6


def test_when_the_preferred_morning_is_not_possible_each_meeting_is_still_planned():
    blocked = _block("Eli", "Dimecres", 0, 12)  # Eli no pot tot el matí de dimecres

    planned, unplanned = plan_meetings(_meetings(), blocked, DAYS, HOURS)

    assert unplanned == []
    assert len(planned) == 3
    assert not any(item["within_preferred_window"] and item["day"] == "Dimecres" for item in planned)
    # i cap parella de reunions amb l'Eli no se solapa
    slots = [(item["day_index"], p) for item in planned for p in range(item["start_index"], item["start_index"] + item["blocks"])]
    assert len(slots) == len(set(slots))


def test_a_meeting_nobody_can_attend_is_reported_instead_of_dropped():
    blocked = _block("Eli", "Dilluns", 0, 27)
    for day in DAYS[1:]:
        blocked = _merge(blocked, _block("Eli", day, 0, 27))

    planned, unplanned = plan_meetings(_meetings(), blocked, DAYS, HOURS)

    assert planned == []
    assert {item["name"] for item in unplanned} == {"Gràfic", "PFI", "COM"}
    assert all(item["reason"] == "no_common_slot" for item in unplanned)


def test_meetings_without_a_series_are_planned_one_by_one_and_inactive_ones_are_ignored():
    meetings = _meetings(series="")
    meetings[2]["active"] = False

    planned, _ = plan_meetings(meetings, {}, DAYS, HOURS)

    assert {item["name"] for item in planned} == {"Gràfic", "PFI"}
    assert all(not item["consecutive_series"] for item in planned)


def test_hours_define_the_length_of_a_meeting():
    meetings = [{"name": "Llarga", "coordinator": "Ana", "participants": [], "hours": 1.5}]

    planned, _ = plan_meetings(meetings, {}, DAYS, HOURS)

    assert planned[0]["blocks"] == 3


def test_joint_coordination_subjects_are_recognised():
    assert is_joint_coordination_subject(meeting_subject("Gràfic"))
    assert not is_joint_coordination_subject("Coordinació ED")


# ------------------------------------------------------------------ repositori
def test_repository_creates_updates_and_deletes_meetings_and_follows_teacher_renames():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Sònia"})
    repo.create_teacher({"name": "Eli"})
    repo.create_coordination_meeting({"name": "Gràfic", "coordinator": "Sònia", "participants": "Eli"})

    with pytest.raises(KeyError):
        repo.create_coordination_meeting({"name": "gràfic", "coordinator": "Sònia"})
    assert repo.summary()["coordination_meetings"] == 1

    repo.update_teacher("Sònia", {"name": "Sònia R."})
    repo.update_teacher("Eli", {"name": "Elisa"})
    meeting = repo.list_coordination_meetings()[0]
    assert meeting["coordinator"] == "Sònia R."
    assert meeting["participants"] == ["Elisa"]

    repo.update_coordination_meeting("Gràfic", {**meeting, "coordinator": "Elisa", "hours": 2})
    assert repo.list_coordination_meetings()[0]["coordinator"] == "Elisa"
    assert repo.list_coordination_meetings()[0]["hours"] == 2.0

    repo.delete_coordination_meeting("Gràfic")
    assert repo.list_coordination_meetings() == []
    with pytest.raises(KeyError):
        repo.delete_coordination_meeting("Gràfic")


# ------------------------------------------------------------------------- API
def test_api_creates_edits_and_removes_meetings_and_rejects_unknown_teachers():
    reset_dependencies()
    client = TestClient(app)
    for name in ("Sònia", "Eli", "Cristina"):
        client.post("/academic-data/teachers", json={"name": name})

    created = client.post(
        "/academic-data/coordination-meetings",
        json={"name": "Gràfic", "coordinator": "Sònia", "participants": ["Eli", "Cristina"]},
    )
    assert created.status_code == 200
    assert client.post("/academic-data/coordination-meetings", json={"name": "X", "coordinator": "Ningú"}).status_code == 400

    changed = client.patch("/academic-data/coordination-meetings/gràfic", json={"coordinator": "Eli", "hours": 1.5})
    assert changed.status_code == 200
    meeting = client.get("/academic-data/coordination-meetings").json()[0]
    assert meeting["coordinator"] == "Eli" and meeting["hours"] == 1.5
    assert client.patch("/academic-data/coordination-meetings/no-existeix", json={"hours": 1}).status_code == 404

    assert client.delete("/academic-data/coordination-meetings/Gràfic").status_code == 200
    assert client.get("/academic-data/coordination-meetings").json() == []


# ----------------------------------------------------------------------- Excel
def _repo_with_meeting():
    repo = AcademicDataRepository()
    repo.create_coordination_meeting(
        {"name": "Gràfic", "coordinator": "Sònia", "participants": ["Eli", "Cristina"], "series": "Dimecres matí"}
    )
    return repo


def test_excel_has_a_coordinations_sheet_that_round_trips():
    data = build_workbook(_repo_with_meeting(), blank=False).getvalue()
    assert "Coordinacions" in load_workbook(io.BytesIO(data)).sheetnames

    other = AcademicDataRepository()
    result = import_workbook(other, data)

    assert result["coordination_meetings"] == 1
    assert other.list_coordination_meetings() == _repo_with_meeting().list_coordination_meetings()


def test_importing_an_old_excel_without_the_sheet_keeps_the_existing_meetings():
    old = build_workbook(AcademicDataRepository(), blank=False)
    workbook = load_workbook(io.BytesIO(old.getvalue()))
    del workbook["Coordinacions"]
    buffer = io.BytesIO()
    workbook.save(buffer)

    repo = _repo_with_meeting()
    import_workbook(repo, buffer.getvalue())

    assert len(repo.list_coordination_meetings()) == 1


def test_importing_an_empty_coordinations_sheet_removes_the_meetings():
    empty = build_workbook(AcademicDataRepository(), blank=False).getvalue()

    repo = _repo_with_meeting()
    import_workbook(repo, empty)

    assert repo.list_coordination_meetings() == []


# ------------------------------------------------------------------- generació
def _generation_use_cases(repo):
    return SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=list(range(5)), periods_per_day=len(HOURS)),
        time_labels={"day_names": DAYS, "hour_names": HOURS},
        academic_data_repo=repo,
    )


def _school_with_meeting(repo):
    for name in ("Sònia", "Eli", "Cristina"):
        repo.create_teacher({"name": name})
    repo.create_group({"name": "G1"})
    repo.create_canonical_assignment({"teacher": "Eli", "subject": "Mates", "group": "G1", "weekly_hours": 2})
    repo.create_canonical_assignment({"teacher": "Cristina", "subject": "Llengua", "group": "G1", "weekly_hours": 2})
    repo.create_canonical_assignment({"teacher": "Sònia", "subject": "Dibuix", "group": "G1", "weekly_hours": 2})
    repo.create_coordination_meeting(
        {"name": "Gràfic", "coordinator": "Sònia", "participants": ["Eli", "Cristina"]}
    )


def test_generation_reserves_the_meeting_before_the_classes_and_nothing_overlaps_it():
    repo = AcademicDataRepository()
    _school_with_meeting(repo)

    result = _generation_use_cases(repo).generate_proposals_from_academic_data()

    planned = result["coordination_meetings"]["planned"]
    assert [(item["name"], item["day"], item["start"]) for item in planned] == [("Gràfic", "Dimecres", "8:00")]
    activities = result["best_proposal"]["activities"]
    meeting = next(item for item in activities if is_joint_coordination_subject(item["subject"]))
    assert meeting["fixed"] is True and meeting["group"] == ""
    assert set(meeting["teacher"].split(", ")) == {"Sònia", "Eli", "Cristina"}
    assert result["best_proposal"]["conflicts"] == []
    assert len(activities) == 4  # 3 classes + la reunió


def test_the_generator_receives_the_meeting_as_a_fixed_activity_so_classes_cannot_take_its_hour(monkeypatch):
    from backend.application import scheduler_use_cases as use_cases_module

    # la classe que fa servir realment el use case (el mòdul es pot carregar amb dos noms)
    SchedulerGenerator = use_cases_module.SchedulerGenerator
    captured = {}
    original = SchedulerGenerator.generate

    def spy(self, requirements, context):
        captured["context"] = context
        return original(self, requirements, context)

    monkeypatch.setattr(SchedulerGenerator, "generate", spy)
    repo = AcademicDataRepository()
    _school_with_meeting(repo)

    _generation_use_cases(repo).generate_proposals_from_academic_data()

    context = captured["context"]
    reserved = [a for a in context.fixed_activities if is_joint_coordination_subject(a.metadata.get("subject"))]
    assert len(reserved) == 1
    assert (reserved[0].day, reserved[0].start_timeslot.period, reserved[0].duration) == (WEDNESDAY, 0, 2)
    assert reserved[0].teacher_id == "Sònia, Eli, Cristina"
    assert reserved[0] in context.existing_scheduled_activities  # ocupa els tres professors


def test_a_meeting_with_an_unknown_teacher_is_reported_not_silently_dropped():
    repo = AcademicDataRepository()
    _school_with_meeting(repo)
    repo.create_coordination_meeting({"name": "Fantasma", "coordinator": "Ningú", "participants": ["Eli"]})

    result = _generation_use_cases(repo).generate_proposals_from_academic_data()

    unplanned = result["coordination_meetings"]["unplanned"]
    assert unplanned == [{"name": "Fantasma", "reason": "professor_desconegut", "members": ["Ningú"]}]


def test_generation_without_meetings_reports_nothing_to_plan():
    repo = AcademicDataRepository()
    _school_with_meeting(repo)
    repo.delete_coordination_meeting("Gràfic")

    result = _generation_use_cases(repo).generate_proposals_from_academic_data()

    assert result["coordination_meetings"] == {"planned": [], "unplanned": []}


# --------------------------------------------------- hores de coordinació / PDF
class _MemoryRepo(WorkingTimetableRepository):
    def __init__(self) -> None:
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        return self._snapshot

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._snapshot = snapshot


def test_the_hours_of_a_joint_meeting_are_discounted_from_each_attendees_coordination_hours():
    repo = AcademicDataRepository()
    repo.create_teacher({"name": "Ana", "coordination_name": "Cap", "coordination_hours": 4.0})
    repo.create_teacher({"name": "Berta", "coordination_name": "Cap", "coordination_hours": 4.0})
    live = LiveScheduleUseCases(engine=SchedulerEngine(), working_timetable_repo=_MemoryRepo(), academic_data_repo=repo)
    live.load(
        [
            {"id": 1, "teacher": "Ana", "subject": "Mat", "group": "G1", "room": "R1", "day": "Dilluns", "start": "8:00", "duration": 2},
            {
                "id": 2, "teacher": "Ana, Berta", "subject": meeting_subject("Gràfic"), "group": "", "room": "",
                "day": "Dimecres", "start": "8:00", "duration": 2,
            },
        ]
    )

    live.assign_center_and_coordination_hours()

    shared = [item for item in live.state()["activities"] if item["subject"] == "Coordinació Cap"]
    assert len(shared) == 1
    # 4 h = 1 h de la reunió conjunta + 1 h del bloc fix de dimecres + 2 h de coordinació comuna
    # (sense la reunió conjunta serien 3 h = 6 franges)
    assert shared[0]["duration"] == 4
    assert live._joint_meeting_coverage() == {"ana": 1.0, "berta": 1.0}
