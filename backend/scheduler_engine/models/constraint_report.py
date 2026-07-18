from dataclasses import dataclass, field
from typing import List

from .constraint_violation import ConstraintViolation


@dataclass
class ConstraintReport:
    """Collection of evaluated constraint findings for a proposal."""

    hard_violations: List[ConstraintViolation] = field(default_factory=list)
    soft_violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)
