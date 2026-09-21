#!/usr/bin/env python3
"""R&D Learning Loop V1 — field tests, failure events, signatures, eligibility.

Deterministic knowledge capture. AI investigator is a separate fallback.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "tools" / "scripts"
_TOOLS = _REPO / "tools"
for _p in (_SCRIPTS, _TOOLS, _REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_evidence_purity import INDEPENDENT_DERIVATION, RAW_RUN_EVIDENCE  # noqa: E402
from fortna_hardware_io_model import build_hardware_io_model  # noqa: E402
from fortna_learning_signatures import build_failure_signature  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_eipmodules_rows,
    parse_eipcfg,
)

from siteforge_warehouse import EXTRACTOR_VERSION  # noqa: E402
from siteforge_warehouse.ids import normalize_archive_sha256  # noqa: E402
from siteforge_warehouse.postgres_repository import make_engine  # noqa: E402

# Meaningful single-controller impact threshold for AI eligibility
_MEANINGFUL_UNRESOLVED = 50

_DESC_FAMILY_RE = re.compile(
    r"^(?P<fam>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)-(?P<idx>\d+)$"
)
_RTA_32PT_RE = re.compile(
    r"^(?P<tok>IB32|OB32P)(?P<role>DATA|STATUS)-(?P<idx>\d+)$", re.I
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(_REPO), text=True
            )
            .strip()
        )
    except Exception:
        return ""


def _uid(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return "fe_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _field_test_id(machine: str, archive_sha: str, git_sha: str) -> str:
    stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"ft_{machine}_{stamp}_{archive_sha[:8]}_{git_sha[:7] or 'nogit'}"


def desc_family(desc: str) -> str:
    d = (desc or "").strip()
    m = _DESC_FAMILY_RE.match(d)
    if m:
        return m.group("fam").upper()
    return re.sub(r"-\d+$", "", d).upper() or "UNKNOWN"


def structural_dims_for_unresolved(u: dict[str, Any], *, eip_bank_state: str = "") -> dict[str, str]:
    """Site-free structural dims for an unresolved Configio word."""
    low = str(u.get("low_desc") or "").strip()
    high = str(u.get("high_desc") or "").strip()
    reason = str(u.get("reason") or "unknown")
    fam = desc_family(low) or desc_family(high)
    rta32 = _RTA_32PT_RE.match(low) or _RTA_32PT_RE.match(high)
    if rta32:
        configio_form = "RTA_TOKEN_DATA_STATUS"
        catalog = f"1794-{rta32.group('tok').upper()}"
        bank_rel = "MIDSPAN_WITHIN_DIRECT_SIZE"
        hw_family = "1794"
    elif re.match(r"^\d{4}-", fam):
        configio_form = "CATALOG_INDEX"
        catalog = fam
        bank_rel = "EQUALS_BASE_OR_UNKNOWN"
        hw_family = fam.split("-")[0] if "-" in fam else "UNKNOWN"
    elif "POWERFLEX" in fam:
        configio_form = "ETHERNET_DRIVE_TOKEN"
        catalog = fam
        bank_rel = "DRIVE_UNMAPPED"
        hw_family = "ETHERNET_DRIVE"
    else:
        configio_form = "UNKNOWN"
        catalog = fam
        bank_rel = "UNKNOWN"
        hw_family = "UNKNOWN"

    return {
        "subsystem": "physical_io",
        "hardware_family": hw_family,
        "adapter_family": hw_family,
        "network_device_class": "RTA",
        "configio_form": configio_form,
        "catalog_signature": catalog,
        "catalog_authority_status": "EIPMODULES_TYPE" if catalog.startswith("1794-") else "UNKNOWN",
        "direction_evidence_class": str(u.get("direction") or "UNKNOWN"),
        "lohi_shape": "PAIR_SAME_FAMILY" if low and high else "SINGLE",
        "bank_relationship_class": bank_rel,
        "interface": "RTA",
        "hardware_topology_status": eip_bank_state or "UNKNOWN",
        "adapter_identity_status": "PROVEN_OR_UNKNOWN",
        "failure_stage": "PHYSICAL_WORD_RESOLVER",
        "failure_reason": reason,
    }


def eipmodules_bank_state(run_dir: Path, machine: str) -> str:
    rows = _load_eipmodules_rows(run_dir, machine)
    if not rows:
        return "NO_EIPMODULES"
    nz = sum(
        1
        for r in rows
        if int(r.get("input_bank") or 0) or int(r.get("output_bank") or 0)
    )
    if nz == 0:
        return "ALL_ZERO_RAW"
    if nz == len(rows):
        return "ALL_NONZERO_RAW"
    return "MIXED_RAW"


def capture_pipeline(run_dir: Path | str, machine: str, *, archive_sha: str = "") -> dict[str, Any]:
    """Fresh deterministic capture for one machine (no PG write)."""
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    bank_state = eipmodules_bank_state(run_dir, machine)
    ev = build_evidence_bundle(run_dir, machine, project=machine)
    raw = ev.get("raw_claims") or []
    disp = Counter(c.get("deterministic_disposition") for c in raw)
    ur = list((ev.get("deterministic_resolver") or {}).get("unresolved_words") or [])
    pwr = PhysicalWordResolver(run_dir, machine)
    words = (pwr.physical_map or {}).get("words") or {}
    hows = Counter((v.get("assign_how") or "") for v in words.values())
    hw = build_hardware_io_model(run_dir, machine)
    topo = parse_eipcfg(run_dir, machine)
    ads = topo.get("adapters") or []
    modules = sum(len(a.get("modules") or []) for a in ads)
    occupancy = []
    claimed_ch = 0
    for ad in hw.get("adapters") or []:
        for mod in ad.get("modules") or []:
            chs = mod.get("channels") or []
            claimed = sum(
                1
                for c in chs
                if (c.get("logical_endpoint") or {}).get("name")
                or str(c.get("owner_state") or "").upper() == "ASSIGNED"
            )
            claimed_ch += claimed
            occupancy.append(
                {
                    "rio": ad.get("rio_name"),
                    "slot": mod.get("slot"),
                    "catalog": mod.get("catalog") or mod.get("type"),
                    "capacity": mod.get("channel_capacity"),
                    "channels": len(chs),
                    "claimed": claimed,
                }
            )
    failures = []
    for u in ur:
        dims = structural_dims_for_unresolved(u, eip_bank_state=bank_state)
        sig = build_failure_signature(**dims)
        failures.append(
            {
                "unresolved": u,
                "dims": dims,
                "signature_id": sig.get("signature_id") or sig.get("id"),
                "signature": sig,
            }
        )
    return {
        "machine": machine,
        "archive_sha": archive_sha,
        "run_dir": str(run_dir),
        "eip_bank_state": bank_state,
        "raw_physical_candidates": len(raw),
        "claims_created": len(raw),
        "claims_resolved": int(disp.get("ASSIGNED") or 0),
        "claims_unresolved": int(disp.get("physical_resolution_failure") or 0),
        "dispositions": dict(disp),
        "resolved_words": len(words),
        "assign_how_counts": dict(hows),
        "racks": len(ads),
        "modules": modules,
        "unplaced_modules": 0,
        "occupancy": occupancy,
        "claimed_channels": claimed_ch,
        "claim_discovery_status": hw.get("claim_discovery_status"),
        "evidence_status": ev.get("evidence_status"),
        "discovery_status": ev.get("discovery_status"),
        "failures": failures,
        "failure_code_counts": dict(
            Counter(f["dims"]["failure_reason"] for f in failures)
        ),
        "signature_counts": dict(Counter(f["signature_id"] for f in failures)),
        "git_sha": _git_sha(),
        "captured_at": _utcnow().isoformat(),
    }


def ai_investigation_eligible(
    *,
    signature_id: str,
    machines_observed: list[str],
    unresolved_count: int,
    blocks_subsystem: bool = False,
    engineer_investigate: bool = False,
    deterministic_explains: bool = False,
    known_production_rule: bool = False,
    source_scope_ambiguous: bool = False,
) -> dict[str, Any]:
    """Deterministic AI eligibility gate."""
    machines = sorted({m for m in machines_observed if m})
    reasons_block = []
    if deterministic_explains:
        reasons_block.append("deterministic_evidence_explains")
    if known_production_rule:
        reasons_block.append("known_production_rule_applies")
    if source_scope_ambiguous:
        reasons_block.append("source_scope_ambiguous_more_evidence_available")
    if unresolved_count <= 1 and len(machines) < 2 and not blocks_subsystem:
        reasons_block.append("single_endpoint_no_pattern")
    if reasons_block:
        return {
            "eligible": False,
            "block_reasons": reasons_block,
            "allow_reasons": [],
            "signature_id": signature_id,
        }
    allow = []
    if len(machines) >= 2:
        allow.append("multi_controller_recurrence")
    if unresolved_count >= _MEANINGFUL_UNRESOLVED:
        allow.append("meaningful_single_controller_impact")
    if blocks_subsystem:
        allow.append("blocks_subsystem_or_build")
    if engineer_investigate:
        allow.append("engineer_marked_investigate")
    return {
        "eligible": bool(allow),
        "allow_reasons": allow,
        "block_reasons": [],
        "signature_id": signature_id,
        "machines_observed": machines,
        "unresolved_count": unresolved_count,
    }


def persist_field_test_and_failures(
    capture: dict[str, Any],
    *,
    archive_sha: str,
    build_status: str = "REVIEW_REQUIRED",
    notes: str = "",
    artifact_paths: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write field_test + structural_signatures + failure_events to PostgreSQL."""
    from siteforge_warehouse.models import (  # local import after migration
        FailureEvent,
        FieldTest,
        StructuralSignature,
        UnknownCluster,
    )
    from sqlalchemy.orm import sessionmaker

    eng = make_engine()
    if eng is None:
        return {"ok": False, "error": "POSTGRESQL_NOT_CONFIGURED"}
    sha = normalize_archive_sha256(archive_sha) if archive_sha else ""
    ft_id = _field_test_id(capture["machine"], sha or "nosha", capture.get("git_sha") or "")
    Session = sessionmaker(bind=eng, future=True, expire_on_commit=False)
    n_fail = 0
    n_sig = 0
    ft_meta = {
        "assign_how_counts": capture.get("assign_how_counts"),
        "eip_bank_state": capture.get("eip_bank_state"),
        "claim_discovery_status": capture.get("claim_discovery_status"),
        "evidence_class": RAW_RUN_EVIDENCE,
    }
    if isinstance(capture.get("meta"), dict):
        ft_meta.update(capture["meta"])
    if meta:
        ft_meta.update(meta)
    with Session() as session:
        with session.begin():
            session.add(
                FieldTest(
                    field_test_id=ft_id,
                    timestamp=_utcnow(),
                    git_sha=str(capture.get("git_sha") or ""),
                    project=str(capture.get("project") or "MSCATL"),
                    machine=str(capture.get("machine") or ""),
                    archive_sha=sha,
                    raw_physical_candidates=int(capture.get("raw_physical_candidates") or 0),
                    claims_created=int(capture.get("claims_created") or 0),
                    claims_resolved=int(capture.get("claims_resolved") or 0),
                    claims_unresolved=int(capture.get("claims_unresolved") or 0),
                    claims_emitted_specialized=0,
                    claims_emitted_generic=0,
                    claims_muted=0,
                    claims_lost=0,
                    racks=int(capture.get("racks") or 0),
                    modules=int(capture.get("modules") or 0),
                    unplaced_modules=int(capture.get("unplaced_modules") or 0),
                    transportation_objects=int(capture.get("transportation_objects") or 0),
                    transportation_review=str(capture.get("transportation_review") or ""),
                    safety_devices=int(capture.get("safety_devices") or 0),
                    safety_review=str(capture.get("safety_review") or ""),
                    build_status=build_status,
                    notes=notes,
                    artifact_paths=list(artifact_paths or []),
                    meta=ft_meta,
                    extractor_version=EXTRACTOR_VERSION,
                )
            )
            for f in capture.get("failures") or []:
                sid = str(f.get("signature_id") or "")
                if not sid:
                    continue
                sig_row = session.get(StructuralSignature, sid)
                now = _utcnow()
                if sig_row is None:
                    session.add(
                        StructuralSignature(
                            signature_id=sid,
                            subsystem="physical_io",
                            structural_pattern=json.dumps(f.get("dims") or {}, sort_keys=True),
                            pattern_hash=sid.replace("fs_", "")[:16],
                            dims=f.get("dims") or {},
                            first_seen_at=now,
                            last_seen_at=now,
                            observation_count=1,
                        )
                    )
                    n_sig += 1
                else:
                    sig_row.last_seen_at = now
                    sig_row.observation_count = int(sig_row.observation_count or 0) + 1
                    n_sig += 1
                u = f.get("unresolved") or {}
                fu = _uid(ft_id, sid, u.get("octal_word"), u.get("low_desc"))
                session.add(
                    FailureEvent(
                        failure_uid=fu,
                        field_test_id=ft_id,
                        archive_sha=sha,
                        machine=str(capture.get("machine") or ""),
                        subsystem="physical_io",
                        pipeline_stage="PHYSICAL_WORD_RESOLVER",
                        resolver_rule="PhysicalWordResolver",
                        failure_code=str((f.get("dims") or {}).get("failure_reason") or ""),
                        signature_id=sid,
                        object_identity=str(u.get("octal_word") or ""),
                        physical_catalog_family=str(
                            (f.get("dims") or {}).get("catalog_signature") or ""
                        ),
                        raw_fact_uids=[],
                        source_scope="ACTIVE",
                        status="OPEN",
                        details={"unresolved": u, "dims": f.get("dims")},
                        created_at=now,
                    )
                )
                n_fail += 1
                # Upsert unknown cluster
                cid = f"uc_{sid.replace('fs_', '')[:16]}"
                uc = session.get(UnknownCluster, cid)
                machines = [capture["machine"]]
                if uc is None:
                    session.add(
                        UnknownCluster(
                            cluster_id=cid,
                            pattern_hash=sid.replace("fs_", "")[:16],
                            structural_pattern=json.dumps(f.get("dims") or {}, sort_keys=True),
                            count=1,
                            example_raw=[u],
                            archives=[sha] if sha else [],
                            machines=machines,
                            fields={
                                **(f.get("dims") or {}),
                                "signature_id": sid,
                                "evidence_class": INDEPENDENT_DERIVATION,
                            },
                            extractor_version=EXTRACTOR_VERSION,
                        )
                    )
                else:
                    uc.count = int(uc.count or 0) + 1
                    ms = list(uc.machines or [])
                    if capture["machine"] not in ms:
                        ms.append(capture["machine"])
                        uc.machines = ms
                    arcs = list(uc.archives or [])
                    if sha and sha not in arcs:
                        arcs.append(sha)
                        uc.archives = arcs
    return {
        "ok": True,
        "field_test_id": ft_id,
        "failure_events": n_fail,
        "signatures_touched": n_sig,
    }
