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

# MachineClosure focus tables for provenance emission (GATE 9)
_CLOSURE_FOCUS_TABLES = frozenset(
    {"Conveyor", "MergeBoss", "MergeInputs", "MergeRoute", "EStop", "SawLane", "SawMerge"}
)

# Site-specific equipment / merge / divert artifact shapes
_SITE_ARTIFACT_RE = re.compile(
    r"^(P\d{2,4}(?:_P\d+)?(?:_Merge|_Divert\d*|_Conv)?|"
    r".*_Merge|.+_Divert\d*)$",
    re.I,
)
_P_TOKEN_RE = re.compile(r"(P\d{2,4}(?:_P\d+)?)", re.I)

# Compiler / library / datatype placeholders — never orphans
_EXEMPT_ARTIFACT_RE = re.compile(
    r"""(?ix)
    ^(
        NO_[A-Za-z0-9_]+
        |Merge_2to1(?:_RAT)?
        |Merge_Time
        |Fast_Conv|Slow_Flt|Slow_Jam|Slow_ConvPI\d*
        |PE_Logic|Full_PE|Sawtooth_Merge
        |Comm_UDT|Barcode_Scanner_UDT|PE_UDT|Conv_UDT
        |ES_SIL1_Cat1|ES_PI\d+
        |Main_Area|Default_Area|Default\s+Safety|Unassigned\s+Safety
    )$
    """
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


def _derive_merge_query_names(identity: str, table: str) -> list[str]:
    """Extra search tokens so why P600_Merge can hit Fortna merge/conveyor paths."""
    names: list[str] = []
    ident = str(identity or "").strip()
    if not ident:
        return names
    names.append(ident)
    for tok in _P_TOKEN_RE.findall(ident):
        names.append(tok)
        names.append(f"{tok}_Merge")
        names.append(f"{tok}_Divert1")
    if table in {"MergeBoss", "MergeInputs", "MergeRoute", "SawMerge"}:
        compact = re.sub(r"\s+", "_", ident)
        if compact != ident:
            names.append(compact)
            names.append(f"{compact}_Merge")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def collect_machine_closure_provenance(
    run_dir: Path,
    machine: str,
) -> list[ProvenanceRecord]:
    """Emit ProvenanceRecords for MachineClosure members (GATE 9).

    Especially Conveyor / MergeBoss / MergeInputs / MergeRoute / EStop / SawLane,
    with full relationship_path in transform / sources / extras.
    """
    from fortna_machine_closure import build_machine_closure

    try:
        closure = build_machine_closure(run_dir, machine)
    except Exception as exc:
        return [
            ProvenanceRecord(
                id=_stable_id("closure-error", machine),
                subsystem="machine_closure",
                artifact="MachineClosure",
                decision="build_machine_closure",
                classification=CLASS_UNKNOWN,
                sources=[],
                transform=[],
                result=str(exc)[:200],
                evidence_missing=["machine_closure"],
                severity="warn",
            )
        ]

    records: list[ProvenanceRecord] = []
    for m in closure.get("members") or []:
        if not isinstance(m, dict):
            continue
        table = str(m.get("source_table") or "").strip()
        if table == "Machine":
            continue
        if table not in _CLOSURE_FOCUS_TABLES and table != "Mtrchain":
            # Focus tables especially; still keep Mtrchain as ownership walk evidence
            continue
        ident = str(m.get("identity") or "").strip()
        path = [str(p) for p in (m.get("relationship_path") or [])]
        merge_names = _derive_merge_query_names(ident, table)
        src_file = str(m.get("source_file") or f"{table}.asc")
        records.append(
            ProvenanceRecord(
                id=_stable_id("closure", machine, table, ident or m.get("source_id") or ""),
                subsystem="machine_closure",
                artifact=ident or str(m.get("source_id") or table),
                decision="machine_closure_membership",
                classification=CLASS_PROVEN,
                sources=[
                    src_file,
                    "fortna_machine_closure.build_machine_closure",
                    f"table:{table}",
                ],
                transform=path or ["Machine", table],
                result=f"{table}:{ident} via {' → '.join(path) if path else table}",
                evidence_available=[
                    f"source_id:{m.get('source_id')}",
                    f"provenance:{m.get('provenance') or 'RUN_EXPLICIT'}",
                ]
                + [f"merge_name:{n}" for n in merge_names[:6]],
                severity="info",
                found=True,
                included=True,
                generated=False,
                extras={
                    "relationship_path": path,
                    "identity": ident,
                    "source_table": table,
                    "source_id": m.get("source_id"),
                    "merge_names": merge_names,
                    "machine": machine,
                },
            )
        )
    return records


def collect_native_merge_provenance(
    run_dir: Path,
    machine: str,
) -> list[ProvenanceRecord]:
    """Emit ProvenanceRecords for native MergeBoss/MergeInputs/MergeRoute 2→1 merges.

    Discharge conveyors (e.g. P600) may have Machine_Name=N/A and therefore not
    appear as Conveyor.Machine_Name closure members. Ownership still flows:

      Machine → MergeBoss.Owner → MergeInputs → MergeRoute → discharge

    Artifacts include ``{downstream}_Merge`` so ``why P600_Merge`` resolves.
    """
    from fortna_plc2_merge_discovery import (
        discover_plc2_merges,
        discovery_to_autogen_merges_2to1,
    )

    try:
        report = discover_plc2_merges(run_dir, machine)
    except Exception as exc:
        return [
            ProvenanceRecord(
                id=_stable_id("native-merge-error", machine),
                subsystem="native_merge",
                artifact="native_merges_2to1",
                decision="discover_plc2_merges",
                classification=CLASS_UNKNOWN,
                sources=[],
                result=str(exc)[:200],
                evidence_missing=["native_merge_discovery"],
                severity="warn",
            )
        ]

    records: list[ProvenanceRecord] = []
    merges = list(report.get("merges") or [])
    # Also normalize via autogen shape for consistent discharge/name fields
    autogen_by_name = {
        str(m.get("discovery_name") or m.get("name") or ""): m
        for m in discovery_to_autogen_merges_2to1(report)
    }

    for m in merges:
        if not isinstance(m, dict):
            continue
        boss = str(m.get("name") or "").strip()
        downstream = str(
            m.get("downstream") or m.get("mergeSection3") or ""
        ).strip()
        auto = autogen_by_name.get(boss) or {}
        if not downstream:
            downstream = str(auto.get("discharge") or auto.get("name") or "").strip()
        cls = str(m.get("classification") or "").upper()
        classification = CLASS_PROVEN if cls == "PROVEN" else CLASS_REVIEW
        if cls in {"UNRESOLVED", "CANDIDATE"} and classification == CLASS_PROVEN:
            classification = CLASS_REVIEW

        path = [
            "Machine",
            f"MergeBoss.Owner:{boss}" if boss else "MergeBoss.Owner",
            "MergeInputs",
            "MergeRoute",
        ]
        if downstream:
            path.append(f"discharge:{downstream}")

        merge_names: list[str] = []
        for n in (
            boss,
            downstream,
            f"{downstream}_Merge" if downstream else "",
            auto.get("discovery_name"),
            auto.get("name"),
            m.get("mergeSection1"),
            m.get("mergeSection2"),
            m.get("mainLane"),
            m.get("inductLane"),
        ):
            if n:
                merge_names.extend(_derive_merge_query_names(str(n), "MergeBoss"))
        # de-dupe
        seen_n: set[str] = set()
        uniq_names: list[str] = []
        for n in merge_names:
            k = n.lower()
            if k in seen_n:
                continue
            seen_n.add(k)
            uniq_names.append(n)

        artifact = f"{downstream}_Merge" if downstream else (boss or "merge")
        evidence = m.get("evidence") or []
        evidence_kinds = [
            str(e.get("kind") or "")
            for e in evidence
            if isinstance(e, dict) and e.get("kind")
        ][:12]

        records.append(
            ProvenanceRecord(
                id=_stable_id("native-merge", machine, boss, downstream),
                subsystem="native_merge",
                artifact=artifact,
                decision="native_merge_2to1",
                classification=classification,
                sources=[
                    "MergeBoss.asc",
                    "MergeInputs.asc",
                    "MergeRoute.asc",
                    "fortna_plc2_merge_discovery.discover_plc2_merges",
                ],
                transform=path,
                result=(
                    f"{artifact} via MergeBoss:{boss} → lanes "
                    f"{m.get('mergeSection1')}/{m.get('mergeSection2')} → {downstream}"
                ),
                evidence_available=[f"evidence:{k}" for k in evidence_kinds]
                + [f"merge_name:{n}" for n in uniq_names[:10]],
                confidence=str(m.get("confidence") or classification),
                severity="info" if classification == CLASS_PROVEN else "warn",
                found=True,
                included=True,
                generated=False,
                extras={
                    "relationship_path": path,
                    "identity": downstream or boss,
                    "source_table": "MergeBoss",
                    "merge_names": uniq_names,
                    "discovery_name": boss,
                    "downstream": downstream,
                    "lane_a": m.get("mergeSection1") or m.get("mainLane"),
                    "lane_b": m.get("mergeSection2") or m.get("inductLane"),
                    "machine": machine,
                    "native_merge": True,
                },
            )
        )
        # Also emit boss-named record for why "2-1 SERVO"
        if boss and boss.lower() != artifact.lower():
            records.append(
                ProvenanceRecord(
                    id=_stable_id("native-merge-boss", machine, boss),
                    subsystem="native_merge",
                    artifact=boss,
                    decision="native_merge_boss",
                    classification=classification,
                    sources=[
                        "MergeBoss.asc",
                        "fortna_plc2_merge_discovery.discover_plc2_merges",
                    ],
                    transform=path,
                    result=f"MergeBoss:{boss} owns {artifact}",
                    evidence_available=[f"merge_name:{n}" for n in uniq_names[:8]],
                    severity="info",
                    found=True,
                    included=True,
                    generated=False,
                    extras={
                        "relationship_path": path,
                        "identity": boss,
                        "source_table": "MergeBoss",
                        "merge_names": uniq_names,
                        "downstream": downstream,
                        "machine": machine,
                        "native_merge": True,
                    },
                )
            )
    return records


def _closure_identity_index(records: list[ProvenanceRecord]) -> set[str]:
    """Normalized identities / merge tokens present in MachineClosure + native merge provenance."""
    out: set[str] = set()
    for r in records:
        if r.subsystem not in {"machine_closure", "native_merge"}:
            continue
        extras = r.extras or {}
        for key in (
            str(r.artifact or ""),
            str(extras.get("identity") or ""),
            str(extras.get("source_id") or ""),
            str(extras.get("discovery_name") or ""),
            str(extras.get("downstream") or ""),
        ):
            if key:
                out.add(key.strip().lower())
        for n in extras.get("merge_names") or []:
            if n:
                out.add(str(n).strip().lower())
        for step in extras.get("relationship_path") or []:
            s = str(step or "").strip()
            if not s:
                continue
            out.add(s.lower())
            # Conveyor:P600 / discharge:P600 → also index P600
            if ":" in s:
                out.add(s.split(":", 1)[-1].strip().lower())
            for tok in _P_TOKEN_RE.findall(s):
                out.add(tok.lower())
                out.add(f"{tok}_merge".lower())
    return out


def _is_exempt_artifact(name: str) -> bool:
    n = str(name or "").strip()
    if not n:
        return True
    if _EXEMPT_ARTIFACT_RE.match(n):
        return True
    # datatype / AOI style library names without site P-tags
    if n.startswith("NO_"):
        return True
    if re.match(r"^[A-Za-z_]+_UDT$", n):
        return True
    return False


def _candidate_site_artifacts(
    autogen_report: dict[str, Any] | None,
    transport_merges: list[Any] | None,
) -> list[dict[str, Any]]:
    """Collect site-specific merge/divert/equipment names from optional reports."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, *, origin: str, engineer: bool = False) -> None:
        n = str(name or "").strip()
        if not n or n.lower() in seen:
            return
        if _is_exempt_artifact(n):
            return
        # Only flag site-shaped merge/divert/equipment identities
        if not (
            _SITE_ARTIFACT_RE.match(n)
            or _P_TOKEN_RE.search(n)
            or "merge" in n.lower()
            or "divert" in n.lower()
        ):
            return
        seen.add(n.lower())
        found.append({"name": n, "origin": origin, "engineer_assigned": bool(engineer)})

    if isinstance(autogen_report, dict):
        merge_lists = []
        for key in ("merges", "merges_2to1", "transport_merges"):
            val = autogen_report.get(key)
            if isinstance(val, list):
                merge_lists.append((f"autogen_report.{key}", val))
        for origin, items in merge_lists:
            for m in items:
                if isinstance(m, str):
                    _add(m, origin=origin)
                    continue
                if not isinstance(m, dict):
                    continue
                eng = bool(
                    m.get("engineer_assigned")
                    or m.get("engineerAssigned")
                    or str(m.get("origin") or "").upper().startswith("ENGINEER")
                )
                for key in (
                    "name",
                    "merge_tag",
                    "tag",
                    "identity",
                    "artifact",
                    "discovery_name",
                    "discharge",
                ):
                    if m.get(key):
                        val = str(m.get(key))
                        _add(val, origin=origin, engineer=eng)
                        if re.match(r"^P\d{2,4}$", val, re.I):
                            _add(f"{val}_Merge", origin=origin, engineer=eng)
                # Downstream section often becomes {Pxxx}_Merge
                for key in ("mergeSection3", "downstream", "bossNumber", "discharge"):
                    val = m.get(key)
                    if val and re.match(r"^P\d{2,4}", str(val), re.I):
                        _add(f"{val}_Merge", origin=origin, engineer=eng)

        for eq in autogen_report.get("equipment") or autogen_report.get("conveyors") or []:
            if isinstance(eq, str):
                _add(eq, origin="autogen_report.equipment")
                continue
            if not isinstance(eq, dict):
                continue
            eng = bool(eq.get("engineer_assigned") or eq.get("engineerAssigned"))
            for key in ("name", "clean_name", "conveyor", "tag", "identity"):
                if eq.get(key):
                    _add(str(eq.get(key)), origin="autogen_report.equipment", engineer=eng)

        for t in autogen_report.get("generated_tags") or autogen_report.get("tags") or []:
            if isinstance(t, str):
                _add(t, origin="autogen_report.tags")
            elif isinstance(t, dict) and t.get("name"):
                eng = bool(t.get("engineer_assigned") or t.get("engineerAssigned"))
                _add(str(t.get("name")), origin="autogen_report.tags", engineer=eng)

        for d in autogen_report.get("diverts") or []:
            if isinstance(d, str):
                _add(d, origin="autogen_report.diverts")
            elif isinstance(d, dict):
                eng = bool(d.get("engineer_assigned") or d.get("engineerAssigned"))
                for key in ("name", "tag", "identity"):
                    if d.get(key):
                        _add(str(d.get(key)), origin="autogen_report.diverts", engineer=eng)

    for m in transport_merges or []:
        if isinstance(m, str):
            _add(m, origin="transport_merges")
        elif isinstance(m, dict):
            eng = bool(m.get("engineer_assigned") or m.get("engineerAssigned"))
            for key in ("name", "merge_tag", "tag", "identity", "artifact"):
                if m.get(key):
                    _add(str(m.get(key)), origin="transport_merges", engineer=eng)
            for key in ("mergeSection3", "downstream"):
                val = m.get(key)
                if val and re.match(r"^P\d{2,4}", str(val), re.I):
                    _add(f"{val}_Merge", origin="transport_merges", engineer=eng)

    return found


def _artifact_in_closure(name: str, closure_ids: set[str]) -> bool:
    n = str(name or "").strip().lower()
    if not n:
        return False
    if n in closure_ids:
        return True
    # P600_Merge → try P600 / P600_Merge
    stem = re.sub(r"_(merge|divert\d*|conv)$", "", n, flags=re.I)
    if stem in closure_ids:
        return True
    if f"{stem}_merge" in closure_ids:
        return True
    for tok in _P_TOKEN_RE.findall(name):
        tl = tok.lower()
        if tl in closure_ids or f"{tl}_merge" in closure_ids:
            return True
    return False


def collect_orphan_closure_checks(
    run_dir: Path,
    machine: str,
    *,
    autogen_report: dict[str, Any] | None = None,
    transport_merges: list[Any] | None = None,
    closure_records: list[ProvenanceRecord] | None = None,
) -> list[ProvenanceRecord]:
    """Flag site-specific artifacts absent from MachineClosure and not engineer-assigned."""
    closure_recs = list(closure_records or [])
    if not closure_recs:
        closure_recs = collect_machine_closure_provenance(run_dir, machine)
    closure_ids = _closure_identity_index(closure_recs)
    candidates = _candidate_site_artifacts(autogen_report, transport_merges)
    out: list[ProvenanceRecord] = []
    for c in candidates:
        name = c["name"]
        if c.get("engineer_assigned"):
            continue
        if _is_exempt_artifact(name):
            continue
        if _artifact_in_closure(name, closure_ids):
            continue
        out.append(
            ProvenanceRecord(
                id=_stable_id("orphan", machine, name),
                subsystem="anti_copy",
                artifact=name,
                decision="orphan_site_specific_artifact",
                classification=CLASS_REVIEW,
                sources=["autogen_report/transport_merges", "MachineClosure"],
                transform=[
                    "generated site-specific artifact",
                    "not in MachineClosure",
                    "not engineer-assigned",
                ],
                result=f"ORPHAN: {name} lacks MachineClosure membership",
                evidence_available=[f"origin:{c.get('origin')}"],
                evidence_missing=["machine_closure_membership", "engineer_assignment"],
                severity="error",
                found=True,
                included=True,
                generated=True,
                extras={
                    "orphan": True,
                    "origin": c.get("origin"),
                    "machine": machine,
                },
            )
        )
    return out


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
    transport_merges: list[Any] | None = None,
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
    transport_merges_in = list(transport_merges or [])
    if isinstance(autogen_report, dict):
        saw_build = autogen_report.get("sawtooth_build")
        if not transport_merges_in and isinstance(autogen_report.get("transport_merges"), list):
            transport_merges_in = list(autogen_report.get("transport_merges") or [])
    records.extend(
        collect_sawtooth_pack_provenance(
            run_dir,
            machine,
            autogen_report=autogen_report,
            sawtooth_build=saw_build if isinstance(saw_build, dict) else None,
        )
    )
    closure_recs = collect_machine_closure_provenance(run_dir, machine)
    records.extend(closure_recs)
    native_merge_recs = collect_native_merge_provenance(run_dir, machine)
    records.extend(native_merge_recs)
    # Native merge discharges count as closure-linked for orphan checks
    closure_for_orphans = list(closure_recs) + list(native_merge_recs)
    orphan_recs = collect_orphan_closure_checks(
        run_dir,
        machine,
        autogen_report=autogen_report,
        transport_merges=transport_merges_in,
        closure_records=closure_for_orphans,
    )
    records.extend(orphan_recs)
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
    orphans = [
        r
        for r in records
        if r.decision == "orphan_site_specific_artifact"
    ]

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine,
        "run_dir": str(run_dir),
        "finished_plc_used": False,
        "counts": {c: int(counts.get(c, 0)) for c in sorted(VALID_CLASSES)},
        "total_records": len(records),
        "orphan_generation_count": len(orphans),
        "records": [asdict(r) for r in records],
        "review_required": [asdict(r) for r in review],
        "unknown": [asdict(r) for r in unknown],
        "no_valid_lineage": [asdict(r) for r in no_lineage],
        "anti_copy": [asdict(r) for r in records if r.subsystem == "anti_copy"],
        "orphans": [asdict(r) for r in orphans],
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
        f"Orphan generation count: **{audit_doc.get('orphan_generation_count', 0)}**",
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
    _section("Orphan site-specific artifacts", audit_doc.get("orphans") or [])
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
    # P600_Merge / P506_Divert1 → also match stem P600 / P506
    q_stem = re.sub(r"_(merge|divert\d*|conv)$", "", q_norm, flags=re.I)
    hits = []
    for r in audit_doc.get("records") or []:
        artifact = str(r.get("artifact") or "")
        extras = r.get("extras") if isinstance(r.get("extras"), dict) else {}
        rel_path = extras.get("relationship_path") or []
        merge_names = extras.get("merge_names") or []
        identity = str(extras.get("identity") or "")
        blob = " ".join(
            [
                artifact,
                str(r.get("decision") or ""),
                str(r.get("result") or ""),
                " ".join(r.get("evidence_available") or []),
                " ".join(r.get("evidence_missing") or []),
                " ".join(str(p) for p in rel_path),
                " ".join(str(n) for n in merge_names),
                identity,
                str(extras.get("source_table") or ""),
                " ".join(str(s) for s in (r.get("sources") or [])),
                " ".join(str(t) for t in (r.get("transform") or [])),
            ]
        ).lower()
        art_norm = artifact.lower().replace("-", "_").replace(" ", "_")
        matched = (
            q in blob
            or q_norm in art_norm
            or q_norm in blob
            or (q_stem and q_stem != q_norm and q_stem in blob)
            or ("sawtooth" in q_norm and art_norm == "sawtooth_merge")
        )
        if matched:
            hits.append(r)
    # Prefer exact Sawtooth_Merge lineage record first when asked
    if "sawtooth" in q_norm:
        hits.sort(
            key=lambda r: 0 if str(r.get("artifact") or "") == "Sawtooth_Merge" else 1
        )
    # Prefer native_merge records for *_Merge queries (complete Fortna path)
    elif q_norm.endswith("_merge") or "merge" in q_norm:
        hits.sort(
            key=lambda r: (
                0
                if r.get("subsystem") == "native_merge"
                and str(r.get("artifact") or "").lower().replace("-", "_") == q_norm
                else 1
                if r.get("subsystem") == "native_merge"
                else 2
                if r.get("subsystem") == "machine_closure"
                else 3
            )
        )
    # Prefer MachineClosure path hits when querying merge/divert equipment tags
    elif "_merge" in q_norm or "divert" in q_norm or (q_stem and q_stem != q_norm):
        def _rank(r: dict[str, Any]) -> tuple[int, int]:
            extras = r.get("extras") if isinstance(r.get("extras"), dict) else {}
            has_path = 0 if extras.get("relationship_path") else 1
            sub = 0 if r.get("subsystem") == "machine_closure" else 1
            return (sub, has_path)

        hits.sort(key=_rank)
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
