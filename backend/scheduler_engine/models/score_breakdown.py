from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ScoreBreakdown:
    """Simple scoring breakdown for a schedule proposal."""

    total_score: float
    compactness_score: float = 0.0
    distribution_score: float = 0.0
    gap_penalty: float = 0.0
    warning_penalty: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
