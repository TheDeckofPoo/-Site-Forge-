"""Staging dataclasses for archive evidence bundles (offline, pre-DB)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

BIRTH_CERTIFICATE_FIELDS = (
    "archive_sha256",
    "project",
    "machine",
    "source_path",
    "source_row_index",
    "machine_scope",
    "evidence_class",
    "extractor_version",
)


@dataclass
class ArchiveMeta:
    archive_sha256: str
    filename: str = ""
    archive_class: str = ""
    discovered_path: str = ""
    size_bytes: int | None = None
    project: str = ""
    site: str = ""
    machine: str = ""
    timestamp_token: str = ""
    tables_present: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArchiveEvidenceBundle:
    """Staged evidence for one archive / RUN before warehouse insert."""

    archive: ArchiveMeta
    project: str = ""
    machine: str = ""
    source_files: list[dict[str, Any]] = field(default_factory=list)
    configio_rows: list[dict[str, Any]] = field(default_factory=list)
    eipmodules: list[dict[str, Any]] = field(default_factory=list)
    eipadapters: list[dict[str, Any]] = field(default_factory=list)
    eipmodule_types: list[dict[str, Any]] = field(default_factory=list)
    eipcfg_adapters: list[dict[str, Any]] = field(default_factory=list)
    eipcfg_modules: list[dict[str, Any]] = field(default_factory=list)
    io_claims: list[dict[str, Any]] = field(default_factory=list)
    purpose_annotations: list[dict[str, Any]] = field(default_factory=list)
    dialect_annotations: list[dict[str, Any]] = field(default_factory=list)
    scopes: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    adapter_bridges: list[dict[str, Any]] = field(default_factory=list)
    extractor_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["archive"] = self.archive.to_dict()
        return d

    def staging_counts(self) -> dict[str, int]:
        return {
            "source_files": len(self.source_files),
            "configio_rows": len(self.configio_rows),
            "eipmodules": len(self.eipmodules),
            "eipadapters": len(self.eipadapters),
            "eipmodule_types": len(self.eipmodule_types),
            "eipcfg_adapters": len(self.eipcfg_adapters),
            "eipcfg_modules": len(self.eipcfg_modules),
            "io_claims": len(self.io_claims),
            "purpose_annotations": len(self.purpose_annotations),
            "dialect_annotations": len(self.dialect_annotations),
            "scopes": len(self.scopes),
            "conflicts": len(self.conflicts),
            "adapter_bridges": len(self.adapter_bridges),
        }


def _missing_birth_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in BIRTH_CERTIFICATE_FIELDS:
        if key not in row:
            missing.append(key)
            continue
        val = row[key]
        if val is None:
            missing.append(key)
        elif isinstance(val, str) and key in {
            "archive_sha256",
            "evidence_class",
            "extractor_version",
        } and not val.strip():
            missing.append(key)
    return missing


def validate_bundle(bundle: ArchiveEvidenceBundle) -> list[str]:
    """Return list of validation errors (empty = OK). Checks birth certificates."""
    errors: list[str] = []
    if not bundle.archive.archive_sha256:
        errors.append("archive.archive_sha256 missing")
    if not bundle.extractor_version:
        errors.append("extractor_version missing on bundle")

    collections = [
        ("source_files", bundle.source_files),
        ("configio_rows", bundle.configio_rows),
        ("eipmodules", bundle.eipmodules),
        ("eipadapters", bundle.eipadapters),
        ("eipmodule_types", bundle.eipmodule_types),
        ("eipcfg_adapters", bundle.eipcfg_adapters),
        ("eipcfg_modules", bundle.eipcfg_modules),
        ("io_claims", bundle.io_claims),
        ("purpose_annotations", bundle.purpose_annotations),
        ("dialect_annotations", bundle.dialect_annotations),
        ("scopes", bundle.scopes),
        ("conflicts", bundle.conflicts),
        ("adapter_bridges", bundle.adapter_bridges),
    ]
    for name, rows in collections:
        for i, row in enumerate(rows):
            miss = _missing_birth_fields(row)
            if miss:
                errors.append(f"{name}[{i}] missing birth fields: {', '.join(miss)}")
    return errors
