from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schedule_proposal import ScheduleProposal
from .scheduled_activity import ScheduledActivity


@dataclass
class GenerationResult:
    """The output of a generation pass.

    This object is intentionally separate from ScheduleProposal and is used as a
    simple domain contract for future generator implementations.
    """

    generated_scheduled_activities: List[ScheduledActivity]
    warnings: List[str] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    elapsed_time_ms: float = 0.0
    proposal_score: Optional[float] = None
    valid: bool = False
    schedule_proposal: Optional[ScheduleProposal] = None
    proposals: List[ScheduleProposal] = field(default_factory=list)
