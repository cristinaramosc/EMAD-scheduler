from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .activity import Activity
from .conflict import Conflict
from .score_breakdown import ScoreBreakdown


@dataclass
class ScheduleProposal:
    """Represents a complete proposed schedule before it is accepted."""

    id: str
    activities: List[Activity] = field(default_factory=list)
    score: float = 0.0
    conflicts: List[Conflict] = field(default_factory=list)
    warnings: List[dict]= field(default_factory=list)
    score_breakdown: Optional[ScoreBreakdown] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
