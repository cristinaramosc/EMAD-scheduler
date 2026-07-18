from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

try:
    from backend.scheduler_engine.models import Schedule
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import Schedule

from .contracts import (
    DataCategory,
    BackupProvider,
    DocumentProvider,
    DocumentRecord,
    ExportArtifact,
    ExportRequest,
    ExportProvider,
    ImportPayload,
    ImportProvider,
    MappedDataset,
    MappingBundle,
    MappingLayer,
    PersistenceProvider,
)


class InMemoryPersistenceProvider(PersistenceProvider):
    """Minimal persistence provider used as architecture scaffold."""

    def __init__(self) -> None:
        self._store: Dict[str, Schedule] = {}

    def save_schedule(self, schedule: Schedule) -> str:
        schedule_id = str(uuid4())
        self._store[schedule_id] = deepcopy(schedule)
        return schedule_id

    def load_schedule(self, schedule_id: str) -> Optional[Schedule]:
        schedule = self._store.get(schedule_id)
        return deepcopy(schedule) if schedule is not None else None

    def list_schedules(self) -> List[str]:
        return sorted(self._store.keys())

    def replace_all(self, schedules: Dict[str, Schedule]) -> None:
        self._store = deepcopy(schedules)

    def dump_all(self) -> Dict[str, Schedule]:
        return deepcopy(self._store)


class InMemoryDocumentProvider(DocumentProvider):
    """In-memory document holder that avoids committing to file formats."""

    def __init__(self) -> None:
        self._documents: Dict[str, DocumentRecord] = {}

    def save_document(self, document: DocumentRecord) -> str:
        document_id = document.id or str(uuid4())
        copy = deepcopy(document)
        copy.id = document_id
        self._documents[document_id] = copy
        return document_id

    def load_document(self, document_id: str) -> Optional[DocumentRecord]:
        document = self._documents.get(document_id)
        return deepcopy(document) if document is not None else None

    def list_documents(self) -> List[str]:
        return sorted(self._documents.keys())


class PlaceholderExportProvider(ExportProvider):
    """Export placeholder until concrete formats are defined."""

    def export_data(self, request: ExportRequest) -> ExportArtifact:
        dataset_count = sum(len(dataset.records) for dataset in request.datasets)
        payload = f"placeholder-export:{request.format_name}:{dataset_count}".encode("utf-8")
        return ExportArtifact(
            format_name="placeholder",
            payload=payload,
            metadata={
                "requested_format": request.format_name,
                "dataset_types": [dataset.entity_name for dataset in request.datasets],
                "record_count": dataset_count,
                **request.metadata,
            },
        )


class PlaceholderImportProvider(ImportProvider):
    """Import placeholder that returns normalized datasets without side effects."""

    def import_data(self, payload: ImportPayload) -> MappingBundle:
        return MappingBundle(
            source_format=payload.format_name,
            datasets=[],
            warnings=["placeholder_import_provider_returns_no_datasets"],
            metadata=dict(payload.metadata),
        )


class PassthroughMappingLayer(MappingLayer):
    """Minimal shared mapping scaffold for future import/export modules."""

    def normalize_import(self, payload: ImportPayload) -> MappingBundle:
        return MappingBundle(
            source_format=payload.format_name,
            datasets=[],
            metadata=dict(payload.metadata),
        )

    def prepare_export(
        self,
        datasets: List[MappedDataset],
        format_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExportRequest:
        return ExportRequest(
            format_name=format_name,
            datasets=list(datasets),
            metadata=dict(metadata or {}),
        )


class InMemoryBackupProvider(BackupProvider):
    """Snapshot-based backup provider working over a persistence provider."""

    def __init__(self, persistence: InMemoryPersistenceProvider) -> None:
        self._persistence = persistence
        self._snapshots: Dict[str, Dict[str, Schedule]] = {}

    def create_backup(self, label: Optional[str] = None) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_id = label or f"backup-{timestamp}-{uuid4().hex[:6]}"
        self._snapshots[backup_id] = self._persistence.dump_all()
        return backup_id

    def restore_backup(self, backup_id: str) -> bool:
        snapshot = self._snapshots.get(backup_id)
        if snapshot is None:
            return False
        self._persistence.replace_all(snapshot)
        return True

    def list_backups(self) -> List[str]:
        return sorted(self._snapshots.keys())


@dataclass
class CloudSyncStatus:
    sync_id: str
    state: str
    details: Dict[str, str] = field(default_factory=dict)


class CloudSyncService:
    """Cloud-sync contract scaffold with local status tracking only."""

    def __init__(self) -> None:
        self._sync_jobs: Dict[str, CloudSyncStatus] = {}

    def queue_sync(self, scope: str) -> str:
        sync_id = str(uuid4())
        self._sync_jobs[sync_id] = CloudSyncStatus(
            sync_id=sync_id,
            state="queued",
            details={"scope": scope},
        )
        return sync_id

    def mark_completed(self, sync_id: str) -> bool:
        status = self._sync_jobs.get(sync_id)
        if status is None:
            return False
        status.state = "completed"
        return True

    def get_status(self, sync_id: str) -> Optional[CloudSyncStatus]:
        status = self._sync_jobs.get(sync_id)
        return deepcopy(status) if status is not None else None
