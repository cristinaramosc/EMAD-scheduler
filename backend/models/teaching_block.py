from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    from time_units import blocks_to_hours, hours_to_blocks
except ModuleNotFoundError:  # pragma: no cover
    from backend.time_units import blocks_to_hours, hours_to_blocks


@dataclass
class TeachingBlock:
    """Domini: bloc docent no programat.

    Un bloc només coneix durada i ordre; no coneix dia ni hora ni aula.
    """

    id: str
    duration: float
    order: int
    duration_blocks: Optional[int] = None
    preferred_room_id: Optional[str] = None
    preferred_teacher_id: Optional[str] = None
    fixed: bool = False
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_blocks is None:
            self.duration_blocks = hours_to_blocks(float(self.duration))
        else:
            self.duration = blocks_to_hours(int(self.duration_blocks))
