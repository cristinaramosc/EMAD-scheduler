from dataclasses import dataclass, field

@dataclass
class Schedule:
    lessons: list = field(default_factory=list)

    def add(self, lesson):
        self.lessons.append(lesson)

    def remove(self, lesson):
        self.lessons.remove(lesson)

    def all(self):
        return self.lessons