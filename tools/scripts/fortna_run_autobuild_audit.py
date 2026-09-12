#!/usr/bin/env python3
"""RUN-only audit of Auto Build From RUN results (evidence gathering).

SOURCE-OF-TRUTH: This script must NEVER read a finished/reference L5X.
It audits Conveyor.asc, Mtrchain, Merge* tables, and the Auto Build geometry
pipeline using RUN evidence only.

Usage:
  python fortna_run_autobuild_audit.py \\
    --run-dir workspace/active/RUN \\
    --machine ORNCCP2 \\
    --out exports/run-geometry/audit
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _anchors,
    _angle_delta,
    _clean,
    _dist,
    _f,
    _is_mech_conveyor,
    _is_motor_row,
    _is_pe_row,
    _load_merge_hints,
    _load_mtrchain,
    investigate,
)
from fortna_run_physical_layout import build_transport_graph  # noqa: E402

try:
    from fortna_autogen import _load_eip_adapters, load_from_run
except Exception:  # pragma: no cover
    _load_eip_adapters = None  # type: ignore
    load_from_run = None  # type: ignore

try:
    from fortna_io_extract import belongs_to_controller, row_machine_matches
except Exception:  # pragma: no cover
    belongs_to_controller = None  # type: ignore
    row_machine_matches = None  # type: ignore

MECH = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p_tag_ok(name: str) -> bool:
    return bool(re.match(r"^P\d{2,4}[A-Za-z0-9_]*$", (name or "").strip(), re.I))


def audit_conveyor_inventory(run_dir: Path, machine: str) -> dict:
    """Classify every mechanical P-row: all / scoped / rejected+reason."""
    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    word_map = {}
    if _load_eip_adapters:
        try:
            _a, _ip, _m, _t, word_map = _load_eip_adapters(run_dir)
        except Exception:
            word_map = {}

    scoped_tags: set[str] = set()
    if load_from_run:
        try:
            inp = load_from_run(run_dir, processor="1756-L83E")
            scoped_tags = {
                (c.conveyor or "").strip().upper()
                for c in (inp.conveyors or [])
                if (c.conveyor or "").strip()
            }
        except Exception:
            scoped_tags = set()

    all_mech: list[dict] = []
    rejected: list[dict] = []
    accepted: list[dict] = []
    seen: set[str] = set()

    for r in rows:
        typ = _clean(r.get("Type")).upper()
        name = _clean(r.get("IO_Name"))
        if typ not in MECH:
            continue
        # mechanical equipment type row
        if not name:
            rejected.append(
                {
                    "io_name": "",
                    "type": typ,
                    "reason": "invalid_row",
                    "detail": "empty IO_Name",
                    "machine_name": _clean(r.get("Machine_Name")),
                }
            )
            continue
        if not _p_tag_ok(name):
            rejected.append(
                {
                    "io_name": name,
                    "type": typ,
                    "reason": "non_p_tag_mechanical_row",
                    "detail": (
                        "Row Type is in mechanical set (STRAIGHT/CURVE/…) but IO_Name "
                        "is not a P### conveyor identity (e.g. TRIANG device / other)"
                    ),
                    "machine_name": _clean(r.get("Machine_Name")),
                }
            )
            continue
        key = name.upper()
        if key in seen:
            rejected.append(
                {
                    "io_name": name,
                    "type": typ,
                    "reason": "duplicate",
                    "detail": "duplicate mechanical P-tag row",
                    "machine_name": _clean(r.get("Machine_Name")),
                }
            )
            continue
        seen.add(key)

        x, y = _f(r.get("X_cord")), _f(r.get("Y_cord"))
        ang, length, width = _f(r.get("Angle")), _f(r.get("Length")), _f(r.get("Width"))
        rec = {
            "conveyor": name,
            "type": typ,
            "machine_name": _clean(r.get("Machine_Name")),
            "io_address_word": _clean(r.get("IO_Address_Word")),
            "x": x,
            "y": y,
            "angle": ang,
            "length": length,
            "width": width,
            "provenance": "RUN",
        }
        all_mech.append(rec)

        row_mach = _clean(r.get("Machine_Name"))
        # Explicit other controller
        if row_mach and row_mach.upper() not in ("N/A", "INVALID", "NONE", "ALL"):
            if row_machine_matches and not row_machine_matches(row_mach, machine):
                rejected.append(
                    {
                        "io_name": name,
                        "type": typ,
                        "reason": "wrong_controller",
                        "detail": f"Machine_Name={row_mach} != {machine}",
                        "machine_name": row_mach,
                    }
                )
                continue
            if not row_machine_matches and row_mach.upper() != machine.upper():
                rejected.append(
                    {
                        "io_name": name,
                        "type": typ,
                        "reason": "wrong_controller",
                        "detail": f"Machine_Name={row_mach} != {machine}",
                        "machine_name": row_mach,
                    }
                )
                continue

        # Untagged / N/A: Auto Build uses Autogen controller linkage (PE/VFD/IO)
        if key in scoped_tags:
            rec["scope_reason"] = "controller_scoped_via_autogen_io_link"
            accepted.append(rec)
        else:
            rejected.append(
                {
                    "io_name": name,
                    "type": typ,
                    "reason": "missing_io_link_to_controller",
                    "detail": (
                        "Machine_Name empty/N/A and no PE/VFD/IO on this controller "
                        "links to this P-tag (same rule as Autogen load_from_run)"
                    ),
                    "machine_name": row_mach or "N/A",
                    "has_xy": x is not None and y is not None,
                }
            )

    # Also note scoped tags missing from mechanical ASC (shouldn't happen often)
    missing_geom = sorted(scoped_tags - seen)

    reason_counts = Counter(r["reason"] for r in rejected)
    return {
        "generated_at": _ts(),
        "run_dir": str(run_dir),
        "machine": machine,
        "source_of_truth": "RUN/FORTNA/Conveyor.asc only — no reference L5X",
        "all_mechanical_p_tags": len(all_mech),
        "unique_mechanical_p_tags": len(seen),
        "controller_scoped_conveyors": len(accepted),
        "rejected_conveyors": len(rejected),
        "rejection_reason_counts": dict(reason_counts),
        "scoped_tags_missing_mech_row": missing_geom,
        "accepted": accepted,
        "rejected": rejected,
        "note": (
            "Controller scoping matches Autogen: explicit Machine_Name match OR "
            "untagged row linked via this controller's PE/VFD/IO. Plant-wide ASC "
            "often leaves conveyors as Machine_Name=N/A."
        ),
    }


def audit_geometry(run_dir: Path, machine: str, inventory: dict) -> dict:
    """Per imported conveyor: source geom + anchors + assumption status."""
    result = investigate(run_dir, machine, run_dir.parent / "_audit_geom_tmp")
    equipment = result.get("equipment") or []

    assumption = {
        "model": "X/Y = footprint center; Angle = flow direction deg CCW from +X; entry/exit = center ± Length/2 along angle",
        "status": "ASSUMPTION",
        "supported_by_run": False,
        "evidence": [
            "Conveyor.asc provides X_cord, Y_cord, Angle, Length, Width numeric fields.",
            "Conveyor.asc does NOT document whether X/Y is center, infeed corner, or discharge.",
            "Infeed_Tangent / Discharge_Tangent / NoseOver exist but are not used by Auto Build today.",
            "No RUN field named entry_anchor/exit_anchor — anchors are INFERRED_GEOMETRY.",
        ],
        "provenance_for_anchors": "INFERRED_GEOMETRY",
        "provenance_for_source_xy": "RUN",
    }

    rows = []
    for e in equipment:
        rows.append(
            {
                "conveyor": e.get("conveyor"),
                "source_x": e.get("x"),
                "source_y": e.get("y"),
                "source_angle": e.get("angle"),
                "source_length": e.get("length"),
                "source_width": e.get("width"),
                "equipment_type": e.get("equipment_type"),
                "computed_entry_anchor": e.get("entry_anchor"),
                "computed_exit_anchor": e.get("exit_anchor"),
                "geometry_confidence": e.get("confidence"),
                "geometry_issues": e.get("geometry_issues") or [],
                "provenance": {
                    "x": "RUN",
                    "y": "RUN",
                    "angle": "RUN",
                    "length": "RUN",
                    "width": "RUN",
                    "entry_anchor": "INFERRED_GEOMETRY",
                    "exit_anchor": "INFERRED_GEOMETRY",
                },
            }
        )

    return {
        "generated_at": _ts(),
        "machine": machine,
        "anchor_assumption": assumption,
        "imported_conveyor_count": len(rows),
        "conveyors": rows,
        "source_of_truth": "RUN geometry fields only — anchors are labeled ASSUMPTION/INFERRED_GEOMETRY",
    }


def audit_connections(run_dir: Path, machine: str) -> dict:
    """Evidence for each geometric candidate — no P-order, no reference PLC."""
    result = investigate(run_dir, machine, run_dir.parent / "_audit_conn_tmp")
    equipment = {e["conveyor"].upper(): e for e in (result.get("equipment") or [])}
    candidates = result.get("candidates") or []

    evidence = []
    for c in candidates:
        a = equipment.get((c.get("from_conveyor") or "").upper())
        b = equipment.get((c.get("to_conveyor") or "").upper())
        reasons = [
            "mate scored by exit→entry Euclidean distance in RUN drawing units",
            "angle compatibility = |angle_from - angle_to| wrapped to [0,180]",
            "P-tag numerical order NOT used",
            "reference PLC downstream NOT consulted",
        ]
        if c.get("ambiguity"):
            reasons.append(f"ambiguity: {c['ambiguity']}")
        if a and (a.get("equipment_type") or "").upper() in {"CURVE", "TRIANG"}:
            reasons.append("from equipment is non-straight — lower geometric trust")
        if b and (b.get("equipment_type") or "").upper() in {"CURVE", "TRIANG"}:
            reasons.append("to equipment is non-straight — lower geometric trust")

        evidence.append(
            {
                "from": c.get("from_conveyor"),
                "to": c.get("to_conveyor"),
                "exit_to_entry_distance": c.get("exit_to_entry_distance"),
                "angle_compatibility_deg": c.get("angle_delta_deg"),
                "from_equipment_type": (a or {}).get("equipment_type"),
                "to_equipment_type": (b or {}).get("equipment_type"),
                "confidence": c.get("classification"),
                "reason": reasons,
                "method": c.get("method"),
                "provenance": "INFERRED_GEOMETRY",
            }
        )

    # Also list Auto Build threshold effect
    auto_levels = {"CONFIRMED", "HIGH-CONFIDENCE CANDIDATE"}
    auto = [e for e in evidence if e["confidence"] in auto_levels]
    amb = [e for e in evidence if e["confidence"] == "AMBIGUOUS"]

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN geometry only",
        "candidate_count": len(evidence),
        "auto_connect_threshold": "CONFIRMED + HIGH-CONFIDENCE CANDIDATE",
        "would_auto_connect": len(auto),
        "ambiguous": len(amb),
        "candidates": evidence,
    }


def audit_motors(run_dir: Path, machine: str) -> dict:
    """Honest Mtrchain / VFD / contactor audit — RUN only."""
    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    word_map = {}
    if _load_eip_adapters:
        try:
            _a, _ip, _m, _t, word_map = _load_eip_adapters(run_dir)
        except Exception:
            word_map = {}

    motor_rows = []
    vfd_rows_all = []
    vfd_rows_scoped = []
    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        nu = name.upper()
        if nu.startswith("VFD"):
            vfd_rows_all.append(r)
            on = False
            if belongs_to_controller:
                try:
                    on = belongs_to_controller(
                        machine_name=_clean(r.get("Machine_Name")),
                        io_word=str(r.get("IO_Address_Word") or "").strip(),
                        controller=machine,
                        word_map=word_map,
                    )
                except Exception:
                    on = False
            if on:
                vfd_rows_scoped.append(
                    {
                        "io_name": name,
                        "machine_name": _clean(r.get("Machine_Name")),
                        "type": _clean(r.get("Type")),
                        "drive_field": _clean(r.get("Drive")),
                    }
                )
        if _is_motor_row(r):
            on = True
            if belongs_to_controller:
                try:
                    on = belongs_to_controller(
                        machine_name=_clean(r.get("Machine_Name")),
                        io_word=str(r.get("IO_Address_Word") or "").strip(),
                        controller=machine,
                        word_map=word_map,
                    )
                except Exception:
                    on = _clean(r.get("Machine_Name")).upper() in ("", "N/A", machine.upper())
            if on:
                motor_rows.append(
                    {
                        "io_name": name,
                        "type": _clean(r.get("Type")),
                        "drive_field": _clean(r.get("Drive")),
                        "machine_name": _clean(r.get("Machine_Name")),
                        "general_description": _clean(r.get("General_Description")),
                    }
                )

    mtrchain = _load_mtrchain(run_dir)
    # Invert motor → conveyors
    motor_to_convs: dict[str, list[str]] = defaultdict(list)
    for conv, motors in mtrchain.items():
        for m in motors:
            motor_to_convs[m.upper()].append(conv.upper())

    multi = {m: convs for m, convs in motor_to_convs.items() if len(set(convs)) >= 2}

    # What Auto Build currently does: link Mtrchain motors to scoped conveyors;
    # classify VFD if name starts with VFD else CONTACTOR for M*
    linked = []
    for conv, motors in sorted(mtrchain.items()):
        for m in motors:
            dt = "UNKNOWN"
            if m.upper().startswith("VFD"):
                dt = "VFD"
            elif re.match(r"^M\d", m.upper()):
                dt = "CONTACTOR / MOTOR STARTER (name-heuristic — NOT proven by Drive field)"
            linked.append({"conveyor": conv, "motor": m, "auto_build_label": dt})

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN Conveyor.asc + Mtrchain.asc — no reference L5X",
        "findings": {
            "mtrchain_meaning": (
                "Mtrchain.asc maps Motor_Name → Motor_Chained1..N. Chained entries are often "
                "P### conveyors (and sometimes PE tags). This is a Fortna motor-chain / latch "
                "control relationship, not proven physical ownership of a single drive for every "
                "chained conveyor. A motor listing two P-tags (e.g. M114→P114,P112) may be a "
                "control chain / accum group rather than one physical motor driving both belts."
            ),
            "vfd_identity_in_run": (
                f"Conveyor.asc contains {len(vfd_rows_all)} IO_Name VFD* rows plant-wide. "
                f"For controller {machine}, belongs_to_controller matched {len(vfd_rows_scoped)} VFD rows. "
                "If zero, Auto Build reporting VFD=0 for this controller is consistent with RUN "
                "scoping — VFDs may live on other masters (e.g. ORNCCP4/ORNCCP5) or only as "
                "print/OCR artifacts, not as this controller's Conveyor.asc VFD rows."
            ),
            "contactor_label_caveat": (
                "Auto Build currently labels M### as CONTACTOR/MOTOR STARTER when the name is not "
                "VFD*. The Drive column on sampled mechanical/motor rows is often empty. Therefore "
                "contactor classification is a NAME HEURISTIC (provenance DEFAULT/GENERIC_PATTERN), "
                "not a RUN Drive-field confirmation. Prefer UNKNOWN when Drive is empty if stricter "
                "policy is required later."
            ),
        },
        "counts": {
            "motor_rows_scoped": len(motor_rows),
            "vfd_rows_plantwide": len(vfd_rows_all),
            "vfd_rows_controller_scoped": len(vfd_rows_scoped),
            "mtrchain_conveyors_with_motors": len(mtrchain),
            "mtrchain_links": sum(len(v) for v in mtrchain.values()),
            "motors_driving_multiple_p_tags": len(multi),
            "auto_build_linked_pairs": len(linked),
            "auto_build_vfd_labels": sum(1 for x in linked if x["auto_build_label"] == "VFD"),
            "auto_build_contactor_heuristic_labels": sum(
                1 for x in linked if "CONTACTOR" in x["auto_build_label"]
            ),
        },
        "vfd_rows_controller_scoped": vfd_rows_scoped,
        "motors_with_multiple_chained_conveyors_sample": [
            {"motor": m, "conveyors": sorted(set(cs))} for m, cs in list(multi.items())[:20]
        ],
        "linked_pairs_sample": linked[:40],
        "drive_field_populated_on_scoped_motors": sum(
            1 for m in motor_rows if m.get("drive_field")
        ),
    }


def audit_merges(run_dir: Path, machine: str) -> dict:
    """What merge ASC tables contain — RUN only."""
    files = []
    for pattern in (
        f"MergeInputs.asc.{machine}",
        "MergeInputs.asc",
        f"MergeBoss.asc.{machine}",
        "MergeBoss.asc",
        "Merges.asc",
        f"MergeRoute.asc.{machine}",
        "MergeRoute.asc",
        f"ZipperMerge.asc.{machine}",
        "ZipperMerge.asc",
        f"SawMerge.asc.{machine}",
        "SawMerge.asc",
    ):
        p = run_dir / "FORTNA" / pattern
        if p.is_file() and p.stat().st_size > 0:
            files.append(p)

    tables = []
    for p in files:
        headers, rows = read_asc(p)
        usable = []
        for r in rows:
            name = _clean(
                r.get("Name")
                or r.get("MergeBoss")
                or r.get("Merge Table Name")
                or r.get("Route")
            )
            valid = _clean(r.get("Valid")).upper()
            blob = " ".join(str(v) for v in r.values())
            ptags = sorted({x.upper() for x in re.findall(r"P\d+[A-Za-z]?", blob, flags=re.I)})
            pes = sorted(
                {
                    x
                    for x in re.findall(r"(?:EZ)?PE\d+[A-Za-z0-9_]*", blob, flags=re.I)
                }
            )
            if not name and not ptags:
                continue
            if valid in {"N", "NO"} and not ptags:
                continue
            usable.append(
                {
                    "name": name,
                    "valid": valid,
                    "merge_boss": _clean(r.get("MergeBoss")),
                    "merge_route": _clean(r.get("MergeRoute")),
                    "presence": _clean(r.get("Presense") or r.get("Presense_Eye1")),
                    "p_tags_mentioned": ptags,
                    "pe_tags_mentioned": pes,
                    "fields_nonempty": {
                        k: _clean(r.get(k))
                        for k in headers
                        if _clean(r.get(k))
                        and _clean(r.get(k)).upper()
                        not in {"INVALID", "N/A", "N", "0", "0.000"}
                    },
                }
            )
        tables.append(
            {
                "file": p.name,
                "headers": headers,
                "row_count": len(rows),
                "usable_rows": usable,
                "usable_count": len(usable),
            }
        )

    interpretation = {
        "lanes": "Often encoded in Name / MergeRoute strings (e.g. LANE1_P404, LANE2_P138) — not geometry.",
        "common_discharge": (
            "Sometimes implied by MergeBoss name (e.g. MERGE_406_3-1) — heuristic string parse only; "
            "not a reliable discharge conveyor field."
        ),
        "presence_eyes": "Presense / Presense_Eye* fields when populated.",
        "merge_boss": "MergeBoss / Merge Table Name identify logical merge objects.",
        "timing_only": (
            "Many Merges.asc rows are placeholders (Valid=N, INVALID eyes, zero timers) — "
            "timing/config shells rather than physical topology."
        ),
        "why_auto_build_merges_zero": (
            "Auto Build currently detects merges only from geometric inbound count "
            "(≥2 HIGH/CONFIRMED exit→entry mates to same discharge). Merge ASC hints are "
            "exported for audit but not yet consumed to create asMerge. With few "
            "auto-connections and many AMBIGUOUS mates, geometric merge count stays 0."
        ),
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN Merge*.asc tables only — no reference L5X",
        "tables": tables,
        "interpretation": interpretation,
        "auto_build_merges_detected": (
            build_transport_graph(run_dir, machine).get("metrics") or {}
        ).get("merges_detected"),
    }


def write_report(out: Path, inv: dict, geom: dict, conn: dict, motors: dict, merges: dict) -> None:
    lines = [
        "# RUN Auto-Build Audit (evidence only)",
        "",
        f"Generated: `{_ts()}`",
        "",
        "## Source-of-truth firewall",
        "",
        "This audit uses **RUN tables only**. The finished Greensboro L5X was **not** read.",
        "See `docs/SOURCE_OF_TRUTH_POLICY.md`.",
        "",
        "## Why Auto Build reported ~37 / 3 / 20 / 31 / 0",
        "",
        f"- **Conveyors discovered/placed = {inv['controller_scoped_conveyors']}**: "
        f"plant-wide mechanical P-tags ≈ **{inv['unique_mechanical_p_tags']}**, but Auto Build "
        f"only imports controller-scoped belts (same Autogen IO-link rule). "
        f"Rejected ≈ **{inv['rejected_conveyors']}** (see rejection_reason_counts).",
        f"- **Auto connections ≈ {conn['would_auto_connect']}**: only CONFIRMED + HIGH-CONFIDENCE "
        "geometric exit→entry mates are wired.",
        f"- **Ambiguous ≈ {conn['ambiguous']}**: spatially near but multi-candidate / weak angle / "
        "outside high band — flagged, not auto-wired.",
        f"- **Disconnected ≈ many**: conveyors with no HIGH/CONFIRMED outbound or inbound wire.",
        f"- **Merges = {merges.get('auto_build_merges_detected')}**: geometric merge requires ≥2 "
        "auto-inbound mates; merge ASC hints are not yet applied as topology.",
        f"- **Motors linked ≈ {motors['counts']['auto_build_linked_pairs']} / VFD = "
        f"{motors['counts']['auto_build_vfd_labels']}**: Mtrchain supplies links; "
        f"controller-scoped VFD* rows = **{motors['counts']['vfd_rows_controller_scoped']}**; "
        "M### contactor label is a **name heuristic** when Drive field empty.",
        "",
        "## Conveyor inventory",
        "",
        f"| Bucket | Count |",
        f"|---|---:|",
        f"| All mechanical P-tags (unique) | {inv['unique_mechanical_p_tags']} |",
        f"| Controller-scoped (imported) | {inv['controller_scoped_conveyors']} |",
        f"| Rejected | {inv['rejected_conveyors']} |",
        "",
        "Rejection reasons:",
        "",
    ]
    for reason, n in sorted((inv.get("rejection_reason_counts") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"- `{reason}`: {n}")
    lines.extend(
        [
            "",
            "## Geometry assumption",
            "",
            f"**Status: {geom['anchor_assumption']['status']}** — "
            f"{geom['anchor_assumption']['model']}",
            "",
            "Evidence:",
            "",
        ]
    )
    for e in geom["anchor_assumption"]["evidence"]:
        lines.append(f"- {e}")
    lines.extend(
        [
            "",
            "## Connections",
            "",
            f"Candidates: **{conn['candidate_count']}** "
            f"(auto {conn['would_auto_connect']}, ambiguous {conn['ambiguous']})",
            "",
            "See `connection_evidence.json` for per-candidate distance/angle/type/confidence/reason.",
            "",
            "## Motors / drives",
            "",
            motors["findings"]["mtrchain_meaning"],
            "",
            motors["findings"]["vfd_identity_in_run"],
            "",
            motors["findings"]["contactor_label_caveat"],
            "",
            "## Merges",
            "",
            merges["interpretation"]["why_auto_build_merges_zero"],
            "",
            "See `merge_evidence.json` for table contents.",
            "",
            "## Artifacts",
            "",
            "- `conveyor_inventory_audit.json`",
            "- `connection_evidence.json`",
            "- `motor_drive_audit.json`",
            "- `merge_evidence.json`",
            "",
            "No Auto Build algorithm changes in this pass.",
            "",
        ]
    )
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RUN-only Auto Build audit")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", default=str(ROOT / "exports" / "run-geometry" / "audit"))
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Guard: refuse if caller tries to pass a reference L5X path (none accepted)
    inv = audit_conveyor_inventory(run_dir, args.machine)
    geom = audit_geometry(run_dir, args.machine, inv)
    conn = audit_connections(run_dir, args.machine)
    motors = audit_motors(run_dir, args.machine)
    merges = audit_merges(run_dir, args.machine)

    (out / "conveyor_inventory_audit.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")
    # geometry details live alongside inventory for the requested per-conveyor fields
    (out / "geometry_assumption_audit.json").write_text(json.dumps(geom, indent=2), encoding="utf-8")
    (out / "connection_evidence.json").write_text(json.dumps(conn, indent=2), encoding="utf-8")
    (out / "motor_drive_audit.json").write_text(json.dumps(motors, indent=2), encoding="utf-8")
    (out / "merge_evidence.json").write_text(json.dumps(merges, indent=2), encoding="utf-8")
    write_report(out, inv, geom, conn, motors, merges)

    # Fold geometry into conveyor inventory accepted rows for convenience
    by = {c["conveyor"].upper(): c for c in geom.get("conveyors") or []}
    for a in inv.get("accepted") or []:
        g = by.get(a["conveyor"].upper())
        if g:
            a["computed_entry_anchor"] = g.get("computed_entry_anchor")
            a["computed_exit_anchor"] = g.get("computed_exit_anchor")
            a["geometry_confidence"] = g.get("geometry_confidence")
            a["provenance"] = g.get("provenance")
    (out / "conveyor_inventory_audit.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")

    print("RUN AUTO-BUILD AUDIT (RUN-only)")
    print(f"  mechanical P-tags: {inv['unique_mechanical_p_tags']}")
    print(f"  controller-scoped: {inv['controller_scoped_conveyors']}")
    print(f"  rejected: {inv['rejected_conveyors']} {inv['rejection_reason_counts']}")
    print(f"  connection candidates: {conn['candidate_count']} auto={conn['would_auto_connect']} amb={conn['ambiguous']}")
    print(f"  VFD rows on controller: {motors['counts']['vfd_rows_controller_scoped']}")
    print(f"  report: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
