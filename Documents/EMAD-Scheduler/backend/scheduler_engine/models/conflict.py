from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conflict:
    type: str
    message: str
    severity: str = "error"
    teacher: str | None = None
    room: str | None = None
    day: str | None = None
    start: str | None = None
    activities: list[int] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
