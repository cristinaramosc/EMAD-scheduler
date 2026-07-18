from dataclasses import dataclass, field
from typing import Dict, List, Optional
from copy import deepcopy

try:
    from backend.scheduler_engine.models import Activity, Schedule
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import Activity, Schedule


@dataclass
class SchedulerState:
    """
    Estat global mutable del sistema d'horaris.
    """

    activities: Dict[int, Activity] = field(default_factory=dict)

    def load(self, schedule: Schedule):
        self.activities = {a.id: a for a in schedule.all()}

    def add(self, activity: Activity):
        self.activities[activity.id] = activity

    def remove(self, activity_id: int):
        self.activities.pop(activity_id, None)

    def move(self, activity_id: int, *, day: str, start: str):
        if activity_id not in self.activities:
            return

        self.activities[activity_id].day = day
        self.activities[activity_id].start = start

    def simulate_move(
        self,
        activity_id: int,
        *,
        day: str,
        start: str
    ) -> Dict[int, Activity]:
        """
        Retorna un estat simulat sense modificar l'original.
        Ideal per drag & drop.
        """

        snapshot = deepcopy(self.activities)

        if activity_id in snapshot:
            snapshot[activity_id].day = day
            snapshot[activity_id].start = start

        return snapshot

    def all(self) -> List[Activity]:
        return list(self.activities.values())