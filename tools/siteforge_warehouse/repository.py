"""Abstract warehouse repository interfaces.

CURRENT SITE EVIDENCE vs CROSS-SITE KNOWLEDGE isolation is enforced here:
CurrentSiteEvidenceRepository requires archive_sha256 + machine on every query.
CorpusLearningRepository is the only path for cross-corpus pattern queries.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WarehouseNotConfigured(RuntimeError):
    """Raised when PostgreSQL is not configured / no engine is available."""

    def __init__(self, message: str = "POSTGRESQL_NOT_CONFIGURED") -> None:
        super().__init__(message)


def _require_site_keys(*, archive_sha256: str | None, machine: str | None) -> tuple[str, str]:
    if archive_sha256 is None or not str(archive_sha256).strip():
        raise ValueError("archive_sha256 is required for current-site evidence queries")
    if machine is None or not str(machine).strip():
        raise ValueError("machine is required for current-site evidence queries")
    return str(archive_sha256).strip().lower(), str(machine).strip()


class CurrentSiteEvidenceRepository(ABC):
    """Evidence for ONE archive + machine. Never cross-site.

    Every evidence query method REQUIRES archive_sha256 and machine.
    Missing either raises ValueError.
    """

    @abstractmethod
    def get_configio_rows(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_eipmodules(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_io_claims(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_source_files(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        ...


class CorpusLearningRepository(ABC):
    """Cross-corpus pattern / learning queries (NOT current-site evidence)."""

    @abstractmethod
    def count_dialects(self) -> dict[str, int]:
        ...

    @abstractmethod
    def list_unknown_clusters(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def list_rule_candidates(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def hardware_catalog_counts(self) -> dict[str, int]:
        ...
