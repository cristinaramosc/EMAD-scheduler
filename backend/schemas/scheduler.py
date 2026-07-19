from pydantic import BaseModel
from typing import List, Dict, Any


class ActivityDTO(BaseModel):
    id: int
    teacher: str
    subject: str
    group: str
    room: str
    day: str
    start: str
    duration: int


class MoveDTO(BaseModel):
    activity_id: int
    day: str
    start: str


class SwapDTO(BaseModel):
    activity_id_a: int
    activity_id_b: int


class ManualActivityDTO(BaseModel):
    subject: str
    day: str
    start: str
    duration: int = 1
    teacher: str = ""
    group: str = ""
    room: str = ""


class ToggleGroupBreakDTO(BaseModel):
    group: str
    day: str


class SchedulerStateDTO(BaseModel):
    activities: List[ActivityDTO]


class ConflictDTO(BaseModel):
    type: str
    teacher_id: str | None = None
    room: str | None = None
    timeslot: str | None = None
    data: Dict[str, Any] = {}