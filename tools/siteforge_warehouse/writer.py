#!/usr/bin/env python3
"""Transactional PostgreSQL writer for ArchiveEvidenceBundle.

ONE archive = ONE transaction. On failure: ROLLBACK; archive never COMPLETE.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import EXTRACTOR_VERSION
from .config import POSTGRESQL_NOT_CONFIGURED, get_database_url
from .ids import normalize_archive_sha256
from .models import (
    AdapterBridge,
    Archive,
    ConfigioRow,
    Conflict,
    Controller,
    DialectObservation,
    EipAdapter,
    EipcfgAdapter,
    EipcfgModule,
    EipModule,
    EipModuleType,
    ExtractorVersion,
    IoClaim,
    MachineSourceScope,
    Project,
    RuleCandidate,
    SourceFile,
    SyncRun,
)
from .postgres_repository import make_engine
from .repository import WarehouseNotConfigured
from .staging import ArchiveEvidenceBundle, validate_bundle

STATUS_INGESTING = "INGESTING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _s(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _i(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _birth_kwargs(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_uid": _s(row.get("fact_uid")),
        "archive_sha256": normalize_archive_sha256(_s(row.get("archive_sha256"))),
        "project": _s(row.get("project")),
        "machine": _s(row.get("machine")),
        "source_path": _s(row.get("source_path")),
        "source_row_index": _i(row.get("source_row_index"), 0),
        "machine_scope": _s(row.get("machine_scope")),
        "evidence_class": _s(row.get("evidence_class")),
        "extractor_version": _s(row.get("extractor_version") or EXTRACTOR_VERSION),
    }


class PostgresWarehouseWriter:
    """Writes ArchiveEvidenceBundle rows transactionally to PostgreSQL."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else make_engine()
        if self._engine is None:
            raise WarehouseNotConfigured(POSTGRESQL_NOT_CONFIGURED)
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True
        )

    def known_complete_shas(self, extractor_version: str = EXTRACTOR_VERSION) -> set[str]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(Archive.archive_sha256).where(
                    Archive.complete.is_(True),
                    Archive.extractor_version == extractor_version,
                    Archive.sync_status == STATUS_COMPLETE,
                )
            ).all()
            return {str(r) for r in rows}

    def ensure_extractor_version(self, version: str = EXTRACTOR_VERSION) -> None:
        with self._session_factory() as session:
            with session.begin():
                existing = session.get(ExtractorVersion, version)
                if existing is None:
                    session.add(
                        ExtractorVersion(
                            version=version,
                            notes="warehouse Stage-1 hardware/I-O extractor",
                        )
                    )

    def seed_rule_candidate(self, payload: dict[str, Any]) -> None:
        """Upsert a learning.rule_candidates row (METHOD metadata, not site answers)."""
        with self._session_factory() as session:
            with session.begin():
                key = _s(payload.get("rule_key") or payload.get("rule_id"))
                existing = session.get(RuleCandidate, key)
                fields = {
                    "rule_id": key,
                    "title": _s(payload.get("title") or key),
                    "status": _s(payload.get("status") or "CANDIDATE_RULE"),
                    "summary": _s(payload.get("summary")),
                    "production_auto_promote": bool(
                        payload.get("production_auto_promote") or False
                    ),
                    "related_forms": payload.get("related_forms") or [],
                    "related_modules": payload.get("related_modules") or [],
                    "evidence_tests": payload.get("evidence_tests") or [],
                    "honesty_notes": payload.get("honesty_notes")
                    or payload.get("purity_notes")
                    or [],
                    "meta": {
                        "implementation_commit": _s(
                            payload.get("implementation_commit")
                        ),
                        "subsystem": _s(payload.get("subsystem") or "PHYSICAL_IO"),
                        "evidence_basis": payload.get("evidence_basis"),
                        "covered_controllers": payload.get("covered_controllers") or [],
                        "covered_hardware_families": payload.get(
                            "covered_hardware_families"
                        )
                        or [],
                        **(payload.get("meta") or {}),
                    },
                    "extractor_version": _s(
                        payload.get("extractor_version") or EXTRACTOR_VERSION
                    ),
                }
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    session.add(RuleCandidate(**fields))

    def delete_archive_evidence(self, session: Session, sha: str) -> None:
        """Remove all evidence rows for an archive (used on force reingest)."""
        sha = normalize_archive_sha256(sha)
        for model in (
            ConfigioRow,
            EipModule,
            EipAdapter,
            EipModuleType,
            EipcfgAdapter,
            EipcfgModule,
            IoClaim,
            Conflict,
            MachineSourceScope,
            AdapterBridge,
            SourceFile,
            Controller,
            DialectObservation,
        ):
            session.execute(delete(model).where(model.archive_sha256 == sha))  # type: ignore[attr-defined]

    def ingest_bundle(
        self,
        bundle: ArchiveEvidenceBundle,
        *,
        force: bool = False,
        fail_after: str | None = None,
    ) -> dict[str, Any]:
        """Ingest one archive transactionally.

        fail_after: test hook — raise after named stage to force ROLLBACK.
        """
        errs = validate_bundle(bundle)
        if errs:
            return {"status": STATUS_FAILED, "errors": errs, "archive_sha256": None}

        sha = normalize_archive_sha256(bundle.archive.archive_sha256)
        extractor = bundle.extractor_version or EXTRACTOR_VERSION

        # Idempotency check outside the write txn
        with self._session_factory() as session:
            existing = session.get(Archive, sha)
            if (
                existing
                and existing.complete
                and existing.extractor_version == extractor
                and existing.sync_status == STATUS_COMPLETE
                and not force
            ):
                return {
                    "status": "UNCHANGED",
                    "archive_sha256": sha,
                    "extractor_version": extractor,
                }

        try:
            with self._session_factory() as session:
                with session.begin():
                    if force and existing:
                        self.delete_archive_evidence(session, sha)

                    # Upsert archive as INGESTING
                    arch = session.get(Archive, sha)
                    if arch is None:
                        arch = Archive(archive_sha256=sha)
                        session.add(arch)
                    arch.filename = bundle.archive.filename or ""
                    arch.archive_class = bundle.archive.archive_class or ""
                    arch.discovered_path = bundle.archive.discovered_path or ""
                    arch.size_bytes = bundle.archive.size_bytes
                    arch.project = bundle.project or bundle.archive.project or ""
                    arch.site = bundle.archive.site or arch.project
                    arch.machine = bundle.machine or bundle.archive.machine or ""
                    arch.timestamp_token = bundle.archive.timestamp_token or ""
                    arch.extractor_version = extractor
                    arch.sync_status = STATUS_INGESTING
                    arch.complete = False
                    arch.tables_present = list(bundle.archive.tables_present or [])
                    arch.notes = list(bundle.archive.notes or [])
                    arch.ingested_at = None

                    if fail_after == "after_archive":
                        raise RuntimeError("injected_failure:after_archive")

                    # Project
                    proj_name = arch.project or ""
                    if proj_name:
                        proj = session.scalars(
                            select(Project).where(
                                Project.project == proj_name,
                                Project.site == (arch.site or ""),
                            )
                        ).first()
                        if proj is None:
                            session.add(
                                Project(
                                    project=proj_name,
                                    site=arch.site or "",
                                    notes="",
                                )
                            )

                    # Controller
                    if arch.machine:
                        ctrl = session.scalars(
                            select(Controller).where(
                                Controller.archive_sha256 == sha,
                                Controller.machine == arch.machine,
                            )
                        ).first()
                        if ctrl is None:
                            session.add(
                                Controller(
                                    archive_sha256=sha,
                                    project=arch.project,
                                    machine=arch.machine,
                                    role_hints={},
                                )
                            )

                    if fail_after == "after_controller":
                        raise RuntimeError("injected_failure:after_controller")

                    # Source files
                    for row in bundle.source_files:
                        session.merge(SourceFile(**_birth_kwargs(row), kind=_s(row.get("kind")), size_bytes=row.get("size_bytes"), notes=row.get("notes") or []))

                    # Configio
                    for row in bundle.configio_rows:
                        session.merge(
                            ConfigioRow(
                                **_birth_kwargs(row),
                                octal_word=_s(row.get("octal_word") or row.get("word")),
                                bank=_s(row.get("bank")),
                                lohi=_s(row.get("lohi")),
                                in_out=_s(row.get("in_out")),
                                desc=_s(row.get("desc")),
                                interface=_s(row.get("interface")),
                                i_o_type=_s(row.get("i_o_type")),
                                status=_s(row.get("status")),
                                process=_s(row.get("process")),
                                purpose=_s(row.get("purpose")),
                                purpose_meta=row.get("purpose_meta") or {},
                                dialect_form=_s(row.get("dialect_form")),
                                dialect_meta=row.get("dialect_meta") or {},
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    if fail_after == "after_configio":
                        raise RuntimeError("injected_failure:after_configio")

                    for row in bundle.eipmodules:
                        session.merge(
                            EipModule(
                                **_birth_kwargs(row),
                                name=_s(row.get("name")),
                                adapter=_s(row.get("adapter")),
                                type=_s(row.get("type")),
                                slot=_i(row.get("slot")),
                                connection=_s(row.get("connection")),
                                input_bank=_i(row.get("input_bank")),
                                output_bank=_i(row.get("output_bank")),
                                direction=_s(row.get("direction")),
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    for row in bundle.eipadapters:
                        session.merge(
                            EipAdapter(
                                **_birth_kwargs(row),
                                name=_s(row.get("name")),
                                target_ip=_s(row.get("target_ip") or row.get("targetip")),
                                rack=_s(row.get("rack")),
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    for row in bundle.eipmodule_types:
                        session.merge(
                            EipModuleType(
                                **_birth_kwargs(row),
                                type_name=_s(
                                    row.get("type_name")
                                    or row.get("Name")
                                    or row.get("name")
                                ),
                                raw_fields=row.get("raw_fields") or row,
                            )
                        )

                    for row in bundle.eipcfg_adapters:
                        session.merge(
                            EipcfgAdapter(
                                **_birth_kwargs(row),
                                name=_s(row.get("name")),
                                targetip=_s(row.get("targetip") or row.get("target_ip")),
                                input_address=_s(row.get("input_address")),
                                output_address=_s(row.get("output_address")),
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    for row in bundle.eipcfg_modules:
                        session.merge(
                            EipcfgModule(
                                **_birth_kwargs(row),
                                adapter=_s(row.get("adapter")),
                                slot=_i(row.get("slot")),
                                type=_s(row.get("type")),
                                name=_s(row.get("name")),
                                connection=_s(row.get("connection")),
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    for row in bundle.io_claims:
                        session.merge(
                            IoClaim(
                                **_birth_kwargs(row),
                                io_name=_s(row.get("io_name") or row.get("IO_Name")),
                                fortna_word=_s(
                                    row.get("fortna_word")
                                    or row.get("IO_Address_Word")
                                    or row.get("word")
                                ),
                                fortna_bit=_s(
                                    row.get("fortna_bit")
                                    or row.get("IO_Address_Bit")
                                    or row.get("bit")
                                ),
                                word=_i(row.get("word"), default=-1)
                                if row.get("word") not in (None, "")
                                else None,
                                device_type=_s(row.get("device_type")),
                                raw_fields=row.get("raw_fields") or {},
                            )
                        )

                    for row in bundle.scopes:
                        session.merge(
                            MachineSourceScope(
                                **_birth_kwargs(row),
                                kind=_s(row.get("kind")),
                                source_machine_inferred=_s(
                                    row.get("source_machine_inferred")
                                ),
                                notes=row.get("notes") or [],
                            )
                        )

                    for row in bundle.conflicts:
                        session.merge(
                            Conflict(
                                **_birth_kwargs(row),
                                conflict_kind=_s(
                                    row.get("conflict_kind") or row.get("kind")
                                ),
                                summary=_s(row.get("summary")),
                                details=row.get("details") or {},
                            )
                        )

                    for row in bundle.adapter_bridges:
                        session.merge(
                            AdapterBridge(
                                **_birth_kwargs(row),
                                eipmodules_adapter_name=_s(
                                    row.get("eipmodules_adapter_name")
                                ),
                                eipadapters_name=_s(row.get("eipadapters_name")),
                                target_ip=_s(row.get("target_ip")),
                                eipcfg_adapter_name=_s(row.get("eipcfg_adapter_name")),
                                status=_s(row.get("status")),
                                confidence=_s(row.get("confidence")),
                                details=row.get("details") or {},
                            )
                        )

                    # Dialect observations (aggregate from annotations)
                    dialect_counts: dict[str, int] = {}
                    for row in bundle.dialect_annotations or []:
                        form = _s(row.get("form") or row.get("dialect_form") or "UNKNOWN")
                        dialect_counts[form] = dialect_counts.get(form, 0) + 1
                    # Also from configio dialect_form field
                    for row in bundle.configio_rows:
                        form = _s(row.get("dialect_form") or "")
                        if form:
                            dialect_counts[form] = dialect_counts.get(form, 0) + 1
                    for form, cnt in dialect_counts.items():
                        existing_d = session.scalars(
                            select(DialectObservation).where(
                                DialectObservation.archive_sha256 == sha,
                                DialectObservation.machine == arch.machine,
                                DialectObservation.form == form,
                                DialectObservation.extractor_version == extractor,
                            )
                        ).first()
                        if existing_d:
                            existing_d.count = cnt
                        else:
                            session.add(
                                DialectObservation(
                                    form=form,
                                    structural_pattern_hash="",
                                    archive_sha256=sha,
                                    machine=arch.machine,
                                    count=cnt,
                                    example_raw="",
                                    evidence_class="INDEPENDENT_DERIVATION",
                                    extractor_version=extractor,
                                    meta={},
                                )
                            )

                    if fail_after == "before_complete":
                        raise RuntimeError("injected_failure:before_complete")

                    # Mark COMPLETE inside same transaction
                    arch.sync_status = STATUS_COMPLETE
                    arch.complete = True
                    arch.ingested_at = _utcnow()

            return {
                "status": "REEXTRACTED" if force else "INGESTED",
                "archive_sha256": sha,
                "extractor_version": extractor,
                "counts": bundle.staging_counts(),
            }
        except Exception as exc:
            # Ensure archive is not COMPLETE (txn rolled back). Record failure outside.
            try:
                with self._session_factory() as session:
                    with session.begin():
                        arch = session.get(Archive, sha)
                        if arch is None:
                            session.add(
                                Archive(
                                    archive_sha256=sha,
                                    filename=bundle.archive.filename or "",
                                    archive_class=bundle.archive.archive_class or "",
                                    discovered_path=bundle.archive.discovered_path or "",
                                    project=bundle.project or "",
                                    machine=bundle.machine or "",
                                    extractor_version=extractor,
                                    sync_status=STATUS_FAILED,
                                    complete=False,
                                    notes=[f"ingest_failed:{type(exc).__name__}"],
                                )
                            )
                        else:
                            # Only mark failed if not already a prior COMPLETE from older successful ingest
                            # After rollback of force/reingest failure, prior COMPLETE was rolled back too
                            # if it was in same txn — for force we deleted then failed, so mark FAILED
                            arch.sync_status = STATUS_FAILED
                            arch.complete = False
                            notes = list(arch.notes or [])
                            notes.append(f"ingest_failed:{type(exc).__name__}")
                            arch.notes = notes[-20:]
            except Exception:
                pass
            return {
                "status": STATUS_FAILED,
                "archive_sha256": sha,
                "error": str(exc),
            }


def live_sync(
    roots: list[Any] | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Plan + optionally ingest. dry_run never writes."""
    from .sync import build_bundle_for_discovered, discover_archives, plan_sync

    discovered = discover_archives(roots)
    writer: PostgresWarehouseWriter | None = None
    known: set[str] = set()
    if not dry_run:
        writer = PostgresWarehouseWriter()
        writer.ensure_extractor_version()
        known = writer.known_complete_shas()

    plan = plan_sync(
        discovered,
        known_complete_shas=known,
        force=force,
    )

    results: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    staging_counts: dict[str, int] = {}

    sync_run_id = None
    if writer and not dry_run:
        with writer._session_factory() as session:
            with session.begin():
                sr = SyncRun(
                    extractor_version=EXTRACTOR_VERSION,
                    status="RUNNING",
                    roots=[str(r) for r in (roots or [])],
                    plan_summary={},
                    dry_run=False,
                )
                session.add(sr)
                session.flush()
                sync_run_id = sr.id

    for item in plan:
        if item.status == "UNCHANGED" and not force:
            results.append({"archive_sha256": item.archive_sha256, "status": "UNCHANGED"})
            status_counts["UNCHANGED"] = status_counts.get("UNCHANGED", 0) + 1
            continue
        if item.status == "FAILED":
            results.append(
                {
                    "archive_sha256": item.archive_sha256,
                    "status": "FAILED",
                    "reason": item.reason,
                }
            )
            status_counts["FAILED"] = status_counts.get("FAILED", 0) + 1
            continue

        disc = next(
            (d for d in discovered if d.archive_sha256 == item.archive_sha256), None
        )
        if disc is None:
            continue
        try:
            bundle = build_bundle_for_discovered(disc)
        except Exception as exc:
            results.append(
                {
                    "archive_sha256": item.archive_sha256,
                    "status": "FAILED",
                    "error": str(exc),
                }
            )
            status_counts["FAILED"] = status_counts.get("FAILED", 0) + 1
            continue

        if dry_run or writer is None:
            results.append(
                {
                    "archive_sha256": item.archive_sha256,
                    "status": "NEW",
                    "counts": bundle.staging_counts(),
                }
            )
            status_counts["NEW"] = status_counts.get("NEW", 0) + 1
            for k, v in bundle.staging_counts().items():
                staging_counts[k] = staging_counts.get(k, 0) + v
            continue

        outcome = writer.ingest_bundle(bundle, force=force)
        st = outcome.get("status") or "FAILED"
        results.append(outcome)
        status_counts[st] = status_counts.get(st, 0) + 1
        for k, v in (outcome.get("counts") or {}).items():
            staging_counts[k] = staging_counts.get(k, 0) + int(v)

    if writer and not dry_run and sync_run_id is not None:
        with writer._session_factory() as session:
            with session.begin():
                sr = session.get(SyncRun, sync_run_id)
                if sr:
                    sr.finished_at = _utcnow()
                    sr.status = "COMPLETE"
                    sr.plan_summary = {"status_counts": status_counts}

    return {
        "dry_run": dry_run,
        "extractor_version": EXTRACTOR_VERSION,
        "status_counts": status_counts,
        "staging_counts": staging_counts,
        "results": results,
        "discovered_count": len(discovered),
        "sync_run_id": sync_run_id,
    }
