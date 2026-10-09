from application.live_schedule_use_cases import LiveScheduleUseCases
from repositories.academic_data_repository import AcademicDataRepository
from repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
from scheduler_engine.engine import SchedulerEngine


class InMemoryWorkingTimetableRepository(WorkingTimetableRepository):
    def __init__(self) -> None:
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        return self._snapshot

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._snapshot = snapshot


def _build_use_cases() -> LiveScheduleUseCases:
    return LiveScheduleUseCases(
        engine=SchedulerEngine(),
        working_timetable_repo=InMemoryWorkingTimetableRepository(),
        academic_data_repo=AcademicDataRepository(),
    )


def test_toggle_group_break_persists_restriction_without_creating_break_activity():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Monday",
                "start": "8:00",
                "duration": 2,
            },
            {
                "id": 2,
                "teacher": "B",
                "subject": "Hist",
                "group": "1A",
                "room": "R2",
                "day": "Monday",
                "start": "10:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Monday")
    assert activated.get("ok") is True
    assert activated.get("active") is True

    activities = activated.get("activities") or []
    assert not any((item.get("subject") or "").strip().lower() == "descans" for item in activities)

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Monday" in (restriction.get("break_days") or [])

    deactivated = use_cases.toggle_group_break("1A", "Monday")
    assert deactivated.get("ok") is True
    assert deactivated.get("active") is False

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Monday" not in (restriction.get("break_days") or [])


def test_toggle_group_break_accepts_catalan_day_with_english_schedule_days():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Wednesday",
                "start": "8:00",
                "duration": 2,
            },
            {
                "id": 2,
                "teacher": "B",
                "subject": "Hist",
                "group": "1A",
                "room": "R2",
                "day": "Wednesday",
                "start": "10:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dimecres")
    assert activated.get("ok") is True
    assert activated.get("active") is True

    restrictions = use_cases._academic_data_repo.list_group_restrictions()
    restriction = next((item for item in restrictions if item.get("group") == "1A"), None)
    assert restriction is not None
    assert "Dimecres" in (restriction.get("break_days") or [])


def test_toggle_group_break_fails_cleanly_when_no_gap_window():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Dilluns",
                "start": "8:00",
                "duration": 2,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dilluns")
    assert activated.get("ok") is False
    assert activated.get("error") == "no_free_slot"
    assert activated.get("active") is False

    restriction = next(
        (item for item in use_cases._academic_data_repo.list_group_restrictions() if item.get("group") == "1A"),
        None,
    )
    assert restriction is None or "Dilluns" not in (restriction.get("break_days") or [])


def test_toggle_group_break_never_shares_slot_with_long_activity():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {
                "id": 1,
                "teacher": "A",
                "subject": "Mat",
                "group": "1A",
                "room": "R1",
                "day": "Dilluns",
                "start": "8:00",
                "duration": 4,
            },
            {
                "id": 2,
                "teacher": "B",
                "subject": "Hist",
                "group": "1A",
                "room": "R2",
                "day": "Dilluns",
                "start": "10:00",
                "duration": 4,
            },
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dilluns")

    assert activated.get("ok") is True
    break_start = next(
        slot.split(" ", 1)[1]
        for slot in use_cases._academic_data_repo.list_group_restrictions()[0]["break_slots"]
        if slot.startswith("Dilluns ")
    )
    hour_index = {f"{hour}:{minute:02d}": index for index, (hour, minute) in enumerate(
        ((hour, minute) for hour in range(8, 22) for minute in (0, 30))
    )}
    break_index = hour_index[break_start]
    for activity in activated["activities"]:
        if activity["group"] != "1A":
            continue
        start_index = hour_index[activity["start"]]
        assert not (start_index < break_index + 1 and start_index + activity["duration"] > break_index)


def test_toggle_group_break_shifts_two_consecutive_rounds_atomically():
    use_cases = _build_use_cases()
    use_cases.load(
        [
            {"id": 1, "teacher": "A", "subject": "A", "group": "1A", "room": "R1", "day": "Dilluns", "start": "8:00", "duration": 2},
            {"id": 2, "teacher": "B", "subject": "B", "group": "1A", "room": "R2", "day": "Dilluns", "start": "9:00", "duration": 2},
            {"id": 3, "teacher": "C", "subject": "C", "group": "1A", "room": "R3", "day": "Dilluns", "start": "10:00", "duration": 2},
            {"id": 4, "teacher": "D", "subject": "D", "group": "1A", "room": "R4", "day": "Dilluns", "start": "11:00", "duration": 2},
        ]
    )

    activated = use_cases.toggle_group_break("1A", "Dilluns")

    assert activated.get("ok") is True
    starts = {activity["id"]: activity["start"] for activity in activated["activities"]}
    assert starts == {1: "8:00", 2: "9:30", 3: "10:30", 4: "11:30"}


def _class(activity_id, start, duration, subject="Mat", group="1A", teacher=None, room=None):
    return {
        "id": activity_id,
        "teacher": teacher or f"T{activity_id}",
        "subject": subject,
        "group": group,
        "room": room or f"R{activity_id}",
        "day": "Monday",
        "start": start,
        "duration": duration,
    }


def _break_overlaps_a_class(use_cases, group="1A", day="Monday"):
    _, hour_index = use_cases._half_hour_grid()
    restriction = next(
        item for item in use_cases._academic_data_repo.list_group_restrictions() if item.get("group") == group
    )
    slot = next(slot for slot in restriction.get("break_slots") or [] if str(slot).startswith(day))
    break_idx = hour_index[str(slot).split(" ", 1)[1]]
    return any(
        item.group == group
        and item.day == day
        and hour_index[item.start] <= break_idx < hour_index[item.start] + item.duration
        for item in use_cases._engine.state.all()
    )


def _regenerated_schedule():
    # Horari nou: la franja del descans anterior (10:00) ara és dins d'una classe.
    return [_class(11, "8:00", 3), _class(12, "9:30", 3), _class(13, "11:00", 3)]


def test_auto_place_breaks_replaces_stale_break_and_displaces_classes():
    use_cases = _build_use_cases()
    use_cases.load([_class(1, "8:00", 2), _class(2, "10:00", 2)])
    assert use_cases.toggle_group_break("1A", "Monday").get("active") is True

    use_cases.load(_regenerated_schedule())
    result = use_cases.auto_place_breaks()

    assert result["ok"] is True
    assert {"group": "1A", "day": "Monday"} in result["added"]
    assert _break_overlaps_a_class(use_cases) is False


def test_toggle_group_break_on_stale_break_opens_a_real_gap_instead_of_deactivating():
    use_cases = _build_use_cases()
    use_cases.load([_class(1, "8:00", 2), _class(2, "10:00", 2)])
    use_cases.toggle_group_break("1A", "Monday")

    use_cases.load(_regenerated_schedule())
    result = use_cases.toggle_group_break("1A", "Monday")

    assert result.get("ok") is True
    assert result.get("active") is True
    assert _break_overlaps_a_class(use_cases) is False


def test_auto_place_breaks_keeps_a_valid_break_untouched():
    use_cases = _build_use_cases()
    use_cases.load([_class(1, "8:00", 2), _class(2, "10:00", 2)])
    use_cases.toggle_group_break("1A", "Monday")
    before = next(
        item for item in use_cases._academic_data_repo.list_group_restrictions() if item.get("group") == "1A"
    )["break_slots"]
    positions_before = sorted((item.id, item.start) for item in use_cases._engine.state.all())

    use_cases.auto_place_breaks()

    after = next(
        item for item in use_cases._academic_data_repo.list_group_restrictions() if item.get("group") == "1A"
    )["break_slots"]
    assert after == before
    assert sorted((item.id, item.start) for item in use_cases._engine.state.all()) == positions_before

