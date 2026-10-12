import json

from backend.models.teaching_block import TeachingBlock
from backend.repositories.school_calendar_repository import SchoolCalendarRepository
from backend.scheduler_engine.generator import SchedulerGenerator
from backend.scheduler_engine.models import GenerationContext, ScheduledActivity, SchoolCalendar, TimeSlot


def _hours(last: str):
    names = []
    minutes = 8 * 60
    while True:
        label = f"{minutes // 60}:{minutes % 60:02d}"
        names.append(label)
        if label == last:
            return names
        minutes += 30


def _calendar(tmp_path, hour_names):
    path = tmp_path / "calendar.json"
    path.write_text(
        json.dumps({"day_names": ["Dilluns", "Dimarts"], "hour_names": hour_names}), encoding="utf-8"
    )
    return SchoolCalendarRepository(path).load_school_calendar()


def test_the_21_30_label_is_the_end_of_day_marker_and_not_a_usable_slot(tmp_path):
    with_marker = _calendar(tmp_path, _hours("21:30"))
    without_marker = _calendar(tmp_path, _hours("21:00"))

    # 8:00 ... 21:00 = 27 franges; una classe hi pot acabar com a molt a les 21:30.
    assert with_marker.periods_per_day == 27
    assert without_marker.periods_per_day == 27


def _block(block_id, group, teacher, duration_blocks, fixed=False):
    return TeachingBlock(
        id=block_id,
        duration=duration_blocks / 2,
        order=1,
        duration_blocks=duration_blocks,
        fixed=fixed,
        preferred_teacher_id=teacher,
        metadata={"subject": block_id, "group": group, "group_id": group, "teacher": teacher},
    )


def _placed(block, period):
    return ScheduledActivity(
        teaching_block=block,
        day=0,
        start_timeslot=TimeSlot(day=0, period=period),
        duration=block.duration_blocks,
        teacher_id=block.preferred_teacher_id,
        group_id=block.metadata["group"],
    )


def _context(periods):
    return GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=periods),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={},
    )


def test_a_block_that_does_not_fit_is_placed_by_moving_a_flexible_one_aside():
    generator = SchedulerGenerator()
    middle = _placed(_block("mitja", "G1", "T1", 2), period=1)  # ocupa 1-3 d'un dia de 6 franges
    scheduled = [middle]
    stuck = _block("gran", "G1", "T2", 4)  # necessita 4 franges seguides

    assert generator._placement_strategy.place(stuck, _context(6), scheduled) is None

    placement = generator._try_window_ejection(stuck, _context(6), scheduled)

    assert placement is not None
    everything = scheduled + [placement]
    assert len(everything) == 2
    spans = sorted((item.start_timeslot.period, item.start_timeslot.period + item.duration) for item in everything)
    assert spans[0][1] <= spans[1][0], "cap solapament després de reorganitzar"


def test_fixed_activities_are_never_moved_to_make_room():
    generator = SchedulerGenerator()
    fixed = _placed(_block("fixa", "G1", "T1", 2, fixed=True), period=1)
    scheduled = [fixed]

    placement = generator._try_window_ejection(_block("gran", "G1", "T2", 4), _context(6), scheduled)

    assert placement is None
    assert scheduled == [fixed]


def _consecutive_use_cases():
    from backend.application.scheduler_use_cases import SchedulerUseCases
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.repositories.requirement_repository import RequirementRepository
    from backend.scheduler_engine.engine import SchedulerEngine

    return SchedulerUseCases(
        requirement_repo=RequirementRepository(),
        scheduler_engine=SchedulerEngine(),
        proposal_store={},
        school_calendar=SchoolCalendar(days=[0, 1], periods_per_day=27),
        academic_data_repo=AcademicDataRepository(),
    )


def test_consecutive_classes_never_end_after_the_end_of_the_day():
    from backend.scheduler_engine.models import ScheduleProposal
    from backend.scheduler_engine.models.activity import Activity

    use_cases = _consecutive_use_cases()
    hour_names = _hours("21:00")  # 8:00 ... 21:00: les classes acaben com a màxim a les 21:30

    def activity(activity_id, subject, teacher, start, duration):
        return Activity(
            id=activity_id, teacher=teacher, subject=subject, group="G1", room="",
            day="Dilluns", start=start, duration=duration, fixed=False,
        )

    def run(first_start, second_duration):
        # L'assignació amb `consecutive_group` (Dib) és la "primera"; la seva
        # parella (Mat) es mou just darrere.
        proposal = ScheduleProposal(
            id="p",
            activities=[
                activity(1, "Dib", "T2", first_start, 2),
                activity(2, "Mat", "T1", "8:00", second_duration),
            ],
            score=0.0,
            conflicts=[],
            warnings=[],
        )
        assignments = [
            {"subject": "Mat", "group": "G1", "teacher": "T1"},
            {"subject": "Dib", "group": "G1", "teacher": "T2", "consecutive_group": "Mat"},
        ]
        result = use_cases._apply_consecutive_group_preferences(proposal, assignments, hour_names)
        return {item.subject: (item.day, item.start) for item in result.activities}

    # Hi cap: Dib 18:00-19:00 i Mat (1 h) just darrere, a les 19:00.
    assert run("18:00", 2)["Mat"] == ("Dilluns", "19:00")
    # No hi cap: darrere de Dib (20:00-21:00) una classe de 2 h acabaria a les 23:00.
    assert run("20:00", 4)["Mat"] == ("Dilluns", "8:00")


def _context_with(periods, configuration=None):
    return GenerationContext(
        school_calendar=SchoolCalendar(days=[0], periods_per_day=periods),
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration=configuration or {},
    )


def _holes(activities):
    spans = sorted((item.start_timeslot.period, item.start_timeslot.period + item.duration) for item in activities)
    return sum(max(0, spans[i + 1][0] - spans[i][1]) for i in range(len(spans) - 1))


def test_a_group_hole_larger_than_one_slot_is_closed_by_shifting_classes():
    generator = SchedulerGenerator()
    early = _placed(_block("mati", "G1", "T1", 4), period=0)
    late = _placed(_block("tarda", "G1", "T2", 4), period=8)  # forat de 4 franges entre les dues
    assert _holes([early, late]) == 4

    repaired = generator._repair_group_gaps([early, late], _context_with(27))

    assert len(repaired) == 2
    assert _holes(repaired) <= 1


def test_group_gap_repair_never_moves_fixed_activities_and_can_be_disabled():
    generator = SchedulerGenerator()
    fixed_a = _placed(_block("fixa-a", "G1", "T1", 4, fixed=True), period=0)
    fixed_b = _placed(_block("fixa-b", "G1", "T2", 4, fixed=True), period=8)

    untouched = generator._repair_group_gaps([fixed_a, fixed_b], _context_with(27))
    assert {(item.teaching_block.id, item.start_timeslot.period) for item in untouched} == {("fixa-a", 0), ("fixa-b", 8)}

    early = _placed(_block("mati", "G1", "T1", 4), period=0)
    late = _placed(_block("tarda", "G1", "T2", 4), period=8)
    disabled = generator._repair_group_gaps([early, late], _context_with(27, {"repair_group_gaps": False}))
    assert _holes(disabled) == 4


def test_group_gap_repair_does_not_create_teacher_conflicts():
    generator = SchedulerGenerator()
    early = _placed(_block("mati", "G1", "T1", 4), period=0)
    late = _placed(_block("tarda", "G1", "T2", 4), period=8)
    # T2 està ocupat amb un altre grup just on voldríem portar "tarda" (franges 4-8)
    # i T1 també amb l'altre extrem: el forat no es pot tancar sense conflicte.
    busy_t2 = _placed(_block("ocupat-t2", "G2", "T2", 4), period=4)
    busy_t1 = _placed(_block("ocupat-t1", "G3", "T1", 4), period=4)
    activities = [early, late, busy_t2, busy_t1]

    repaired = generator._repair_group_gaps(activities, _context_with(27))

    for item in repaired:
        for other in repaired:
            if item is other or item.teacher_id != other.teacher_id:
                continue
            assert (
                item.start_timeslot.period + item.duration <= other.start_timeslot.period
                or other.start_timeslot.period + other.duration <= item.start_timeslot.period
            ), "un professor no pot fer dues classes alhora"


def test_a_lone_quarter_is_drawn_at_half_width_in_the_pdf_and_overlaps_are_untouched():
    from backend.services.schedule_pdf_exporter import _halve_lone_quarters

    lone_first = {"quarter": "1Q", "_ncols": 1, "_col": 0}
    lone_second = {"quarter": "2Q", "_ncols": 1, "_col": 0}
    annual = {"quarter": None, "_ncols": 1, "_col": 0}
    overlapped = {"quarter": "2Q", "_ncols": 2, "_col": 1}
    items = [lone_first, lone_second, annual, overlapped]

    _halve_lone_quarters(items)

    assert (lone_first["_ncols"], lone_first["_col"]) == (2, 0)   # 1Q a l'esquerra
    assert (lone_second["_ncols"], lone_second["_col"]) == (2, 1)  # 2Q a la dreta
    assert (annual["_ncols"], annual["_col"]) == (1, 0)           # una classe anual, a ample complet
    assert (overlapped["_ncols"], overlapped["_col"]) == (2, 1)   # ja compartia franja: no es toca
