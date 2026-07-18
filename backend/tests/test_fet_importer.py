from pathlib import Path

import pytest

from backend.services.fet_importer import load_school_calendar


def test_load_school_calendar_reads_days_and_hours_from_fet(tmp_path: Path) -> None:
    fet_path = tmp_path / "sample.fet"
    fet_path.write_text(
        """<?xml version='1.0' encoding='UTF-8'?>
<fet>
  <Days_List>
    <Number_of_Days>4</Number_of_Days>
    <Day><Name>Monday</Name></Day>
    <Day><Name>Tuesday</Name></Day>
    <Day><Name>Wednesday</Name></Day>
    <Day><Name>Thursday</Name></Day>
  </Days_List>
  <Hours_List>
    <Number_of_Hours>9</Number_of_Hours>
    <Hour><Name>08:00</Name></Hour>
  </Hours_List>
</fet>
""",
        encoding="utf-8",
    )

    calendar = load_school_calendar(fet_path)

    assert calendar.days == [0, 1, 2, 3]
    assert calendar.periods_per_day == 9


def test_load_school_calendar_rejects_missing_dimensions(tmp_path: Path) -> None:
    fet_path = tmp_path / "invalid.fet"
    fet_path.write_text(
        """<?xml version='1.0' encoding='UTF-8'?>
<fet>
  <Days_List><Number_of_Days>0</Number_of_Days></Days_List>
  <Hours_List><Number_of_Hours>0</Number_of_Hours></Hours_List>
</fet>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_school_calendar(fet_path)