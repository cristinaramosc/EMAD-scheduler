from dataclasses import dataclass, field
from typing import List, Dict

from .timeslot import TimeSlot


@dataclass
class SchoolCalendar:
    """Representa el calendari escolar en termes de períodes (TimeSlots).

    - `days`: llistat d'índexs de dies lectius (0 = Monday, 1 = Tuesday, ...)
    - `periods_per_day`: nombre de períodes disponibles cada dia
    - `period_length_minutes`: durada d'un període en minuts (informatiu)
    - `breaks`: map de dia -> llista de períodes no lectius (període indices)
    - `holidays`: llista de dates (encara no utilitzades)
    """

    days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    periods_per_day: int = 12
    period_length_minutes: int = 30
    breaks: Dict[int, List[int]] = field(default_factory=dict)
    holidays: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.periods_per_day <= 0:
            raise ValueError("periods_per_day must be > 0")

        if self.period_length_minutes <= 0:
            raise ValueError("period_length_minutes must be > 0")

        for d in self.days:
            if d < 0 or d > 6:
                raise ValueError("day indices must be between 0 and 6")

    def periods_for_day(self, day: int) -> List[TimeSlot]:
        """Retorna la llista de `TimeSlot` disponibles per al `day`, excloent `breaks` i `holidays`."""
        if day not in self.days:
            return []

        slots = [TimeSlot(day=day, period=i) for i in range(self.periods_per_day)]
        blocked = set(self.breaks.get(day, []))
        return [s for s in slots if s.period not in blocked]

    def is_period_lective(self, slot: TimeSlot) -> bool:
        if slot.day not in self.days:
            return False
        if slot.period < 0 or slot.period >= self.periods_per_day:
            return False
        if slot.period in self.breaks.get(slot.day, []):
            return False
        return True
