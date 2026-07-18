from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schedule_proposal import ScheduleProposal


@dataclass
class SearchResult:
    """Represents the outcome of a simple multi-proposal search pass."""

    best_proposal: Optional[ScheduleProposal] = None
    proposals: List[ScheduleProposal] = field(default_factory=list)
    explored_states: int = 0
    elapsed_time_ms: float = 0.0
    statistics: Dict[str, Any] = field(default_factory=dict)
