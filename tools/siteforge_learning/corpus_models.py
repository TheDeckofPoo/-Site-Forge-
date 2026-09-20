"""Corpus / learning dataclasses for Site Forge overnight inventory.

No live API. Models are inventory-only — never mutate source archives.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ARCHIVE_RUN = "RUN"
ARCHIVE_COMM = "COMM_SUPPORTING_EVIDENCE"
ARCHIVE_UNKNOWN = "UNKNOWN_ARCHIVE"

FORM_CATALOG_INDEX = "CATALOG_INDEX"
FORM_CATALOG_WORD_BANK = "CATALOG_WORD_BANK"
FORM_BARE_CATALOG = "BARE_CATALOG"
FORM_SHORT_ALIAS = "SHORT_ALIAS"
FORM_NODE_SLOT = "NODE_SLOT"
FORM_PANEL_STATION = "PANEL_STATION"
FORM_PANEL_CATALOG_NUMERIC_ALPHA = "PANEL_CATALOG_NUMERIC_ALPHA"
FORM_UNKNOWN = "UNKNOWN"

STATUS_PRODUCTION_RULE = "PRODUCTION_RULE"
STATUS_CANDIDATE_RULE = "CANDIDATE_RULE"


def _sorted_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: d[k] for k in sorted(d.keys())}


@dataclass
class ArchiveManifest:
    """One discovered archive or extracted RUN root."""

    sha256: str
    filename: str
    archive_class: str  # RUN | COMM_SUPPORTING_EVIDENCE | UNKNOWN_ARCHIVE
    source_path: str
    project: str = ""
    site: str = ""
    controller: str = ""
    machine: str = ""
    timestamp: str = ""
    tables: list[str] = field(default_factory=list)
    eipcfg_present: bool = False
    eipmodules_present: bool = False
    eipadapters_present: bool = False
    eipmoduletype_present: bool = False
    configio_present: bool = False
    run_dir: str = ""
    member_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tables"] = sorted(d.get("tables") or [])
        d["notes"] = list(d.get("notes") or [])
        return _sorted_dict(d)


@dataclass
class DialectHit:
    """One Configio Desc dialect classification."""

    configio_form: str
    raw_example: str
    catalog: str = ""
    word: int | None = None
    bank: int | None = None
    node: str = ""
    suffix: str = ""
    panel: str = ""
    confidence: str = "MEDIUM"
    evidence: dict[str, Any] = field(default_factory=dict)
    archive_sha256: str = ""
    machine: str = ""
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = _sorted_dict(dict(d.get("evidence") or {}))
        return _sorted_dict(d)


@dataclass
class HardwareFamilyHit:
    catalog: str
    hardware_family: str
    network_device_class: str = ""
    source: str = ""  # EIPModuleType | EIPModules | eipcfg | Configio
    archive_sha256: str = ""
    machine: str = ""
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return _sorted_dict(asdict(self))


@dataclass
class BankCollision:
    """Same numeric bank used as InputBank on one module and OutputBank on another."""

    bank: int
    input_modules: list[dict[str, Any]] = field(default_factory=list)
    output_modules: list[dict[str, Any]] = field(default_factory=list)
    archive_sha256: str = ""
    machine: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["input_modules"] = sorted(
            d.get("input_modules") or [],
            key=lambda m: (
                str(m.get("adapter") or ""),
                int(m.get("slot") or 0),
                str(m.get("type") or ""),
            ),
        )
        d["output_modules"] = sorted(
            d.get("output_modules") or [],
            key=lambda m: (
                str(m.get("adapter") or ""),
                int(m.get("slot") or 0),
                str(m.get("type") or ""),
            ),
        )
        return _sorted_dict(d)


@dataclass
class InOutMaskStat:
    mask: str
    count: int
    archive_sha256: str = ""
    machine: str = ""
    interface: str = ""
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["examples"] = sorted(d.get("examples") or [])
        return _sorted_dict(d)


@dataclass
class UnknownCluster:
    """Site-independent structural cluster of UNKNOWN Configio forms / failures."""

    cluster_id: str
    pattern_hash: str
    signature_id: str = ""
    structural_pattern: str = ""
    example_raw: list[str] = field(default_factory=list)
    count: int = 0
    fields: dict[str, Any] = field(default_factory=dict)
    archives: list[str] = field(default_factory=list)
    machines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["example_raw"] = sorted(set(d.get("example_raw") or []))[:20]
        d["archives"] = sorted(set(d.get("archives") or []))
        d["machines"] = sorted(set(d.get("machines") or []))
        d["fields"] = _sorted_dict(dict(d.get("fields") or {}))
        return _sorted_dict(d)


@dataclass
class DecoderRuleRecord:
    rule_id: str
    title: str
    status: str  # PRODUCTION_RULE | CANDIDATE_RULE
    summary: str = ""
    evidence_tests: list[str] = field(default_factory=list)
    related_forms: list[str] = field(default_factory=list)
    related_modules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence_tests"] = sorted(d.get("evidence_tests") or [])
        d["related_forms"] = sorted(d.get("related_forms") or [])
        d["related_modules"] = sorted(d.get("related_modules") or [])
        return _sorted_dict(d)
