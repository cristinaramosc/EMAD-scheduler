try:
    from backend.scheduler_engine.models.schedule import Schedule
    from backend.scheduler_engine.constraints.group_conflict import GroupConflictConstraint
    from backend.scheduler_engine.constraints.group_time_window import GroupTimeWindowConstraint
    from backend.scheduler_engine.constraints.teacher_conflict import TeacherConflictConstraint
    from backend.scheduler_engine.constraints.room_conflict import RoomConflictConstraint
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models.schedule import Schedule
    from scheduler_engine.constraints.group_conflict import GroupConflictConstraint
    from scheduler_engine.constraints.group_time_window import GroupTimeWindowConstraint
    from scheduler_engine.constraints.teacher_conflict import TeacherConflictConstraint
    from scheduler_engine.constraints.room_conflict import RoomConflictConstraint


class SchedulerEngine:
    def __init__(self):
        self.state = Schedule()
        self.constraints = [
            GroupConflictConstraint(),
            GroupTimeWindowConstraint(),
            TeacherConflictConstraint(),
            RoomConflictConstraint(),
        ]

    def load(self, schedule: Schedule):
        self.state = schedule

    def move_activity(self, activity_id: int, *, day: str, start: str):
        for activity in self.state.all():
            if activity.id == activity_id:
                activity.day = day
                activity.start = start
                return activity

        return None

    def validate(self, schedule=None):
        if schedule is None:
            schedule = self.state
        # Note: GroupConflictConstraint enforces the rule that a parent-group
        # cannot have more than one different subject in the same slot,
        # except when the two activities correspond to 1Q and 2Q (quarter suffixes).
        # This method aggregates validations from all registered constraints.
        conflicts = []
        for c in self.constraints:
            conflicts.extend(c.validate(schedule))

        return conflicts

    def get_conflicts(self):
        return self.validate()
