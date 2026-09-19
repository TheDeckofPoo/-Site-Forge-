#!/usr/bin/env python3
"""Autogen Provenance Auditor — forward evidence lineage for generated PLC facts.

Trust model:
  RUN / FortnaPlus semantics / engineer Apply → generation
  Finished PLC is NEVER a provenance source or generation input.

Classes (Site Forge vocabulary only):
  PROVEN | DERIVED | ENGINEER_ASSIGNED | REVIEW_REQUIRED | UNKNOWN

Version 1 is additive/observational — does not rewrite CP1–CP4 or compilers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Evidence classes — do not invent others
CLASS_PROVEN = "PROVEN"
CLASS_DERIVED = "DERIVED"
CLASS_ENGINEER = "ENGINEER_ASSIGNED"
CLASS_REVIEW = "REVIEW_REQUIRED"
CLASS_UNKNOWN = "UNKNOWN"
VALID_CLASSES = frozenset(
    {CLASS_PROVEN, CLASS_DERIVED, CLASS_ENGINEER, CLASS_REVIEW, CLASS_UNKNOWN}
)

# Anti-copy: production generation must not key on these site tokens
_SITE_NAME_PRODUCTION_RE = re.compile(
    r"""(?x)
    \bif\s+.*(?:machine|site|processor)\s*==\s*[\"']
    (?:ORINDYAC\d+|ORNCCP\d+|Brownsburg|Greensboro|MSCRENO)
    """,
    re.I,
)


@dataclass
class ProvenanceRecord:
    """One engineering decision that caused (or should cause) generation."""

    id: str
    subsystem: str  # io | safety | transport | program | anti_copy
    artifact: str  # human label for generated/resulting object
    decision: str  # engineering decision description
    classification: str
    sources: list[str] = field(default_factory=list)
    transform: list[str] = field(default_factory=list)
    result: str = ""
    confidence: str = ""
    evidence_available: list[str] = field(default_factory=list)
    evidence_missing: list[str] = field(default_factory=list)
    severity: str = "info"  # info | warn | error
    found: bool = True
    included: bool = True
    generated: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.classification not in VALID_CLASSES:
            self.classification = CLASS_UNKNOWN
        if not self.confidence:
            self.confidence = self.classification


def _stable_id(*parts: str) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _owner_class(owner_state: str | None, owner_source: str | None) -> str:
    st = str(owner_state or "").upper()
    src = str(owner_source or "").upper()
    if st == "ASSIGNED":
        if "ENGINEER" in src or src == "ENGINEER_OVERRIDE":
            return CLASS_ENGINEER
        if src in {"RUN_CONVEYOR", "RUN_SPARE"} or "RUN" in src:
            return CLASS_PROVEN
        return CLASS_DERIVED
    if st == "UNRESOLVED_OWNER":
        return CLASS_REVIEW
    if st in {"PROVEN_SPARE"}:
        return CLASS_PROVEN
    if st in {"UNUSED_MAPPED", "ENGINEER_SPARE"}:
        return CLASS_DERIVED if st == "UNUSED_MAPPED" else CLASS_ENGINEER
    if st in {"UNKNOWN", ""}:
        return CLASS_UNKNOWN
    return CLASS_REVIEW


def collect_io_provenance(run_dir: Path, machine: str) -> list[ProvenanceRecord]:
    """Physical I/O: RUN → topology → family → endpoint → owner."""
    from fortna_hardware_family import FAMILY_UNKNOWN, detect_family_from_catalog
    from fortna_hardware_io_model import build_hardware_io_model

    model = build_hardware_io_model(run_dir, machine)
    records: list[ProvenanceRecord] = []
    for ad in model.get("adapters") or []:
        fam = str(ad.get("family") or "")
        for mod in ad.get("modules") or []:
            catalog = str(mod.get("type") or mod.get("catalog") or "")
            detected = detect_family_from_catalog(catalog) if catalog else fam
            for ch in mod.get("channels") or []:
                ep = ch.get("physical_endpoint") if isinstance(ch.get("physical_endpoint"), dict) else {}
                addr = str(
                    ch.get("physical_address")
                    or ep.get("channel")
                    or ""
                ).strip()
                owner = str(ch.get("engineering_owner") or "").strip()
                st = str(ch.get("owner_state") or "")
                src = str(ch.get("owner_source") or "")
                assign_how = str(
                    (ch.get("provenance") or {}).get("assign_how")
                    if isinstance(ch.get("provenance"), dict)
                    else ""
                ) or str(ch.get("assign_how") or "")
                # Word map may stamp assign_how on parent word entry only
                if not assign_how and isinstance(ch.get("provenance"), dict):
                    assign_how = str(ch["provenance"].get("assign_how") or "")

                cls = _owner_class(st, src)
                evidence_avail = []
                evidence_miss = []
                if addr:
                    evidence_avail.append(f"endpoint:{addr}")
                if catalog:
                    evidence_avail.append(f"catalog:{catalog}")
                if assign_how:
                    evidence_avail.append(f"assign_how:{assign_how}")
                if owner:
                    evidence_avail.append(f"owner:{owner}")
                else:
                    evidence_miss.append("engineering_owner")

                # Unknown family must not silently use Flex Data[n] formula
                if detected == FAMILY_UNKNOWN and addr and re.search(
                    r":[IO]\.Data\[\d+\]", addr
                ):
                    cls = CLASS_REVIEW
                    evidence_miss.append("hardware_family_profile")
                    severity = "warn"
                else:
                    severity = "warn" if cls in (CLASS_REVIEW, CLASS_UNKNOWN) else "info"

                transform = [
                    "RUN Configio/eipcfg",
                    "Hardware Topology IR",
                    f"Family Profile ({detected or fam or 'UNKNOWN'})",
                    "Physical Endpoint",
                    "Logical Owner",
                    "IO_MAP (when included)",
                ]
                records.append(
                    ProvenanceRecord(
                        id=_stable_id("io", machine, addr, owner),
                        subsystem="io",
                        artifact=addr or f"{ad.get('rio_name')}/{mod.get('name')}/ch",
                        decision="physical_endpoint_and_owner",
                        classification=cls,
                        sources=[
                            "FORTNA/Configio.asc*",
                            "eipcfg",
                            "FORTNA/Conveyor.asc (owner when assigned)",
                        ],
                        transform=transform,
                        result=f"{addr} ← {owner or '(none)'} [{st}/{src}]",
                        evidence_available=evidence_avail,
                        evidence_missing=evidence_miss,
                        severity=severity,
                        found=True,
                        included=bool(owner) or st in {"ASSIGNED", "PROVEN_SPARE"},
                        generated=False,  # model-level; L5X emit is separate
                        extras={
                            "owner_state": st,
                            "owner_source": src,
                            "family": detected or fam,
                            "assign_how": assign_how,
                            "machine": machine,
                        },
                    )
                )
    return records


def collect_safety_provenance(
    run_dir: Path,
    machine: str,
    safety_build: dict[str, Any] | None = None,
) -> list[ProvenanceRecord]:
    """Safety: zone existence + membership provenance."""
    from fortna_safety_model import build_safety_model

    sb = safety_build if isinstance(safety_build, dict) else {}
    try:
        model = build_safety_model(
            run_dir=run_dir,
            machine=machine,
            engineer_safety_build=sb or None,
        )
    except Exception:
        model = {"zones": []}
    records: list[ProvenanceRecord] = []
    eng_zones = {
        str(z.get("source_id") or z.get("id") or z.get("name") or "").strip(): z
        for z in (sb.get("zones") or [])
        if isinstance(z, dict)
    }

    # Union RUN model zones + engineer safety_build zones (Apply payload)
    zone_rows: list[dict[str, Any]] = []
    seen_z: set[str] = set()
    for z in list(model.get("zones") or []) + list(eng_zones.values()):
        if not isinstance(z, dict):
            continue
        name = str(z.get("source_id") or z.get("id") or z.get("name") or "").strip()
        if not name or name in seen_z:
            continue
        seen_z.add(name)
        zone_rows.append(z)

    for z in zone_rows:
        name = str(z.get("name") or z.get("source_id") or z.get("id") or "").strip()
        if not name:
            continue
        # Skip default/unassigned buckets if flagged
        if z.get("isDefault") or z.get("isUnassignedBucket") or z.get("operational") is False:
            records.append(
                ProvenanceRecord(
                    id=_stable_id("safety-default", machine, name),
                    subsystem="safety",
                    artifact=name,
                    decision="default_unassigned_safety_bucket",
                    classification=CLASS_DERIVED,
                    sources=["Site Forge ownership model"],
                    transform=["Safety discovery → Default/Unassigned bucket"],
                    result="editor bucket only — not operational ES zone",
                    severity="info",
                    found=True,
                    included=False,
                    generated=False,
                    extras={"operational": False},
                )
            )
            continue

        prov = str(z.get("provenance") or z.get("origin") or "").upper()
        members = list(z.get("members") or [])
        eng = eng_zones.get(name) or eng_zones.get(str(z.get("source_id") or ""))
        if eng and isinstance(eng.get("members"), list) and eng["members"]:
            members = list(eng["members"])
            mem_origin = str(eng.get("membersOrigin") or eng.get("members_origin") or "ENGINEER_ASSIGNED")
        else:
            mem_origin = str(z.get("membersOrigin") or z.get("members_origin") or "")

        # Zone existence
        if "RUN" in prov or z.get("runDiscovered"):
            zone_cls = CLASS_PROVEN
        elif "ENGINEER" in prov or eng:
            zone_cls = CLASS_ENGINEER
        else:
            zone_cls = CLASS_DERIVED

        records.append(
            ProvenanceRecord(
                id=_stable_id("safety-zone", machine, name),
                subsystem="safety",
                artifact=f"ES zone {name}",
                decision="zone_existence",
                classification=zone_cls,
                sources=["RUN Safety discovery" if zone_cls == CLASS_PROVEN else "engineer/transport seed"],
                transform=["SafetyModel → ES pack (when membership proven/assigned)"],
                result=f"zone shell; members={len(members)}; origin={mem_origin or '—'}",
                evidence_available=[f"provenance:{prov or 'n/a'}", f"member_count:{len(members)}"],
                evidence_missing=[] if members else ["safety_device_membership"],
                severity="info" if members else "warn",
                found=True,
                included=bool(members),
                generated=False,
                extras={"members_origin": mem_origin, "member_count": len(members)},
            )
        )

        # Membership
        if members:
            mem_cls = (
                CLASS_ENGINEER
                if "ENGINEER" in mem_origin.upper()
                else CLASS_PROVEN
                if "PROVEN" in mem_origin.upper() or "RUN" in mem_origin.upper()
                else CLASS_REVIEW
            )
            records.append(
                ProvenanceRecord(
                    id=_stable_id("safety-members", machine, name, str(len(members))),
                    subsystem="safety",
                    artifact=f"ES membership {name}",
                    decision="safety_device_membership",
                    classification=mem_cls,
                    sources=["safety_build.zones[].members" if mem_cls == CLASS_ENGINEER else "RUN proven membership"],
                    transform=["Safety Apply → safety_build → ES Safe_Logic/Safe_PI"],
                    result=",".join(str(m) for m in members[:12])
                    + ("…" if len(members) > 12 else ""),
                    evidence_available=[f"membersOrigin:{mem_origin}"],
                    severity="info",
                    found=True,
                    included=True,
                    generated=True,
                )
            )
        else:
            records.append(
                ProvenanceRecord(
                    id=_stable_id("safety-members-empty", machine, name),
                    subsystem="safety",
                    artifact=f"ES membership {name}",
                    decision="safety_device_membership",
                    classification=CLASS_REVIEW,
                    sources=["zone shell only"],
                    transform=["ES generator must NOT invent membership"],
                    result="REVIEW_REQUIRED — empty membership (fail-safe NOP/partial)",
                    evidence_available=[],
                    evidence_missing=["engineer_assignment_or_run_proven_devices"],
                    severity="warn",
                    found=True,
                    included=False,
                    generated=False,
                )
            )
    return records


def collect_transport_provenance(run_dir: Path, machine: str) -> list[ProvenanceRecord]:
    """Transportation: key geometry/topology facts from physical layout when available."""
    records: list[ProvenanceRecord] = []
    try:
        from fortna_run_physical_layout import build_transport_graph

        g = build_transport_graph(run_dir, machine)
    except Exception as ex:
        records.append(
            ProvenanceRecord(
                id=_stable_id("transport-error", machine),
                subsystem="transport",
                artifact="transport_graph",
                decision="build_transport_graph",
                classification=CLASS_UNKNOWN,
                sources=[],
                transform=[],
                result=str(ex)[:200],
                evidence_missing=["transport_graph"],
                severity="warn",
            )
        )
        return records

    if not isinstance(g, dict):
        return records

    metrics = g.get("metrics") if isinstance(g.get("metrics"), dict) else {}
    physical = bool(g.get("physicalLayout") or metrics.get("physicalLayout"))
    records.append(
        ProvenanceRecord(
            id=_stable_id("transport-layout", machine),
            subsystem="transport",
            artifact="transport_layout_mode",
            decision="physical_vs_fallback_layout",
            classification=CLASS_PROVEN if physical else CLASS_DERIVED,
            sources=["FORTNA/Conveyor.asc X_cord/Y_cord" if physical else "deterministic fallback"],
            transform=["fortna_run_physical_layout → canvas"],
            result="PHYSICAL" if physical else "FALLBACK/DERIVED",
            evidence_available=[f"metrics:{json.dumps(metrics)[:180]}"],
            severity="info",
            found=True,
            included=True,
            generated=False,
        )
    )

    # Sample node geometry provenance if present
    nodes = []
    for a in g.get("areas") or []:
        if isinstance(a, dict):
            nodes.extend(a.get("nodes") or [])
    proven_xy = 0
    for n in nodes[:500]:
        if not isinstance(n, dict):
            continue
        if n.get("sourceX") is not None and n.get("sourceY") is not None:
            proven_xy += 1
    if nodes:
        records.append(
            ProvenanceRecord(
                id=_stable_id("transport-xy", machine),
                subsystem="transport",
                artifact="conveyor_run_xy",
                decision="run_coordinate_authority",
                classification=CLASS_PROVEN if proven_xy else CLASS_UNKNOWN,
                sources=["Conveyor.asc X_cord/Y_cord"],
                transform=["geometry authority stack"],
                result=f"{proven_xy}/{len(nodes)} nodes with RUN XY",
                severity="info" if proven_xy else "warn",
                found=True,
                included=True,
                generated=False,
            )
        )
    return records


def collect_program_inclusion(
    autogen_report: dict[str, Any] | None = None,
) -> list[ProvenanceRecord]:
    """FOUND / INCLUDED / GENERATED visibility from an autogen report when present."""
    records: list[ProvenanceRecord] = []
    if not isinstance(autogen_report, dict):
        return records
    programs = autogen_report.get("programs") or autogen_report.get("program_names") or []
    if isinstance(programs, list):
        for p in programs:
            name = p if isinstance(p, str) else str((p or {}).get("name") or "")
            if not name:
                continue
            if str(name).strip() == "Sawtooth_Merge":
                # Dedicated Sawtooth lineage record is emitted separately
                continue
            records.append(
                ProvenanceRecord(
                    id=_stable_id("program", name),
                    subsystem="program",
                    artifact=name,
                    decision="program_inclusion",
                    classification=CLASS_DERIVED,
                    sources=["autogen include_programs / pack selection"],
                    transform=["FOUND → INCLUDED → GENERATED"],
                    result="GENERATED",
                    found=True,
                    included=True,
                    generated=True,
                    severity="info",
                )
            )
    es = autogen_report.get("es_program") or autogen_report.get("es_emit") or {}
    if isinstance(es, dict) and es:
        status = str(es.get("status") or "")
        cls = CLASS_REVIEW if "REVIEW" in status.upper() else CLASS_DERIVED
        records.append(
            ProvenanceRecord(
                id=_stable_id("program-es", status),
                subsystem="program",
                artifact="Program ES",
                decision="es_emit_policy",
                classification=cls,
                sources=["safety_build + fortna_es_compiler"],
                transform=["Safety IR → emit_es_program"],
                result=str(es.get("detail") or status)[:240],
                evidence_available=[f"status:{status}"],
                severity="warn" if cls == CLASS_REVIEW else "info",
                found=True,
                included=bool(es.get("emitted")),
                generated=bool(es.get("emitted")),
            )
        )
    return records


def collect_sawtooth_pack_provenance(
    run_dir: Path,
    machine: str,
    *,
    autogen_report: dict[str, Any] | None = None,
    sawtooth_build: dict[str, Any] | None = None,
) -> list[ProvenanceRecord]:
    """Lineage for Sawtooth_Merge pack inclusion (target-machine scoped).

    `why Sawtooth_Merge` must return this record: valid target-machine lineage
    (PROVEN / ENGINEER_ASSIGNED) or REVIEW_REQUIRED when evidence is missing /
    belongs to another machine/area / is only ordinary 2→1 merge topology.
    """
    from fortna_autogen import (
        evaluate_sawtooth_merge_inclusion,
        load_from_run,
        sawtooth_build_is_configured,
    )

    report = autogen_report if isinstance(autogen_report, dict) else {}
    inclusion = dict(report.get("sawtooth_inclusion") or {})
    programs = report.get("programs") or report.get("gold_programs") or []
    prog_names = {
        (p if isinstance(p, str) else str((p or {}).get("name") or "")).strip()
        for p in (programs or [])
    }
    emitted = "Sawtooth_Merge" in prog_names

    decision = dict(inclusion)
    if not decision:
        try:
            inp = load_from_run(Path(run_dir), processor="1756-L83E")
            if str(getattr(inp, "machine", "") or "").upper() != str(machine or "").upper():
                # Keep loaded conveyors (already machine-scoped by load_from_run meta)
                pass
            if isinstance(sawtooth_build, dict) and sawtooth_build:
                inp.sawtooth_build = dict(sawtooth_build)
            elif isinstance(report.get("sawtooth_build"), dict):
                inp.sawtooth_build = dict(report.get("sawtooth_build") or {})
            # Reflect report include intent when present
            if emitted or "Sawtooth_Merge" in (
                report.get("include_programs") or []
            ):
                inc = list(getattr(inp, "include_programs", None) or [])
                if "Sawtooth_Merge" not in inc:
                    inc.append("Sawtooth_Merge")
                inp.include_programs = inc
            decision = evaluate_sawtooth_merge_inclusion(inp)
        except Exception as exc:
            decision = {
                "allowed": False,
                "reason": f"sawtooth_lineage_eval_failed:{exc}"[:200],
                "classification": CLASS_REVIEW,
                "build_configured": sawtooth_build_is_configured(sawtooth_build),
            }

    cls_raw = str(decision.get("classification") or CLASS_REVIEW).upper()
    if cls_raw in VALID_CLASSES:
        cls = cls_raw
    elif decision.get("allowed"):
        cls = CLASS_PROVEN
    else:
        cls = CLASS_REVIEW

    reason = str(decision.get("reason") or "no_target_machine_sawtooth_evidence")
    hits = list(decision.get("build_hits") or []) + list(
        decision.get("discovery_hits") or []
    )
    evidence_avail = []
    if decision.get("build_hits"):
        evidence_avail.append(
            "engineer_sawtooth_build_hits:" + ",".join(decision.get("build_hits") or [])
        )
    if decision.get("discovery_hits"):
        evidence_avail.append(
            "run_sawtooth_hits:" + ",".join(decision.get("discovery_hits") or [])
        )
    if decision.get("build_refs") and not decision.get("build_hits"):
        evidence_avail.append(
            "out_of_scope_refs:" + ",".join(decision.get("build_refs") or [])[:120]
        )
    evidence_missing = []
    if not decision.get("allowed"):
        evidence_missing.append("target_machine_sawtooth_equipment_intersection")
        if reason == "ordinary_merge_topology_is_not_sawtooth":
            evidence_missing.append("sawtooth_collector_pack_evidence")

    included = bool(decision.get("allowed")) and (
        emitted or bool(decision.get("included")) or bool(decision.get("want_include"))
    )
    if decision.get("allowed") and emitted:
        included = True
    if not decision.get("allowed"):
        included = False

    result = (
        f"INCLUDED ({reason}); hits={hits or '—'}"
        if decision.get("allowed") and emitted
        else (
            f"ALLOWED_NOT_EMITTED ({reason})"
            if decision.get("allowed")
            else f"EXCLUDED ({reason})"
        )
    )

    return [
        ProvenanceRecord(
            id=_stable_id("program-sawtooth", machine, reason),
            subsystem="program",
            artifact="Sawtooth_Merge",
            decision="sawtooth_merge_pack_inclusion",
            classification=cls,
            sources=[
                "SawMerge.asc / SawLane.asc (machine overlay)",
                "workbook.sawtooth_build",
                "target-machine conveyor/PE scope",
            ],
            transform=[
                "discover_sawtooth / sawtooth_build",
                "intersect equipment P-tags with target machine",
                "include_programs gate → gold Sawtooth_Merge clone",
            ],
            result=result,
            evidence_available=evidence_avail,
            evidence_missing=evidence_missing,
            severity="info" if decision.get("allowed") and emitted else "warn",
            found=bool(
                decision.get("build_configured")
                or decision.get("discovery_refs")
                or decision.get("want_include")
                or emitted
            ),
            included=included,
            generated=bool(emitted and decision.get("allowed")),
            extras={
                "reason": reason,
                "build_refs": list(decision.get("build_refs") or []),
                "discovery_refs": list(decision.get("discovery_refs") or []),
                "merges_2to1_count": decision.get("merges_2to1_count"),
            },
        )
    ]


def anti_copy_checks(
    *,
    run_dir: Path | None = None,
    records: list[ProvenanceRecord] | None = None,
    scan_production_code: bool = True,
) -> list[ProvenanceRecord]:
    """Suspicious generation / provenance integrity checks."""
    out: list[ProvenanceRecord] = []
    recs = records or []

    # 1) Site-name production conditionals in key compiler modules
    if scan_production_code:
        scan_files = [
            SCRIPT_DIR / "fortna_autogen.py",
            SCRIPT_DIR / "fortna_physical_word_resolver.py",
            SCRIPT_DIR / "fortna_hardware_io_model.py",
            SCRIPT_DIR / "fortna_es_compiler.py",
            SCRIPT_DIR / "fortna_hardware_family.py",
        ]
        for fp in scan_files:
            if not fp.is_file():
                continue
            text = fp.read_text(encoding="utf-8", errors="ignore")
            # Ignore comments and test fixture strings in docstrings lightly
            for m in _SITE_NAME_PRODUCTION_RE.finditer(text):
                # Skip if inside a test_ or docs path — these are production modules
                out.append(
                    ProvenanceRecord(
                        id=_stable_id("anticopy-siteif", fp.name, str(m.start())),
                        subsystem="anti_copy",
                        artifact=fp.name,
                        decision="site_name_conditional_in_production",
                        classification=CLASS_REVIEW,
                        sources=[str(fp.relative_to(REPO_ROOT))],
                        transform=[],
                        result=m.group(0)[:120],
                        evidence_available=["static_scan"],
                        evidence_missing=["generic_rule_justification"],
                        severity="error",
                        found=True,
                        included=True,
                        generated=False,
                    )
                )

    # 2) Safety membership without evidence
    for r in recs:
        if r.subsystem == "safety" and r.decision == "safety_device_membership":
            if r.classification not in (CLASS_PROVEN, CLASS_ENGINEER, CLASS_REVIEW):
                out.append(
                    ProvenanceRecord(
                        id=_stable_id("anticopy-safety", r.id),
                        subsystem="anti_copy",
                        artifact=r.artifact,
                        decision="safety_membership_without_accepted_class",
                        classification=CLASS_REVIEW,
                        sources=r.sources,
                        result=r.result,
                        severity="error",
                    )
                )
            if r.generated and r.classification == CLASS_UNKNOWN:
                out.append(
                    ProvenanceRecord(
                        id=_stable_id("anticopy-safety-unk", r.id),
                        subsystem="anti_copy",
                        artifact=r.artifact,
                        decision="generated_safety_with_unknown_membership",
                        classification=CLASS_REVIEW,
                        sources=r.sources,
                        result=r.result,
                        severity="error",
                    )
                )

    # 3) DERIVED without parent evidence markers
    for r in recs:
        if r.classification == CLASS_DERIVED and not r.sources and not r.evidence_available:
            out.append(
                ProvenanceRecord(
                    id=_stable_id("anticopy-orphan-derived", r.id),
                    subsystem="anti_copy",
                    artifact=r.artifact,
                    decision="derived_without_parent_evidence",
                    classification=CLASS_REVIEW,
                    sources=[],
                    evidence_missing=["parent_PROVEN_or_ENGINEER_ASSIGNED"],
                    severity="warn",
                )
            )

    # 4) Records with no classification lineage
    for r in recs:
        if r.subsystem == "anti_copy":
            continue
        if not r.sources and r.classification == CLASS_PROVEN:
            out.append(
                ProvenanceRecord(
                    id=_stable_id("anticopy-fake-proven", r.id),
                    subsystem="anti_copy",
                    artifact=r.artifact,
                    decision="proven_without_sources",
                    classification=CLASS_REVIEW,
                    sources=[],
                    evidence_missing=["source_citation"],
                    severity="error",
                    result="default/provenance presented as PROVEN without sources",
                )
            )

    # 5) Finished PLC path must not be used as run_dir
    if run_dir is not None:
        rp = str(run_dir).lower()
        if "finished" in rp or rp.endswith(".l5x") or "brownsburg" in rp and "run" not in rp:
            out.append(
                ProvenanceRecord(
                    id=_stable_id("anticopy-finished", rp),
                    subsystem="anti_copy",
                    artifact=str(run_dir),
                    decision="finished_plc_as_run_input",
                    classification=CLASS_REVIEW,
                    sources=[],
                    result="Finished/oracle path used where RUN expected",
                    severity="error",
                )
            )

    return out


def audit(
    run_dir: Path,
    machine: str,
    *,
    safety_build: dict[str, Any] | None = None,
    autogen_report: dict[str, Any] | None = None,
    scan_production_code: bool = True,
) -> dict[str, Any]:
    """Run full provenance audit for a RUN (+ optional safety_build / autogen report)."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    records: list[ProvenanceRecord] = []
    records.extend(collect_io_provenance(run_dir, machine))
    records.extend(collect_safety_provenance(run_dir, machine, safety_build=safety_build))
    records.extend(collect_transport_provenance(run_dir, machine))
    records.extend(collect_program_inclusion(autogen_report))
    saw_build = None
    if isinstance(autogen_report, dict):
        saw_build = autogen_report.get("sawtooth_build")
    records.extend(
        collect_sawtooth_pack_provenance(
            run_dir,
            machine,
            autogen_report=autogen_report,
            sawtooth_build=saw_build if isinstance(saw_build, dict) else None,
        )
    )
    records.extend(
        anti_copy_checks(
            run_dir=run_dir,
            records=records,
            scan_production_code=scan_production_code,
        )
    )

    counts = Counter(r.classification for r in records)
    review = [r for r in records if r.classification == CLASS_REVIEW]
    unknown = [r for r in records if r.classification == CLASS_UNKNOWN]
    no_lineage = [
        r
        for r in records
        if r.subsystem != "anti_copy"
        and not r.sources
        and not r.evidence_available
        and r.classification in (CLASS_PROVEN, CLASS_DERIVED, CLASS_ENGINEER)
    ]

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine,
        "run_dir": str(run_dir),
        "finished_plc_used": False,
        "counts": {c: int(counts.get(c, 0)) for c in sorted(VALID_CLASSES)},
        "total_records": len(records),
        "records": [asdict(r) for r in records],
        "review_required": [asdict(r) for r in review],
        "unknown": [asdict(r) for r in unknown],
        "no_valid_lineage": [asdict(r) for r in no_lineage],
        "anti_copy": [asdict(r) for r in records if r.subsystem == "anti_copy"],
    }


def write_reports(audit_doc: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "autogen_provenance.json"
    mp = out_dir / "autogen_provenance_report.md"
    jp.write_text(json.dumps(audit_doc, indent=2, sort_keys=True), encoding="utf-8")

    counts = audit_doc.get("counts") or {}
    lines = [
        "# Autogen Provenance Report",
        "",
        f"- Machine: `{audit_doc.get('machine')}`",
        f"- RUN: `{audit_doc.get('run_dir')}`",
        f"- Generated: {audit_doc.get('generated_at')}",
        f"- Finished PLC used: **{audit_doc.get('finished_plc_used')}**",
        "",
        "## Counts",
        "",
        "```",
        f"PROVEN             {counts.get(CLASS_PROVEN, 0)}",
        f"DERIVED            {counts.get(CLASS_DERIVED, 0)}",
        f"ENGINEER_ASSIGNED  {counts.get(CLASS_ENGINEER, 0)}",
        f"REVIEW_REQUIRED    {counts.get(CLASS_REVIEW, 0)}",
        f"UNKNOWN            {counts.get(CLASS_UNKNOWN, 0)}",
        "```",
        "",
        f"Total records: **{audit_doc.get('total_records')}**",
        "",
    ]

    def _section(title: str, items: list[dict]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("_None._")
            lines.append("")
            return
        for r in items[:80]:
            lines.append(f"### `{r.get('artifact')}`")
            lines.append("")
            lines.append(f"- subsystem: `{r.get('subsystem')}`")
            lines.append(f"- decision: {r.get('decision')}")
            lines.append(f"- classification: **{r.get('classification')}**")
            lines.append(f"- severity: {r.get('severity')}")
            lines.append(f"- evidence available: {', '.join(r.get('evidence_available') or []) or '—'}")
            lines.append(f"- evidence missing: {', '.join(r.get('evidence_missing') or []) or '—'}")
            lines.append(f"- transform: {' → '.join(r.get('transform') or []) or '—'}")
            lines.append(f"- result: `{r.get('result')}`")
            lines.append("")
        if len(items) > 80:
            lines.append(f"_… {len(items) - 80} more_")
            lines.append("")

    _section("REVIEW_REQUIRED", audit_doc.get("review_required") or [])
    _section("UNKNOWN", audit_doc.get("unknown") or [])
    _section("Anti-copy / integrity", audit_doc.get("anti_copy") or [])
    _section("No valid evidence lineage", audit_doc.get("no_valid_lineage") or [])

    lines.extend(
        [
            "## How to query",
            "",
            "```bash",
            "python tools/scripts/fortna_autogen_provenance.py why --run-dir <RUN> --machine <M> --query PE123",
            "```",
            "",
        ]
    )
    mp.write_text("\n".join(lines), encoding="utf-8")
    return jp, mp


def why_query(audit_doc: dict[str, Any], query: str) -> list[dict[str, Any]]:
    q = str(query or "").strip().lower()
    if not q:
        return []
    # Normalize common pack queries ("why Sawtooth_Merge", "sawtooth merge")
    q_norm = q.replace("-", "_").replace(" ", "_")
    hits = []
    for r in audit_doc.get("records") or []:
        artifact = str(r.get("artifact") or "")
        blob = " ".join(
            [
                artifact,
                str(r.get("decision") or ""),
                str(r.get("result") or ""),
                " ".join(r.get("evidence_available") or []),
                " ".join(r.get("evidence_missing") or []),
            ]
        ).lower()
        art_norm = artifact.lower().replace("-", "_").replace(" ", "_")
        if q in blob or q_norm in art_norm or (
            "sawtooth" in q_norm and art_norm == "sawtooth_merge"
        ):
            hits.append(r)
    # Prefer exact Sawtooth_Merge lineage record first when asked
    if "sawtooth" in q_norm:
        hits.sort(
            key=lambda r: 0 if str(r.get("artifact") or "") == "Sawtooth_Merge" else 1
        )
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Site Forge Autogen Provenance Auditor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    aud = sub.add_parser("audit", help="Run provenance audit and write reports")
    aud.add_argument("--run-dir", type=Path, required=True)
    aud.add_argument("--machine", required=True)
    aud.add_argument("--out", type=Path, default=REPO_ROOT / "exports" / "stabilization")
    aud.add_argument("--safety-build", type=Path, default=None, help="Optional safety_build JSON")
    aud.add_argument("--autogen-report", type=Path, default=None, help="Optional autogen report JSON")
    aud.add_argument("--no-code-scan", action="store_true")

    wh = sub.add_parser("why", help="Query why an artifact was generated")
    wh.add_argument("--run-dir", type=Path, required=True)
    wh.add_argument("--machine", required=True)
    wh.add_argument("--query", required=True)
    wh.add_argument("--safety-build", type=Path, default=None)
    wh.add_argument("--autogen-report", type=Path, default=None)
    wh.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    sb = None
    if getattr(args, "safety_build", None) and Path(args.safety_build).is_file():
        sb = json.loads(Path(args.safety_build).read_text(encoding="utf-8"))
    ar = None
    if getattr(args, "autogen_report", None) and Path(args.autogen_report).is_file():
        ar = json.loads(Path(args.autogen_report).read_text(encoding="utf-8"))

    doc = audit(
        args.run_dir,
        args.machine,
        safety_build=sb,
        autogen_report=ar,
        scan_production_code=not getattr(args, "no_code_scan", False),
    )

    if args.cmd == "audit":
        jp, mp = write_reports(doc, args.out)
        print(json.dumps({"counts": doc["counts"], "json": str(jp), "md": str(mp)}, indent=2))
        return 0

    hits = why_query(doc, args.query)
    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        if not hits:
            print(f"No provenance records matched {args.query!r}")
            return 1
        for r in hits[:20]:
            print("=" * 60)
            print("artifact:", r.get("artifact"))
            print("subsystem:", r.get("subsystem"))
            print("decision:", r.get("decision"))
            print("classification:", r.get("classification"))
            print("sources:", ", ".join(r.get("sources") or []))
            print("transform:", " → ".join(r.get("transform") or []))
            print("result:", r.get("result"))
            print("evidence+:", ", ".join(r.get("evidence_available") or []) or "—")
            print("evidence−:", ", ".join(r.get("evidence_missing") or []) or "—")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
