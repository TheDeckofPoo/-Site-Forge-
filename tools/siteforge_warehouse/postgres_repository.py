"""SQLAlchemy + in-memory repository implementations.

In-memory backends are UNIT_BACKEND_ONLY — they do not qualify PostgreSQL.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import POSTGRESQL_NOT_CONFIGURED, get_database_url
from .ids import normalize_archive_sha256
from .models import (
    ConfigioRow,
    DialectObservation,
    EipModule,
    EipModuleType,
    IoClaim,
    RuleCandidate,
    SourceFile,
    UnknownCluster,
)
from .repository import (
    CorpusLearningRepository,
    CurrentSiteEvidenceRepository,
    WarehouseNotConfigured,
    _require_site_keys,
)

UNIT_BACKEND_ONLY = "UNIT_BACKEND_ONLY"


def make_engine(url: str | None = None) -> Optional[Engine]:
    """Create a SQLAlchemy engine from url or SITEFORGE_DATABASE_URL. None if unset."""
    resolved = (url or get_database_url() or "").strip()
    if not resolved:
        return None
    return create_engine(resolved, future=True)


def _row_to_dict(obj: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col in obj.__table__.columns:
        data[col.name] = getattr(obj, col.name)
    return data


class PostgresCurrentSiteEvidenceRepository(CurrentSiteEvidenceRepository):
    """PostgreSQL-backed current-site evidence. Raises WarehouseNotConfigured if no engine."""

    def __init__(self, engine: Engine | None = None, session_factory: Any = None) -> None:
        self._engine = engine if engine is not None else make_engine()
        if self._engine is None and session_factory is None:
            self._session_factory = None
        else:
            self._session_factory = session_factory or sessionmaker(
                bind=self._engine, expire_on_commit=False, future=True
            )

    def _session(self) -> Session:
        if self._session_factory is None:
            raise WarehouseNotConfigured(POSTGRESQL_NOT_CONFIGURED)
        return self._session_factory()

    def get_configio_rows(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        sha, mach = _require_site_keys(archive_sha256=archive_sha256, machine=machine)
        sha = normalize_archive_sha256(sha)
        with self._session() as session:
            rows = session.scalars(
                select(ConfigioRow).where(
                    ConfigioRow.archive_sha256 == sha,
                    ConfigioRow.machine == mach,
                )
            ).all()
            return [_row_to_dict(r) for r in rows]

    def get_eipmodules(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        sha, mach = _require_site_keys(archive_sha256=archive_sha256, machine=machine)
        sha = normalize_archive_sha256(sha)
        with self._session() as session:
            rows = session.scalars(
                select(EipModule).where(
                    EipModule.archive_sha256 == sha,
                    EipModule.machine == mach,
                )
            ).all()
            return [_row_to_dict(r) for r in rows]

    def get_io_claims(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        sha, mach = _require_site_keys(archive_sha256=archive_sha256, machine=machine)
        sha = normalize_archive_sha256(sha)
        with self._session() as session:
            rows = session.scalars(
                select(IoClaim).where(
                    IoClaim.archive_sha256 == sha,
                    IoClaim.machine == mach,
                )
            ).all()
            return [_row_to_dict(r) for r in rows]

    def get_source_files(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        sha, mach = _require_site_keys(archive_sha256=archive_sha256, machine=machine)
        sha = normalize_archive_sha256(sha)
        with self._session() as session:
            rows = session.scalars(
                select(SourceFile).where(
                    SourceFile.archive_sha256 == sha,
                    SourceFile.machine == mach,
                )
            ).all()
            return [_row_to_dict(r) for r in rows]


class PostgresCorpusLearningRepository(CorpusLearningRepository):
    """PostgreSQL-backed cross-corpus learning queries."""

    def __init__(self, engine: Engine | None = None, session_factory: Any = None) -> None:
        self._engine = engine if engine is not None else make_engine()
        if self._engine is None and session_factory is None:
            self._session_factory = None
        else:
            self._session_factory = session_factory or sessionmaker(
                bind=self._engine, expire_on_commit=False, future=True
            )

    def _session(self) -> Session:
        if self._session_factory is None:
            raise WarehouseNotConfigured(POSTGRESQL_NOT_CONFIGURED)
        return self._session_factory()

    def count_dialects(self) -> dict[str, int]:
        with self._session() as session:
            rows = session.execute(
                select(
                    DialectObservation.form,
                    func.coalesce(func.sum(DialectObservation.count), 0),
                ).group_by(DialectObservation.form)
            ).all()
            return {str(form): int(total) for form, total in rows}

    def list_unknown_clusters(self) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(select(UnknownCluster)).all()
            return [_row_to_dict(r) for r in rows]

    def list_rule_candidates(self) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(select(RuleCandidate)).all()
            return [_row_to_dict(r) for r in rows]

    def hardware_catalog_counts(self) -> dict[str, int]:
        with self._session() as session:
            rows = session.execute(
                select(EipModuleType.type_name, func.count())
                .group_by(EipModuleType.type_name)
            ).all()
            return {str(name): int(cnt) for name, cnt in rows if name}


# ---------------------------------------------------------------------------
# In-memory UNIT_BACKEND_ONLY implementations
# ---------------------------------------------------------------------------


class InMemoryCurrentSiteEvidenceRepository(CurrentSiteEvidenceRepository):
    """UNIT_BACKEND_ONLY — filters strictly by archive_sha256 + machine."""

    backend = UNIT_BACKEND_ONLY

    def __init__(self) -> None:
        self.configio_rows: list[dict[str, Any]] = []
        self.eipmodules: list[dict[str, Any]] = []
        self.io_claims: list[dict[str, Any]] = []
        self.source_files: list[dict[str, Any]] = []

    def _filter(
        self, rows: list[dict[str, Any]], *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        sha, mach = _require_site_keys(archive_sha256=archive_sha256, machine=machine)
        sha = normalize_archive_sha256(sha)
        return [
            dict(r)
            for r in rows
            if str(r.get("archive_sha256") or "").strip().lower() == sha
            and str(r.get("machine") or "").strip() == mach
        ]

    def get_configio_rows(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        return self._filter(
            self.configio_rows, archive_sha256=archive_sha256, machine=machine
        )

    def get_eipmodules(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        return self._filter(
            self.eipmodules, archive_sha256=archive_sha256, machine=machine
        )

    def get_io_claims(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        return self._filter(
            self.io_claims, archive_sha256=archive_sha256, machine=machine
        )

    def get_source_files(
        self, *, archive_sha256: str, machine: str
    ) -> list[dict[str, Any]]:
        return self._filter(
            self.source_files, archive_sha256=archive_sha256, machine=machine
        )


class InMemoryCorpusLearningRepository(CorpusLearningRepository):
    """UNIT_BACKEND_ONLY cross-corpus learning store."""

    backend = UNIT_BACKEND_ONLY

    def __init__(self) -> None:
        self.dialect_counts: dict[str, int] = {}
        self.unknown_clusters: list[dict[str, Any]] = []
        self.rule_candidates: list[dict[str, Any]] = []
        self.catalog_counts: dict[str, int] = {}

    def count_dialects(self) -> dict[str, int]:
        return dict(self.dialect_counts)

    def list_unknown_clusters(self) -> list[dict[str, Any]]:
        return [dict(c) for c in self.unknown_clusters]

    def list_rule_candidates(self) -> list[dict[str, Any]]:
        return [dict(c) for c in self.rule_candidates]

    def hardware_catalog_counts(self) -> dict[str, int]:
        return dict(self.catalog_counts)
