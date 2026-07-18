from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import BackupProvider, DocumentProvider, ExportProvider, ImportProvider, MappingLayer, PersistenceProvider
from .providers import CloudSyncService


@dataclass
class InfrastructureServices:
    """Application-facing infrastructure registry.

    This service coordinates provider access and keeps the rest of the codebase
    independent from concrete IO mechanisms.
    """

    persistence: PersistenceProvider
    documents: DocumentProvider
    exporter: ExportProvider
    importer: ImportProvider
    backups: BackupProvider
    cloud_sync: CloudSyncService
    mapping: Optional[MappingLayer] = None
