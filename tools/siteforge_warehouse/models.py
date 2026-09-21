"""SQLAlchemy 2.x declarative models for Site Forge warehouse Stage-1 schemas.

Uses JSON (not JSONB) in models for dialect portability; Alembic migrations may
emit JSONB for PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMAS = (
    "siteforge_meta",
    "corpus",
    "evidence",
    "learning",
    "qualification",
    "app",
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------------------
# siteforge_meta
# ---------------------------------------------------------------------------


class SchemaInfo(Base):
    __tablename__ = "schema_info"
    __table_args__ = {"schema": "siteforge_meta"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractorVersion(Base):
    __tablename__ = "extractor_versions"
    __table_args__ = {"schema": "siteforge_meta"}

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = {"schema": "siteforge_meta"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    roots: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    plan_summary: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


class Archive(Base):
    __tablename__ = "archives"
    __table_args__ = {"schema": "corpus"}

    archive_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    archive_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    discovered_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    site: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    timestamp_token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    # COMPLETE | FAILED | PARTIAL
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tables_present: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("project", "site", name="uq_projects_project_site"),
        {"schema": "corpus"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False)
    site: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Controller(Base):
    __tablename__ = "controllers"
    __table_args__ = (
        UniqueConstraint(
            "archive_sha256", "machine", name="uq_controllers_archive_machine"
        ),
        {"schema": "corpus"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    role_hints: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = {"schema": "corpus"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)


# ---------------------------------------------------------------------------
# evidence — all rows carry birth-certificate columns
# ---------------------------------------------------------------------------


class ConfigioRow(Base):
    __tablename__ = "configio_rows"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    octal_word: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    bank: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    lohi: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    in_out: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    desc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interface: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    i_o_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    process: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    purpose_meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    dialect_form: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dialect_meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class EipModule(Base):
    __tablename__ = "eipmodules"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    adapter: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    slot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connection: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_bank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_bank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class EipAdapter(Base):
    __tablename__ = "eipadapters"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    target_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    rack: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class EipModuleType(Base):
    __tablename__ = "eipmodule_types"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    type_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class EipcfgAdapter(Base):
    __tablename__ = "eipcfg_adapters"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    targetip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    output_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class EipcfgModule(Base):
    __tablename__ = "eipcfg_modules"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    adapter: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    slot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    connection: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class IoClaim(Base):
    __tablename__ = "io_claims"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    io_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    fortna_word: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    fortna_bit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    word: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    raw_fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class Conflict(Base):
    __tablename__ = "conflicts"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    conflict_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class MachineSourceScope(Base):
    __tablename__ = "machine_source_scopes"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_machine_inferred: Mapped[str] = mapped_column(
        String(256), nullable=False, default=""
    )
    notes: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)


class AdapterBridge(Base):
    __tablename__ = "adapter_bridges"
    __table_args__ = {"schema": "evidence"}

    fact_uid: Mapped[str] = mapped_column(String(48), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    eipmodules_adapter_name: Mapped[str] = mapped_column(
        String(256), nullable=False, default=""
    )
    eipadapters_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    target_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    eipcfg_adapter_name: Mapped[str] = mapped_column(
        String(256), nullable=False, default=""
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# learning — cross-site knowledge (never mixed into CurrentSiteEvidenceRepository)
# ---------------------------------------------------------------------------


class DialectObservation(Base):
    __tablename__ = "dialect_observations"
    __table_args__ = {"schema": "learning"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    form: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    structural_pattern_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    example_raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class UnknownCluster(Base):
    __tablename__ = "unknown_clusters"
    __table_args__ = {"schema": "learning"}

    cluster_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    pattern_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    structural_pattern: Mapped[str] = mapped_column(Text, nullable=False, default="")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    example_raw: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    archives: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    machines: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    fields: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class RuleCandidate(Base):
    __tablename__ = "rule_candidates"
    __table_args__ = {"schema": "learning"}

    rule_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    production_auto_promote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    related_forms: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    related_modules: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    evidence_tests: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    honesty_notes: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class RuleCoverage(Base):
    __tablename__ = "rule_coverage"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "archive_sha256", "machine", name="uq_rule_coverage_cell"
        ),
        {"schema": "learning"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    cell_status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class RuleCounterexample(Base):
    __tablename__ = "rule_counterexamples"
    __table_args__ = {"schema": "learning"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class InvestigationSession(Base):
    __tablename__ = "investigation_sessions"
    __table_args__ = {"schema": "learning"}

    investigation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class FieldTest(Base):
    __tablename__ = "field_tests"
    __table_args__ = {"schema": "learning"}

    field_test_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    git_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    project: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    archive_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    raw_physical_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_unresolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_emitted_specialized: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    claims_emitted_generic: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_muted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    racks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unplaced_modules: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transportation_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transportation_review: Mapped[str] = mapped_column(Text, nullable=False, default="")
    safety_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_review: Mapped[str] = mapped_column(Text, nullable=False, default="")
    build_status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artifact_paths: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class FailureEvent(Base):
    __tablename__ = "failure_events"
    __table_args__ = {"schema": "learning"}

    failure_uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    field_test_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    archive_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    machine: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    subsystem: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    pipeline_stage: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    resolver_rule: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    failure_code: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    signature_id: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    object_identity: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    physical_catalog_family: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    raw_fact_uids: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    source_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StructuralSignature(Base):
    __tablename__ = "structural_signatures"
    __table_args__ = {"schema": "learning"}

    signature_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subsystem: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    structural_pattern: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pattern_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dims: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AiInvestigation(Base):
    __tablename__ = "ai_investigations"
    __table_args__ = {"schema": "learning"}

    investigation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    signature_id: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    cluster_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_fact_uids: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_rule: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_guards: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    contradictions: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    disposition: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class ShadowEvaluation(Base):
    __tablename__ = "shadow_evaluations"
    __table_args__ = {"schema": "learning"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    investigation_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    controllers_applicable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_applicable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reproduced_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    newly_resolved_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counterexamples: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    collisions: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    source_scope_violations: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    false_positive_risk: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class ProvenanceEdge(Base):
    __tablename__ = "provenance_edges"
    __table_args__ = {"schema": "learning"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    to_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    evidence_class: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# qualification
# ---------------------------------------------------------------------------


class QualificationRun(Base):
    __tablename__ = "qualification_runs"
    __table_args__ = {"schema": "qualification"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    meta: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


class QualificationResult(Base):
    __tablename__ = "qualification_results"
    __table_args__ = {"schema": "qualification"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    check_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# app — reserved for future GUI / session state (empty foundation table)
# ---------------------------------------------------------------------------


class AppSetting(Base):
    __tablename__ = "settings"
    __table_args__ = {"schema": "app"}

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
