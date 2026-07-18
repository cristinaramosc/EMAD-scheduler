from __future__ import annotations

from typing import Any, Dict, List

try:
    from backend.scheduler_engine.models import Activity, ScheduleProposal
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import Activity, ScheduleProposal


def serialize_activity(activity: Activity) -> Dict[str, Any]:
    return {
        "id": activity.id,
        "teacher": activity.teacher,
        "subject": activity.subject,
        "group": activity.group,
        "room": activity.room,
        "day": activity.day,
        "start": activity.start,
        "duration": activity.duration,
    }


def serialize_conflict(conflict: Any) -> Dict[str, Any]:
    return {
        "type": conflict.type,
        "message": conflict.message,
        "teacher": getattr(conflict, "teacher", None),
        "day": getattr(conflict, "day", None),
        "start": getattr(conflict, "start", None),
        "activities": getattr(conflict, "activities", []),
    }


def serialize_proposal(proposal: ScheduleProposal | None) -> Dict[str, Any] | None:
    if proposal is None:
        return None

    return {
        "id": proposal.id,
        "activities": [serialize_activity(activity) for activity in proposal.activities],
        "score": proposal.score,
        "warnings": proposal.warnings,
        "conflicts": [serialize_conflict(conflict) for conflict in proposal.conflicts],
    }


def serialize_conflicts(conflicts: List[Any]) -> List[Dict[str, Any]]:
    return [serialize_conflict(conflict) for conflict in conflicts]
