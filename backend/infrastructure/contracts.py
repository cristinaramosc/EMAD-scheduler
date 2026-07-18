from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from backend.scheduler_engine.models import Schedule
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import Schedule


@dataclass
class DocumentRecord:
    id: str
    name: str
    payload: bytes
    content_type: str = "application/octet-stream"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportArtifact:
    format_name: str
    payload: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportPayload:
    format_name: str
    payload: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataCategory:
    PLATFORM_CONFIGURATION: str = "platform_configuration"
    ACADEMIC_YEAR_DATA: str = "academic_year_data"


@dataclass
class MappedDataset:
    category: str
    entity_name: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MappingBundle:
    source_format: str
    datasets: List[MappedDataset] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportRequest:
    format_name: str
    datasets: List[MappedDataset] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PersistenceProvider(ABC):
    @abstractmethod
    def save_schedule(self, schedule: Schedule) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_schedule(self, schedule_id: str) -> Optional[Schedule]:
        raise NotImplementedError

    @abstractmethod
    def list_schedules(self) -> List[str]:
        raise NotImplementedError


class DocumentProvider(ABC):
    @abstractmethod
    def save_document(self, document: DocumentRecord) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_document(self, document_id: str) -> Optional[DocumentRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self) -> List[str]:
        raise NotImplementedError


class ExportProvider(ABC):
    @abstractmethod
    def export_data(self, request: ExportRequest) -> ExportArtifact:
        raise NotImplementedError

    def export_schedule(self, schedule: Schedule, target: str = "default") -> ExportArtifact:
        dataset = MappedDataset(
            category=DataCategory.ACADEMIC_YEAR_DATA,
            entity_name="schedule",
            records=[
                {
                    "id": activity.id,
                    "teacher": activity.teacher,
                    "subject": activity.subject,
                    "group": activity.group,
                    "room": activity.room,
                    "day": activity.day,
                    "start": activity.start,
                    "duration": activity.duration,
                }
                for activity in schedule.all()
            ],
            metadata={"target": target},
        )
        return self.export_data(
            ExportRequest(
                format_name="schedule",
                datasets=[dataset],
                metadata={"target": target},
            )
        )


class ImportProvider(ABC):
    @abstractmethod
    def import_data(self, payload: ImportPayload) -> MappingBundle:
        raise NotImplementedError

    def export_schedule(self, schedule: Schedule, target: str = "default") -> ExportArtifact:
        raise NotImplementedError


    def import_schedule(self, payload: ImportPayload) -> Schedule:
        bundle = self.import_data(payload)
        schedule_dataset = next((dataset for dataset in bundle.datasets if dataset.entity_name == "schedule"), None)
        schedule = Schedule()
        if schedule_dataset is None:
            return schedule

        try:
            from backend.scheduler_engine.models import Activity
        except ModuleNotFoundError:  # pragma: no cover
            from backend.scheduler_engine.models import Activity

        for record in schedule_dataset.records:
            schedule.add(
                Activity(
                    id=record["id"],
                    teacher=record["teacher"],
                    subject=record["subject"],
                    group=record["group"],
                    room=record["room"],
                    day=record["day"],
                    start=record["start"],
                    duration=record["duration"],
                )
            )

        return schedule


class MappingLayer(ABC):
    @abstractmethod
    def normalize_import(self, payload: ImportPayload) -> MappingBundle:
        raise NotImplementedError

    @abstractmethod
    def prepare_export(self, datasets: List[MappedDataset], format_name: str, metadata: Optional[Dict[str, Any]] = None) -> ExportRequest:
        raise NotImplementedError


class BackupProvider(ABC):
    @abstractmethod
    def create_backup(self, label: Optional[str] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def restore_backup(self, backup_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_backups(self) -> List[str]:
        raise NotImplementedError
