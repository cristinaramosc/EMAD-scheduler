from pathlib import Path

from backend.services.fet_importer import load_generation_inputs


def test_load_generation_inputs_splits_fet_data_into_fixed_and_floating(tmp_path: Path) -> None:
    fet_path = tmp_path / "sample.fet"
    fet_path.write_text(
        """<?xml version='1.0' encoding='UTF-8'?>
<fet>
  <Days_List>
    <Number_of_Days>2</Number_of_Days>
    <Day><Name>Dilluns</Name></Day>
    <Day><Name>Dimarts</Name></Day>
  </Days_List>
  <Hours_List>
    <Number_of_Hours>2</Number_of_Hours>
    <Hour><Name>8:00</Name></Hour>
    <Hour><Name>8:30</Name></Hour>
  </Hours_List>
  <Teachers_List>
    <Teacher><Name>Ada</Name></Teacher>
  </Teachers_List>
  <Activities_List>
    <Activity>
      <Teacher>Ada</Teacher>
      <Subject>Disseny</Subject>
      <Students>1A</Students>
      <Duration>1</Duration>
      <Total_Duration>1</Total_Duration>
      <Id>10</Id>
      <Activity_Group_Id>0</Activity_Group_Id>
      <Active>true</Active>
    </Activity>
    <Activity>
      <Teacher>Ada</Teacher>
      <Subject>Projectes</Subject>
      <Students>1A</Students>
      <Duration>1</Duration>
      <Total_Duration>1</Total_Duration>
      <Id>11</Id>
      <Activity_Group_Id>0</Activity_Group_Id>
      <Active>true</Active>
    </Activity>
  </Activities_List>
  <Time_Constraints_List>
    <ConstraintActivityPreferredStartingTime>
      <Weight_Percentage>100</Weight_Percentage>
      <Activity_Id>10</Activity_Id>
      <Preferred_Day>Dilluns</Preferred_Day>
      <Preferred_Hour>8:00</Preferred_Hour>
      <Permanently_Locked>true</Permanently_Locked>
      <Active>true</Active>
      <Day>Dilluns</Day>
      <Hour>8:00</Hour>
    </ConstraintActivityPreferredStartingTime>
    <ConstraintTeacherNotAvailableTimes>
      <Weight_Percentage>100</Weight_Percentage>
      <Teacher>Ada</Teacher>
      <Number_of_Not_Available_Times>1</Number_of_Not_Available_Times>
      <Not_Available_Time>
        <Day>Dimarts</Day>
        <Hour>8:30</Hour>
      </Not_Available_Time>
      <Active>true</Active>
    </ConstraintTeacherNotAvailableTimes>
  </Time_Constraints_List>
</fet>
""",
        encoding="utf-8",
    )

    payload = load_generation_inputs(fet_path)

    assert payload["day_names"] == ["Dilluns", "Dimarts"]
    assert payload["hour_names"] == ["8:00", "8:30"]
    assert len(payload["fixed_activities"]) == 1
    assert len(payload["floating_blocks"]) == 1
    assert len(payload["blocked_activities"]) == 1