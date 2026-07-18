from dataclasses import dataclass

@dataclass(frozen=True)
class TimeSlot:
    day: int
    period: int

    def __str__(self):
        return f"Day {self.day}, Period {self.period}"