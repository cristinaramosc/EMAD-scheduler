from dataclasses import dataclass

@dataclass
class Activity:
    id: int
    teacher: str
    subject: str
    group: str
    room: str
    day: str
    start: str
    duration: int