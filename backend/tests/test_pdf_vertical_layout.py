"""Tests del PDF vertical d'horaris (aspecte d'horari de professorat EMAD)."""

from services.schedule_pdf_exporter import build_schedule_pdf, classify_activity


def _act(subject, day="Dilluns", start="9:00", duration=2, teacher="Inno", group="1r APGI", **extra):
    return {"subject": subject, "day": day, "start": start, "duration": duration, "teacher": teacher, "group": group, "room": "", **extra}


def test_classify_activity_maps_each_kind():
    assert classify_activity(_act("WEB")) == "subject"
    assert classify_activity(_act("Tutoria")) == "tutoria"
    assert classify_activity(_act("Hores de centre", group="")) == "centre"
    assert classify_activity(_act("Reunió", group="")) == "claustre"
    assert classify_activity(_act("Coordinació", day="Dimecres", start="15:00", group="")) == "coordination_fixed"
    assert classify_activity(_act("Coordinació", day="Dijous", start="10:30", group="")) == "coordination"
    assert classify_activity(_act("Descans", group="")) is None


def test_pfi_tutoria_stays_a_normal_subject():
    assert classify_activity(_act("PFI Tutoria", group="PFI")) == "subject"


def test_pdf_is_portrait_a4_with_one_page_per_group_and_teacher():
    data = build_schedule_pdf(
        [_act("WEB"), _act("Tutoria", day="Dimarts", start="11:00", tutor_name="Inno")],
        teachers=[{"name": "Inno", "coordination_name": "Comunicació"}],
    ).read()
    assert data[:5] == b"%PDF-"
    assert b"/MediaBox [ 0 0 595.27" in data
    # 1 grup + 1 professor
    assert data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2


def test_pdf_handles_overlapping_and_out_of_range_activities():
    buffer = build_schedule_pdf(
        [
            _act("WEB", start="10:00", duration=4),
            _act("OF", start="10:30", duration=2, group="2n APGI"),
            _act("Hores de centre", start="22:00", duration=2, group=""),
            _act("Reunió", day="Dissabte", group=""),
        ]
    )
    assert buffer.read()[:5] == b"%PDF-"


def test_activity_quarter_is_read_from_subject_or_group():
    from services.schedule_pdf_exporter import activity_quarter

    assert activity_quarter(_act("Metodologia 1Q")) == "1Q"
    assert activity_quarter(_act("Anglès", group="1r COM 2Q")) == "2Q"
    assert activity_quarter(_act("WEB")) is None


def test_quarter_pair_sharing_a_slot_draws_1q_left_and_2q_right():
    from services.schedule_pdf_exporter import _layout_columns

    items = [
        {"_start": 540, "_end": 660, "_qorder": 1},  # 2Q, apareix primer a la llista
        {"_start": 540, "_end": 660, "_qorder": 0},  # 1Q
    ]
    _layout_columns(items)
    by_order = {it["_qorder"]: it for it in items}
    assert by_order[0]["_col"] == 0 and by_order[1]["_col"] == 1
    assert by_order[0]["_ncols"] == by_order[1]["_ncols"] == 2


def test_pdf_with_quarter_pairs_builds_without_crashing():
    buffer = build_schedule_pdf(
        [
            _act("Metodologia 1Q", group="1r COM", teacher="Marta"),
            _act("Anglès 2Q", group="1r COM", teacher="Pere"),
        ]
    )
    assert buffer.read()[:5] == b"%PDF-"
