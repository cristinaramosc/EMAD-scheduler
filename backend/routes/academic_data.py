from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from backend.dependencies import get_academic_data_repo
except ModuleNotFoundError:  # pragma: no cover
    from dependencies import get_academic_data_repo


router = APIRouter(prefix="/academic-data", tags=["Academic Data"])


@router.get("/summary")
def academic_data_summary():
    return get_academic_data_repo().summary()


class TeacherDTO(BaseModel):
    name: str
    active: Optional[bool] = True
    unavailable_slots: Optional[List[str]] = []
    center_hours: Optional[float] = None
    coordination_name: Optional[str] = ""
    coordination_hours: Optional[float] = None


class TeacherUpdateDTO(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    unavailable_slots: Optional[List[str]] = None
    center_hours: Optional[float] = None
    coordination_name: Optional[str] = None
    coordination_hours: Optional[float] = None


class TeacherRestrictionDTO(BaseModel):
    teacher: str
    no_gaps: Optional[bool] = False
    max_hours_per_day: Optional[float] = None
    max_consecutive_hours: Optional[float] = None
    preferred_availability: Optional[List[str]] = []
    unavailable_slots: Optional[List[str]] = []
    weekly_meeting_active: Optional[bool] = True
    weekly_coordination_active: Optional[bool] = True


class TeacherRestrictionUpdateDTO(BaseModel):
    teacher: Optional[str] = None
    no_gaps: Optional[bool] = None
    max_hours_per_day: Optional[float] = None
    max_consecutive_hours: Optional[float] = None
    preferred_availability: Optional[List[str]] = None
    unavailable_slots: Optional[List[str]] = None
    weekly_meeting_active: Optional[bool] = None
    weekly_coordination_active: Optional[bool] = None


class GroupDTO(BaseModel):
    name: str
    course: Optional[str] = ""
    active: Optional[bool] = True
    unavailable_slots: Optional[List[str]] = []
    fixed_slots: Optional[List[str]] = []
    is_split: Optional[bool] = False


class GroupUpdateDTO(BaseModel):
    name: Optional[str] = None
    course: Optional[str] = None
    active: Optional[bool] = None
    unavailable_slots: Optional[List[str]] = None
    fixed_slots: Optional[List[str]] = None
    is_split: Optional[bool] = None


class GroupRestrictionDTO(BaseModel):
    group: str
    no_gaps: Optional[bool] = False
    max_hours_per_day: Optional[float] = None
    max_consecutive_hours: Optional[float] = None
    max_days: Optional[int] = None
    preferred_availability: Optional[List[str]] = []
    unavailable_slots: Optional[List[str]] = []
    daily_start_time: Optional[str] = ""
    daily_max_end_time: Optional[str] = ""
    daily_windows: Optional[Dict[str, Dict[str, str]]] = {}
    exception_slots: Optional[List[str]] = []
    break_days: Optional[List[str]] = []
    break_slots: Optional[List[str]] = []


class GroupRestrictionUpdateDTO(BaseModel):
    group: Optional[str] = None
    no_gaps: Optional[bool] = None
    max_hours_per_day: Optional[float] = None
    max_consecutive_hours: Optional[float] = None
    max_days: Optional[int] = None
    preferred_availability: Optional[List[str]] = None
    unavailable_slots: Optional[List[str]] = None
    daily_start_time: Optional[str] = None
    daily_max_end_time: Optional[str] = None
    daily_windows: Optional[Dict[str, Dict[str, str]]] = None
    exception_slots: Optional[List[str]] = None
    break_days: Optional[List[str]] = None
    break_slots: Optional[List[str]] = None


class SubjectDTO(BaseModel):
    name: str
    color: Optional[str] = ""
    allowed_session_lengths: Optional[List[float]] = []
    weekly_hours: Optional[float] = 0


class SubjectUpdateDTO(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    allowed_session_lengths: Optional[List[float]] = None
    weekly_hours: Optional[float] = None


class RoomDTO(BaseModel):
    name: str
    capacity: Optional[int] = Field(default=0, ge=0)
    unavailable_slots: Optional[List[str]] = []


class RoomUpdateDTO(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=0)
    unavailable_slots: Optional[List[str]] = None


class AssignmentDTO(BaseModel):
    teacher: str
    subject: str
    group: str
    weekly_hours: float
    preferred_room: Optional[str] = ""
    notes: Optional[str] = ""
    fixed_day: Optional[str] = ""
    fixed_start: Optional[str] = ""
    max_session_days: Optional[str] = ""
    consecutive_group: Optional[str] = ""


class AssignmentUpdateDTO(BaseModel):
    teacher: Optional[str] = None
    subject: Optional[str] = None
    group: Optional[str] = None
    weekly_hours: Optional[float] = None
    preferred_room: Optional[str] = None
    notes: Optional[str] = None
    fixed_day: Optional[str] = None
    fixed_start: Optional[str] = None
    max_session_days: Optional[str] = None
    consecutive_group: Optional[str] = None


@router.get("/teachers")
def list_teachers():
    repo = get_academic_data_repo()
    teachers = repo.list_teachers()
    restrictions = {r["teacher"]: r for r in repo.list_teacher_restrictions()}
    for teacher in teachers:
        teacher.update(restrictions.get(teacher["name"], {}))
    return teachers


@router.post("/teachers")
def create_teacher(payload: TeacherDTO):
    repo = get_academic_data_repo()
    try:
        record = payload.dict()
        active = record.pop("active", True)
        repo.create_teacher(record)
        if not active:
            repo.delete_teacher(record["name"])
        if payload.unavailable_slots:
            repo.upsert_teacher_restriction({"teacher": payload.name, "unavailable_slots": payload.unavailable_slots})
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.patch("/teachers/{name}")
def update_teacher(name: str, payload: TeacherUpdateDTO):
    repo = get_academic_data_repo()
    current = next((t for t in repo.list_teachers() if t["name"] == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="teacher_not_found")
    if payload.active is False:
        repo.delete_teacher(name)
        return {"ok": True}
    updated = {**current, **{k: v for k, v in payload.dict().items() if v is not None and k != "active"}}
    try:
        repo.update_teacher(name, updated)
        if payload.unavailable_slots is not None:
            repo.upsert_teacher_restriction({"teacher": updated["name"], "unavailable_slots": payload.unavailable_slots})
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/teachers/{name}")
def delete_teacher(name: str):
    repo = get_academic_data_repo()
    try:
        repo.delete_teacher(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/teachers/{name}/restrictions")
def get_teacher_restrictions(name: str):
    repo = get_academic_data_repo()
    restriction = next((item for item in repo.list_teacher_restrictions() if item.get("teacher") == name), None)

    if restriction is None:
        raise HTTPException(status_code=404, detail="teacher_restrictions_not_found")

    merged = dict(restriction)
    merged.setdefault("weekly_meeting_active", True)
    merged.setdefault("weekly_coordination_active", True)
    return merged


@router.patch("/teachers/{name}/restrictions")
def update_teacher_restrictions(name: str, payload: TeacherRestrictionUpdateDTO):
    repo = get_academic_data_repo()
    current = next((item for item in repo.list_teachers() if item.get("name") == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="teacher_not_found")

    existing_restriction = next((item for item in repo.list_teacher_restrictions() if item.get("teacher") == name), None)
    existing_weekly_meeting_active = (existing_restriction or {}).get("weekly_meeting_active", True)
    existing_weekly_coordination_active = (existing_restriction or {}).get("weekly_coordination_active", True)

    record = {
        "teacher": payload.teacher or name,
        "no_gaps": payload.no_gaps if payload.no_gaps is not None else False,
        "max_hours_per_day": payload.max_hours_per_day,
        "max_consecutive_hours": payload.max_consecutive_hours,
        "preferred_availability": payload.preferred_availability if payload.preferred_availability is not None else [],
        "unavailable_slots": payload.unavailable_slots if payload.unavailable_slots is not None else [],
        "weekly_meeting_active": payload.weekly_meeting_active if payload.weekly_meeting_active is not None else existing_weekly_meeting_active,
        "weekly_coordination_active": payload.weekly_coordination_active if payload.weekly_coordination_active is not None else existing_weekly_coordination_active,
    }
    repo.upsert_teacher_restriction(record)
    return {"ok": True}


@router.get("/groups")
def list_groups():
    repo = get_academic_data_repo()
    groups = repo.list_groups()
    restrictions = {r["group"]: r for r in repo.list_group_restrictions()}
    for group in groups:
        group.update(restrictions.get(group["name"], {}))
    return groups


@router.post("/groups")
def create_group(payload: GroupDTO):
    repo = get_academic_data_repo()
    try:
        record = payload.dict()
        active = record.pop("active", True)
        repo.create_group(record)
        if not active:
            repo.delete_group(record["name"])
        if payload.unavailable_slots or payload.fixed_slots:
            repo.upsert_group_restriction({
                "group": payload.name,
                "unavailable_slots": payload.unavailable_slots or [],
                "fixed_slots": payload.fixed_slots or [],
            })
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.patch("/groups/{name}")
def update_group(name: str, payload: GroupUpdateDTO):
    repo = get_academic_data_repo()
    current = next((g for g in repo.list_groups() if g["name"] == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="group_not_found")
    if payload.active is False:
        repo.delete_group(name)
        return {"ok": True}
    updated = {**current, **{k: v for k, v in payload.dict().items() if v is not None and k != "active"}}
    try:
        repo.update_group(name, updated)
        if payload.unavailable_slots is not None or payload.fixed_slots is not None:
            repo.upsert_group_restriction({
                "group": updated["name"],
                "unavailable_slots": updated.get("unavailable_slots", []),
                "fixed_slots": updated.get("fixed_slots", []),
            })
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/groups/{name}")
def delete_group(name: str):
    repo = get_academic_data_repo()
    try:
        repo.delete_group(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/groups/{name}/restrictions")
def get_group_restrictions(name: str):
    repo = get_academic_data_repo()
    restriction = next((item for item in repo.list_group_restrictions() if item.get("group") == name), None)

    if restriction is None:
        raise HTTPException(status_code=404, detail="group_restrictions_not_found")

    return dict(restriction)


@router.patch("/groups/{name}/restrictions")
def update_group_restrictions(name: str, payload: GroupRestrictionUpdateDTO):
    repo = get_academic_data_repo()
    current = next((item for item in repo.list_groups() if item.get("name") == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="group_not_found")

    existing_restriction = next(
        (item for item in repo.list_group_restrictions() if item.get("group") == name),
        {},
    )

    record = {
        "group": payload.group or name,
        "no_gaps": payload.no_gaps if payload.no_gaps is not None else False,
        "max_hours_per_day": payload.max_hours_per_day,
        "max_consecutive_hours": payload.max_consecutive_hours,
        "max_days": payload.max_days if payload.max_days is not None else existing_restriction.get("max_days"),
        "preferred_availability": payload.preferred_availability if payload.preferred_availability is not None else existing_restriction.get("preferred_availability", []),
        "unavailable_slots": payload.unavailable_slots if payload.unavailable_slots is not None else existing_restriction.get("unavailable_slots", []),
        "fixed_slots": existing_restriction.get("fixed_slots", []),
        "daily_start_time": payload.daily_start_time if payload.daily_start_time is not None else existing_restriction.get("daily_start_time", ""),
        "daily_max_end_time": payload.daily_max_end_time if payload.daily_max_end_time is not None else existing_restriction.get("daily_max_end_time", ""),
        "daily_windows": payload.daily_windows if payload.daily_windows is not None else existing_restriction.get("daily_windows", {}),
        "exception_slots": payload.exception_slots if payload.exception_slots is not None else existing_restriction.get("exception_slots", []),
        "break_days": payload.break_days if payload.break_days is not None else existing_restriction.get("break_days", []),
        "break_slots": payload.break_slots if payload.break_slots is not None else existing_restriction.get("break_slots", []),
    }
    repo.upsert_group_restriction(record)
    return {"ok": True}


@router.get("/subjects")
def list_subjects():
    return get_academic_data_repo().list_subjects()


@router.post("/subjects")
def create_subject(payload: SubjectDTO):
    repo = get_academic_data_repo()
    try:
        repo.create_subject(payload.dict())
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.patch("/subjects/{name}")
def update_subject(name: str, payload: SubjectUpdateDTO):
    repo = get_academic_data_repo()
    current = next((s for s in repo.list_subjects() if s["name"] == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="subject_not_found")
    updated = {**current, **{k: v for k, v in payload.dict().items() if v is not None}}
    try:
        repo.update_subject(name, updated)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/subjects/{name}")
def delete_subject(name: str):
    repo = get_academic_data_repo()
    try:
        repo.delete_subject(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/rooms")
def list_rooms():
    return get_academic_data_repo().list_rooms()


@router.post("/rooms")
def create_room(payload: RoomDTO):
    repo = get_academic_data_repo()
    try:
        repo.create_room(payload.dict())
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.patch("/rooms/{name}")
def update_room(name: str, payload: RoomUpdateDTO):
    repo = get_academic_data_repo()
    current = next((r for r in repo.list_rooms() if r["name"] == name), None)
    if current is None:
        raise HTTPException(status_code=404, detail="room_not_found")
    updated = {**current, **{k: v for k, v in payload.dict().items() if v is not None}}
    try:
        repo.update_room(name, updated)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/rooms/{name}")
def delete_room(name: str):
    repo = get_academic_data_repo()
    try:
        repo.delete_room(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/assignments")
def list_assignments():
    return get_academic_data_repo().active_canonical_assignments()


@router.post("/assignments")
def create_assignment(payload: AssignmentDTO):
    repo = get_academic_data_repo()
    subject = next((s for s in repo.list_subjects() if s["name"] == payload.subject), None)
    if subject is None:
        raise HTTPException(status_code=400, detail="subject_not_found")
    try:
        record = payload.dict()
        record["allowed_session_lengths"] = subject.get("allowed_session_lengths", [])
        assignment_id = repo.create_canonical_assignment(record)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "id": assignment_id}


@router.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: AssignmentUpdateDTO):
    repo = get_academic_data_repo()
    current = next((a for a in repo.active_canonical_assignments() if a["id"] == assignment_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    updated = {**current, **{k: v for k, v in payload.dict().items() if v is not None}}
    subject = next((s for s in repo.list_subjects() if s["name"] == updated["subject"]), None)
    if subject:
        updated["allowed_session_lengths"] = subject.get("allowed_session_lengths", [])
    try:
        repo.update_canonical_assignment(assignment_id, updated)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/assignments/{assignment_id}/duplicate")
def duplicate_assignment(assignment_id: str):
    repo = get_academic_data_repo()
    try:
        new_id = repo.duplicate_canonical_assignment(assignment_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    return {"ok": True, "id": new_id}


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: str):
    repo = get_academic_data_repo()
    repo.delete_canonical_assignment(assignment_id)
    return {"ok": True}


class MergeQuartersDTO(BaseModel):
    first_id: str
    second_id: str


@router.post("/assignments/merge-quarters")
def merge_quarter_assignments(payload: MergeQuartersDTO):
    """Compacta dues assignacions (p.ex. dues d'1 hora) en una de sola de 2
    hores que comparteix la mateixa franja tot l'any (1Q per a una, 2Q per
    a l'altra), com 'Foto 1Q + Anglès 2Q'."""
    repo = get_academic_data_repo()
    try:
        new_id = repo.merge_quarter_assignments(payload.first_id, payload.second_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "id": new_id}


@router.post("/assignments/{assignment_id}/split")
def split_merged_assignment(assignment_id: str):
    """Desfà una assignació compactada, recuperant les dues originals per separat."""
    repo = get_academic_data_repo()
    try:
        new_ids = repo.split_merged_assignment(assignment_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="assignment_not_found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "ids": new_ids}
