try:
    from backend.scheduler_engine.engine import SchedulerEngine
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.engine import SchedulerEngine

engine = SchedulerEngine()