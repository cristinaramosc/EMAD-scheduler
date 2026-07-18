from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from time_units import hours_to_blocks
except ModuleNotFoundError:  # pragma: no cover
    from backend.time_units import hours_to_blocks


@dataclass
class TeachingRequirement:
    """Domini: Teaching Requirement (no-persistent domain model).

    Identificadors són referències a altres entitats (no portar noms).
    """

    id: Optional[str]
    group_id: str
    subject_id: str
    teacher_id: str

    weekly_hours: float
    min_days: int
    max_days: int
    min_block_duration: float
    max_consecutive_hours: float
    allow_half_hour_blocks: bool
    min_distribution_days: Optional[int] = None
    max_distribution_days: Optional[int] = None

    # opcionals
    preferred_distribution: Dict[str, int] = field(default_factory=dict)
    preferred_rooms: List[str] = field(default_factory=list)
    fixed_teacher: bool = False
    priority: int = 2

    def __post_init__(self):
        if self.min_distribution_days is None:
            self.min_distribution_days = self.min_days
        if self.max_distribution_days is None:
            self.max_distribution_days = self.max_days

        # Keep legacy fields aligned with the canonical distribution fields.
        self.min_days = self.min_distribution_days
        self.max_days = self.max_distribution_days
        self.validate()

    def validate(self) -> None:
        """Validacions de domini mínimes.

        Llença ValueError si algun camp no compleix les regles.
        """
        if not (isinstance(self.weekly_hours, (int, float)) and self.weekly_hours > 0):
            raise ValueError("weekly_hours must be a number > 0")

        if not (isinstance(self.min_distribution_days, int) and self.min_distribution_days >= 1):
            raise ValueError("min_distribution_days must be an integer >= 1")

        if not (isinstance(self.max_distribution_days, int) and self.max_distribution_days >= self.min_distribution_days):
            raise ValueError("max_distribution_days must be an integer >= min_distribution_days")

        if not (isinstance(self.min_block_duration, (int, float)) and self.min_block_duration > 0):
            raise ValueError("min_block_duration must be a number > 0")

        if not (isinstance(self.max_consecutive_hours, (int, float)) and self.max_consecutive_hours >= self.min_block_duration):
            raise ValueError("max_consecutive_hours must be >= min_block_duration")

        # Enforce 30-minute grid for all public hour-based fields.
        try:
            hours_to_blocks(float(self.weekly_hours))
            hours_to_blocks(float(self.min_block_duration))
            hours_to_blocks(float(self.max_consecutive_hours))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if self.priority not in {1, 2, 3}:
            raise ValueError("priority must be one of {1,2,3}")

    @property
    def weekly_blocks(self) -> int:
        return hours_to_blocks(float(self.weekly_hours))

    @property
    def min_block_duration_blocks(self) -> int:
        return hours_to_blocks(float(self.min_block_duration))

    @property
    def max_consecutive_blocks(self) -> int:
        return hours_to_blocks(float(self.max_consecutive_hours))
