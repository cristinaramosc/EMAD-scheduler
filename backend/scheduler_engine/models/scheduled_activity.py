from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    from backend.models.teaching_block import TeachingBlock
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
from .timeslot import TimeSlot


@dataclass
class ScheduledActivity:
    """A teaching block assigned to a concrete school slot."""

    teaching_block: TeachingBlock
    day: int
    start_timeslot: TimeSlot
    duration: int
    room_id: Optional[str] = None
    teacher_id: Optional[str] = None
    group_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
