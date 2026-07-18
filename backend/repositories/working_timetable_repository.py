from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional


@dataclass
class WorkingTimetableSnapshot:
    active_schedule: List[Dict[str, Any]] = field(default_factory=list)
    current_proposal: Optional[Dict[str, Any]] = None
    generation_stats: Optional[Dict[str, Any]] = None
    unscheduled_activities: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkingTimetableRepository(ABC):
    @abstractmethod
    def load_snapshot(self) -> WorkingTimetableSnapshot:
        raise NotImplementedError

    @abstractmethod
    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        raise NotImplementedError


class JsonWorkingTimetableRepository(WorkingTimetableRepository):
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        if not self._file_path.exists():
            return WorkingTimetableSnapshot()

        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        return WorkingTimetableSnapshot(
            active_schedule=list(payload.get("active_schedule", [])),
            current_proposal=payload.get("current_proposal"),
            generation_stats=payload.get("generation_stats"),
            unscheduled_activities=list(payload.get("unscheduled_activities", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(snapshot)

        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self._file_path.parent) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)

        temp_path.replace(self._file_path)