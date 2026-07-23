import xml.etree.ElementTree as ET

try:
    from backend.models.teaching_block import TeachingBlock
    from backend.scheduler_engine.models import SchoolCalendar
    from backend.scheduler_engine.models import ScheduledActivity, TimeSlot
    from backend.time_units import blocks_to_hours
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
    from scheduler_engine.models import SchoolCalendar
    from scheduler_engine.models import ScheduledActivity, TimeSlot
    from time_units import blocks_to_hours


def text(element, tag):
    node = element.find(tag)
    return node.text if node is not None else None


def _parse_fet_root(filename):
    tree = ET.parse(filename)
    return tree.getroot()


def _is_active(element) -> bool:
    active_value = text(element, "Active")
    if active_value is None:
        return True
    return active_value.strip().lower() != "false"


def _read_day_names(root) -> list[str]:
    return [text(day, "Name") for day in root.findall("./Days_List/Day") if text(day, "Name")]


def _read_hour_names(root) -> list[str]:
    return [text(hour, "Name") for hour in root.findall("./Hours_List/Hour") if text(hour, "Name")]


def load_school_calendar(filename):
    root = _parse_fet_root(filename)
    days_list = root.find("Days_List")
    hours_list = root.find("Hours_List")

    number_of_days = int(text(days_list, "Number_of_Days") or 0) if days_list is not None else 0
    number_of_hours = int(text(hours_list, "Number_of_Hours") or 0) if hours_list is not None else 0

    if number_of_days <= 0:
        raise ValueError("FET file does not define a valid Number_of_Days")
    if number_of_hours <= 0:
        raise ValueError("FET file does not define a valid Number_of_Hours")

    return SchoolCalendar(days=list(range(number_of_days)), periods_per_day=number_of_hours)


def load_time_labels(filename):
    root = _parse_fet_root(filename)
    return {
        "day_names": _read_day_names(root),
        "hour_names": _read_hour_names(root),
    }


def load_restrictions(filename):
    root = _parse_fet_root(filename)
    day_names = _read_day_names(root)
    hour_names = _read_hour_names(root)
    day_indexes = {name: index for index, name in enumerate(day_names)}
    hour_indexes = {name: index for index, name in enumerate(hour_names)}

    teacher_restrictions: dict[str, dict] = {}
    for constraint in root.iter("ConstraintTeacherNotAvailableTimes"):
        if not _is_active(constraint):
            continue
        teacher = (text(constraint, "Teacher") or "").strip()
        if not teacher:
            continue
        teacher_record = teacher_restrictions.setdefault(
            teacher, {"teacher": teacher, "unavailable_slots": []}
        )
        for slot in constraint.findall("Not_Available_Time"):
            day = text(slot, "Day")
            hour = text(slot, "Hour")
            if day not in day_indexes or hour not in hour_indexes:
                continue
            teacher_record["unavailable_slots"].append(f"{day} {hour}")

    group_restrictions: dict[str, dict] = {}
    for constraint in root.iter("ConstraintStudentsSetNotAvailableTimes"):
        if not _is_active(constraint):
            continue
        group = (text(constraint, "Students") or "").strip()
        if not group:
            continue
        group_record = group_restrictions.setdefault(
            group, {"group": group, "unavailable_slots": []}
        )
        for slot in constraint.findall("Not_Available_Time"):
            day = text(slot, "Day")
            hour = text(slot, "Hour")
            if day not in day_indexes or hour not in hour_indexes:
                continue
            group_record["unavailable_slots"].append(f"{day} {hour}")

    return {
        "teacher_restrictions": list(teacher_restrictions.values()),
        "group_restrictions": list(group_restrictions.values()),
    }


def load_activities(filename):
    root = _parse_fet_root(filename)

    # Horaris preferits
    timetable = {}
    for c in root.iter("ConstraintActivityPreferredStartingTime"):
        if not _is_active(c):
            continue
        activity_id = int(text(c, "Activity_Id"))
        timetable[activity_id] = {
            "day": text(c, "Day"),
            "start": text(c, "Hour"),
        }

    # Aules preferides
    rooms = {}
    for c in root.iter("ConstraintActivityPreferredRoom"):
        if not _is_active(c):
            continue
        activity_id = int(text(c, "Activity_Id"))
        rooms[activity_id] = text(c, "Room")

    # Activitats
    excluded_subjects = {"descans", "dinar", "pati", "esbarjo"}
    activities = []

    for activity in root.iter("Activity"):
        subject_text = text(activity, "Subject")
        if (subject_text or "").strip().lower() in excluded_subjects:
            continue

        # === MILLORA: Gestió millorada de professors ===
        teachers = activity.findall("Teacher")
        teacher_list = [t.text.strip() for t in teachers if t.text and t.text.strip()]
        teacher_names = ", ".join(teacher_list)

        fet_id = int(text(activity, "Id"))

        schedule = timetable.get(fet_id, {"day": None, "start": None})

        activities.append({
            "fet_id": fet_id,
            "teacher": teacher_names,           # mantingut per compatibilitat
            "teachers": teacher_list,           # ← Nova llista (més útil)
            "subject": subject_text,
            "group_name": text(activity, "Students"),
            "duration": int(text(activity, "Duration") or 1),
            "day": schedule["day"],
            "start": schedule["start"],
            "room": rooms.get(fet_id),
        })

    return activities