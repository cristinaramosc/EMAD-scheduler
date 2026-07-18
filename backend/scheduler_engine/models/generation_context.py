from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from .school_calendar import SchoolCalendar
from .scheduled_activity import ScheduledActivity


@dataclass(frozen=True)
class GenerationContext:
    """Inputs required for a generation pass.

    The context is intentionally domain-only and does not depend on FastAPI,
    repositories, or persistence concerns.
    """

    school_calendar: SchoolCalendar
    existing_scheduled_activities: Tuple[ScheduledActivity, ...] = field(default_factory=tuple)
    fixed_activities: Tuple[ScheduledActivity, ...] = field(default_factory=tuple)
    blocked_time_slots: Tuple[Tuple[int, int], ...] = field(default_factory=tuple)
    configuration: Dict[str, Any] = field(default_factory=dict)
    random_seed: int | None = None
