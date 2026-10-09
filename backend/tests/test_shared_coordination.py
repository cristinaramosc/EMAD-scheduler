import pytest

from backend.application.live_schedule_use_cases import LiveScheduleUseCases
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
from backend.scheduler_engine.constraints.teacher_max_days import TeacherMaxDaysConstraint
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models.activity import Activity
from backend.scheduler_engine.models.schedule import Schedule
from backend.scheduler_engine.subject_utils import is_non_class_subject
from backend.services.schedule_pdf_exporter import classify_activity


class _MemoryRepo(WorkingTimetableRepository):
    def __init__(self) -> None:
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        return self._snapshot

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._snapshot = snapshot


def _class(activity_id, teacher, day, start="8:00", duration=2, group="G1", subject="Mat"):
    return {
        "id": activity_id, "teacher": teacher, "subject": subject, "group": group,
        "room": f"R{activity_id}", "day": day, "start": start, "duration": duration,
    }


def _build(teachers, activities, restrictions=()):
    repo = AcademicDataRepository()
    for teacher in teachers:
        repo.create_teacher({"name": teacher["name"], "coordination_name": teacher.get("coordination_name", ""),
                             "coordination_hours": teacher.get("coordination_hours")})
    for restriction in restrictions:
        repo.upsert_teacher_restriction(restriction)
    live = LiveScheduleUseCases(engine=SchedulerEngine(), working_timetable_repo=_MemoryRepo(), academic_data_repo=repo)
    live.load([dict(item) for item in activities])
    return live


def _coordinations(live, name="ED"):
    return [item for item in live.state()["activities"] if item["subject"] == f"Coordinació {name}"]


ED_TEACHERS = [
    {"name": "Ana", "coordination_name": "ED", "coordination_hours": 4.0},
    {"name": "Berta", "coordination_name": "ED", "coordination_hours": 4.0},
    {"name": "Carla", "coordination_name": "ED", "coordination_hours": 4.0},
]
CLASSES = [
    _class(1, "Ana", "Dilluns", "8:00"),
    _class(2, "Berta", "Dilluns", "8:00", group="G2"),
    _class(3, "Carla", "Dimarts", "8:00", group="G3"),
]


def test_a_coordination_shared_by_several_teachers_is_one_common_block():
    live = _build(ED_TEACHERS, CLASSES)

    result = live.assign_center_and_coordination_hours()

    blocks = _coordinations(live)
    assert len(blocks) == 1
    assert set(blocks[0]["teacher"].split(", ")) == {"Ana", "Berta", "Carla"}
    assert blocks[0]["duration"] == 6  # 4 h - 1 h del bloc fix de dimecres = 3 h per a tothom
    assert result["added_shared_coordinations"][0]["subject"] == "Coordinació ED"
    assert live.state()["conflicts"] == []


def test_the_shared_block_does_not_repeat_hours_already_covered_and_is_idempotent():
    live = _build(ED_TEACHERS, CLASSES)

    live.assign_center_and_coordination_hours()
    live.assign_center_and_coordination_hours()

    assert len(_coordinations(live)) == 1
    individual = [
        item for item in live.state()["activities"]
        if item["subject"] == "Coordinació" and item["day"] != "Dimecres"
    ]
    assert individual == []  # les 3 h ja estan cobertes per la reunió comuna


def test_the_common_slot_respects_every_members_unavailability():
    blocked = [f"Dilluns {hour}" for hour in ("8:00", "8:30", "9:00", "9:30", "10:00", "10:30", "11:00", "11:30")]
    live = _build(ED_TEACHERS, CLASSES, restrictions=[{"teacher": "Carla", "unavailable_slots": blocked}])

    live.assign_center_and_coordination_hours()

    block = _coordinations(live)[0]
    assert not (block["day"] == "Dilluns" and block["start"] in {"8:00", "9:00", "10:00", "11:00"})
    assert live.state()["conflicts"] == []


def test_a_coordination_with_a_single_teacher_stays_individual():
    live = _build(
        [{"name": "Ana", "coordination_name": "ED", "coordination_hours": 4.0}], CLASSES[:1]
    )

    result = live.assign_center_and_coordination_hours()

    assert result["added_shared_coordinations"] == []
    assert _coordinations(live) == []


def test_non_class_subjects_do_not_count_as_class_days_for_the_teacher_maximum():
    assert is_non_class_subject("Coordinació ED") and is_non_class_subject("Coordinació")
    assert is_non_class_subject("Hores de centre") and is_non_class_subject("Reunió")
    assert not is_non_class_subject("Tutoria") and not is_non_class_subject("Dibuix")

    def conflicts(activities):
        schedule = Schedule()
        schedule.configuration = {"teacher_max_days_constraints": {"ana": 2}, "day_names": ["Dilluns", "Dimarts", "Dimecres"]}
        for item in activities:
            schedule.add(Activity(**item, fixed=False))
        return TeacherMaxDaysConstraint().validate(schedule)

    two_class_days = [_class(1, "Ana", "Dilluns"), _class(2, "Ana", "Dimarts")]
    coordination_day = _class(3, "Ana", "Dimecres", subject="Coordinació ED", group="")

    assert conflicts(two_class_days + [coordination_day]) == []
    assert conflicts(two_class_days + [_class(3, "Ana", "Dimecres")]) != []


def test_a_named_coordination_is_classified_as_coordination_in_exports_and_hours():
    assert classify_activity({"subject": "Coordinació ED", "day": "Divendres", "start": "11:30"}) == "coordination"
    assert classify_activity({"subject": "Coordinació", "day": "Dimecres", "start": "15:00"}) == "coordination_fixed"
    assert classify_activity({"subject": "Coordinació", "day": "Dijous", "start": "9:00"}) == "coordination"
