"""Repositori del calendari escolar (dies i hores lectives), en substitució
del calendari llegit fins ara del fitxer .fet.

Segueix el mateix patró que `JsonWorkingTimetableRepository`: un JSON petit
a `backend/data/`, editable a mà o des d'un futur formulari de configuració,
amb un valor per defecte raonable si encara no existeix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

try:
    from backend.scheduler_engine.models import SchoolCalendar
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import SchoolCalendar

_DEFAULT_DAY_NAMES = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
# Graella de 30 minuts, 8:00-21:30 (franja màxima que cobreix tots els
# grups: matí 8:00-15:00 i tarda/vespre 15:00-21:30). Les franges
# concretes per grup es limiten amb group_time_window_constraints, no aquí.
_DEFAULT_HOUR_NAMES = [
    f"{h}:{m:02d}" for h in range(8, 22) for m in (0, 30) if not (h == 21 and m == 30)
]


@dataclass
class SchoolCalendarSettings:
    day_names: List[str] = field(default_factory=lambda: list(_DEFAULT_DAY_NAMES))
    hour_names: List[str] = field(default_factory=lambda: list(_DEFAULT_HOUR_NAMES))

    def to_dict(self) -> Dict[str, List[str]]:
        return {"day_names": self.day_names, "hour_names": self.hour_names}

    @classmethod
    def from_dict(cls, data: Dict[str, List[str]]) -> "SchoolCalendarSettings":
        return cls(
            day_names=list(data.get("day_names") or _DEFAULT_DAY_NAMES),
            hour_names=list(data.get("hour_names") or _DEFAULT_HOUR_NAMES),
        )


class SchoolCalendarRepository:
    """Llegeix/escriu la configuració de dies i hores lectives des d'un
    fitxer JSON, en lloc de llegir-la del .fet."""

    def __init__(self, storage_file: Path) -> None:
        self._storage_file = storage_file

    def load_settings(self) -> SchoolCalendarSettings:
        if not self._storage_file.exists():
            settings = SchoolCalendarSettings()
            self.save_settings(settings)
            return settings

        try:
            data = json.loads(self._storage_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return SchoolCalendarSettings()

        return SchoolCalendarSettings.from_dict(data)

    def save_settings(self, settings: SchoolCalendarSettings) -> None:
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._storage_file.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # --- Helpers equivalents als que oferia fet_importer, per minimitzar
    #     el canvi a bootstrap.py i scheduler_use_cases.py -----------------

    def load_school_calendar(self) -> SchoolCalendar:
        settings = self.load_settings()
        return SchoolCalendar(
            days=list(range(len(settings.day_names))),
            periods_per_day=len(settings.hour_names),
        )

    def load_time_labels(self) -> Dict[str, List[str]]:
        settings = self.load_settings()
        return {"day_names": settings.day_names, "hour_names": settings.hour_names}
