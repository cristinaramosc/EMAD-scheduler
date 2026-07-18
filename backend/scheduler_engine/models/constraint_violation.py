from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ConstraintViolation:
    """A soft or hard constraint violation identified for a proposal."""

    constraint_name: str
    severity: str
    message: str
    affected_activity_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
