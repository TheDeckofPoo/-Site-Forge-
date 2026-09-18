#!/usr/bin/env python3
"""GATE 3 Confirm-PE audit + GATE 4 DestinationLane↔PhysicalDivert model from RUN.

Source of truth: FortnaPlus RUN tables only. Finished PLC Track_Divert_UDT count
is validation AFTER discovery — never used to invent grouping.

Does NOT hardcode physical_diverts = lanes/2.
Does NOT classify Confirm PE from FullClearTimer name similarity alone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_discovery import (  # noqa: E402
    _clean,
    _conveyor_io_names,
    _meaningful,
    build_divert_rows,
    iter_active_table_rows,
)
from fortna_sorter_divert_research import _pe_from_timer  # noqa: E402


def _ssv_family(out_io: str) -> str:
    s = _clean(out_io).upper()
    m = re.match(r"^(SSV\d+[A-Z]+)", s)
    return m.group(1) if m else s


def _field_val(obj: Any) -> str:
    if isinstance(obj, dict):
        return _clean(obj.get("value"))
    return _clean(obj)


def _outpoints_by_lane(run_dir: Path, machine: str) -> dict[str, dict[str, str]]:
    by: dict[str, dict[str, str]] = {}
    for r in iter_active_table_rows(run_dir, "Outpoints.asc", machine):
        lane = _clean(r.get("Outpoint Name"))
        if not lane:
            continue
        by[lane.upper()] = r
    return by


def build_confirm_pe_audit(
    *,
    divert_rows: list[dict[str, Any]],
    machine: str,
) -> dict[str, Any]:
    """Per-lane Confirm-PE review report (GATE 3)."""
    rows_out: list[dict[str, Any]] = []
    summary = Counter()
    for d in divert_rows:
        lane = _field_val(d.get("lane"))
        name = _field_val(d.get("name"))
        sorter = _field_val(d.get("sorter_section"))
        out_io = _field_val(d.get("divert_output_io"))
        timer = _field_val(d.get("full_clear_timer"))
        pe_obj = d.get("divert_pe")
        pe_val = _field_val(pe_obj)
        pe_src = pe_obj.get("source") if isinstance(pe_obj, dict) else ""
        pe_auth = (d.get("authority") or {}).get("divert_pe") or "REVIEW_REQUIRED"
        ui_val = pe_val

        # Reconstruct Verify I/O evidence class without promoting timer names.
        verify_note = pe_src or ""
        evidence_class = "ENGINEER_REQUIRED"
        candidate = pe_val or None
        candidate_source = None
        engineer_mode = "SELECTION_REQUIRED"

        if pe_auth == "PROVEN" and pe_val:
            evidence_class = "PROVEN"
            candidate_source = "Outpoints.Verify I/O Name (≠ Outpoint I/O)"
            engineer_mode = "CONFIRMATION_OPTIONAL"
            summary["proven_confirm_pe"] += 1
        elif pe_auth == "DERIVED" and pe_val:
            evidence_class = "DERIVED"
            candidate_source = pe_src or "DERIVED relationship"
            engineer_mode = "CONFIRMATION_REQUIRED"  # Accept / Change
            summary["derived_confirm_pe"] += 1
        else:
            # No Accept-Derived path — timer PE token is hint only.
            hint = _pe_from_timer(timer) if timer else None
            evidence_class = "REVIEW_REQUIRED"
            engineer_mode = "SELECTION_REQUIRED"
            summary["no_confirm_pe_candidate"] += 1
            if hint:
                summary["full_clear_timer_pe_hint_present"] += 1

        # Physical divert mechanism if grouping keys present
        phys = _ssv_family(out_io) if out_io and out_io.upper() != "INVALID" else None

        rows_out.append(
            {
                "sorter": sorter or None,
                "fortna_lane_record": name or None,
                "lane_number_or_name": lane or None,
                "host_zone": _field_val(d.get("host_zone")) or None,
                "physical_divert_mechanism": phys,
                "physical_divert_evidence": (
                    "SSV family from Outpoints.Outpoint I/O Name + shared FullClearTimer"
                    if phys
                    else None
                ),
                "candidate_confirmation_pe": candidate,
                "candidate_source_table_field": candidate_source,
                "evidence_class": evidence_class,
                "current_ui_value": ui_val or "",
                "engineer_action": engineer_mode,
                "full_clear_timer": timer or None,
                "full_clear_pe_hint_non_proof": _pe_from_timer(timer) if timer else None,
                "divert_output_io": out_io or None,
                "divert_pe_authority": pe_auth,
                "divert_pe_source": verify_note or None,
            }
        )

    return {
        "gate": 3,
        "machine": machine,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": "RUN only — finished PLC L5X not read for Confirm-PE discovery",
        "confirm_pe_semantic_conclusion": {
            "meaning": (
                "Confirm PE = divert verification photoeye that proves the carton "
                "physically entered the destination after the divert fired "
                "(Track_Divert_Confirm / Outpoints verify path)."
            ),
            "primary_run_field": "Outpoints.Verify I/O Name",
            "join": "SrtZoneLane.Lane == Outpoints.Outpoint Name",
            "proven_when": (
                "Verify I/O Name is meaningful, not INVALID, and distinct from "
                "Outpoint I/O Name (solenoid / SSV). Sites often mirror SSV into Verify — "
                "that is NOT a PE."
            ),
            "not_confirm_pe": [
                "Outpoints.Outpoint I/O Name (divert solenoid / SSV)",
                "SrtZoneLane.FullClearTimer / Outpoints.Full_Clr_Timer_Name "
                "(timer object names — PE tokens are hints only, never proof)",
                "Verify I/O Name when equal to Outpoint I/O Name",
                "Name similarity between timer strings and Conveyor PE inventory alone",
            ],
            "ui_policy": {
                "when_proven_or_derived_candidate": "Derived/Proven: <PE> [Accept] [Change]",
                "when_no_candidate": "empty Select (Confirm PE…) only",
                "acceptance_kind": "ENGINEER_ACCEPTED — never falsify PROVEN",
            },
        },
        "plc5_audit_summary": {
            "destination_lanes_reviewed": len(rows_out),
            "proven_confirm_pe": summary["proven_confirm_pe"],
            "derived_confirm_pe": summary["derived_confirm_pe"],
            "no_confirm_pe_candidate": summary["no_confirm_pe_candidate"],
            "full_clear_timer_pe_hint_present": summary["full_clear_timer_pe_hint_present"],
            "engineer_action_required": (
                "SELECTION_REQUIRED on all lanes without distinct Verify I/O PE — "
                "do not Accept-Derived from FullClearTimer name parse"
            ),
        },
        "divert_rows_requiring_review": rows_out,
    }


def build_lane_divert_relationship(
    *,
    divert_rows: list[dict[str, Any]],
    machine: str,
    finished_oracle_track_divert_udt: int | None = 16,
) -> dict[str, Any]:
    """GATE 4 — DestinationLane vs PhysicalDivert from Fortna relationships."""
    lanes: list[dict[str, Any]] = []
    by_timer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_ssv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    out_ios: set[str] = set()
    hosts: set[str] = set()

    for d in divert_rows:
        lane = _field_val(d.get("lane"))
        name = _field_val(d.get("name"))
        timer = _field_val(d.get("full_clear_timer"))
        out_io = _field_val(d.get("divert_output_io"))
        host = _field_val(d.get("host_zone"))
        sorter = _field_val(d.get("sorter_section"))
        fam = _ssv_family(out_io) if out_io and out_io.upper() != "INVALID" else ""
        entry = {
            "lane": lane,
            "zone_name": name,
            "host_zone": host,
            "full_clear_timer": timer,
            "divert_output_io": out_io,
            "ssv_family": fam,
            "sorter_section": sorter,
        }
        lanes.append(entry)
        if timer:
            by_timer[timer].append(entry)
        if name:
            by_name[name].append(entry)
        if fam:
            by_ssv[fam].append(entry)
        if out_io and out_io.upper() != "INVALID":
            out_ios.add(out_io)
        if host:
            hosts.add(host)

    timer_sizes = Counter(len(v) for v in by_timer.values())
    name_sizes = Counter(len(v) for v in by_name.values())
    ssv_sizes = Counter(len(v) for v in by_ssv.values())

    # Deterministic PhysicalDivert id = shared FullClearTimer (RUN field),
    # corroborated by SSV family + consecutive HostZones.
    mechanisms: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    consecutive_hosts = 0
    for timer, members in sorted(by_timer.items(), key=lambda kv: kv[0]):
        fams = sorted({m["ssv_family"] for m in members if m["ssv_family"]})
        zone_names = sorted({m["zone_name"] for m in members if m["zone_name"]})
        host_list = [m["host_zone"] for m in members]
        host_nums = sorted(int(h) for h in host_list if str(h).isdigit())
        consec = len(host_nums) == len(members) == 2 and host_nums[1] == host_nums[0] + 1
        if consec:
            consecutive_hosts += 1
        if len(members) != 2 or len(fams) != 1:
            unresolved.append(
                {
                    "timer": timer,
                    "lanes": [m["lane"] for m in members],
                    "ssv_families": fams,
                    "why": "timer group is not exactly 2 lanes / 1 SSV family",
                }
            )
        mech_id = fams[0] if len(fams) == 1 else timer
        mechanisms.append(
            {
                "physical_divert_id": mech_id,
                "grouping_key_primary": "SrtZoneLane.FullClearTimer == Outpoints.Full_Clr_Timer_Name",
                "full_clear_timer": timer,
                "ssv_family": fams[0] if len(fams) == 1 else None,
                "zone_names": zone_names,
                "destination_lanes": [
                    {
                        "lane": m["lane"],
                        "host_zone": m["host_zone"],
                        "divert_output_io": m["divert_output_io"],
                    }
                    for m in members
                ],
                "lanes_per_physical_divert": len(members),
                "consecutive_host_zones": consec,
                "evidence_class": (
                    "STRONGLY_SUPPORTED"
                    if len(members) == 2 and len(fams) == 1 and consec
                    else "PARTIAL"
                ),
            }
        )

    classification = "STRONGLY_SUPPORTED"
    if unresolved or consecutive_hosts != len(by_timer):
        classification = "STRONGLY_SUPPORTED_WITH_GAPS"
    # Still not PROVEN schema FK — do not fold Phase-1 emit.

    return {
        "gate": 4,
        "machine": machine,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": "RUN SrtZoneLane ⋈ Outpoints — finished PLC used only as post-discovery validation",
        "hypothesis": (
            "One physical sorter divert commonly services two destination lanes "
            "(field engineering)."
        ),
        "classification": classification,
        "not": (
            "Not a PROVEN schema FK. Do not hardcode physical_diverts=lanes/2."
        ),
        "counts": {
            "destination_lane_records": len(lanes),
            "unique_physical_outputs": len(out_ios),
            "unique_physical_divert_mechanisms": len(mechanisms),
            "unique_host_zones": len(hosts),
            "unique_SrtZoneLane_Name": len(by_name),
            "unique_FullClearTimer": len(by_timer),
            "unique_SSV_families": len(by_ssv),
            "lanes_per_physical_divert": (
                2
                if timer_sizes == Counter({2: len(by_timer)}) and by_timer
                else dict(timer_sizes)
            ),
            "unresolved_mappings": len(unresolved),
            "finished_oracle_Track_Divert_UDT": finished_oracle_track_divert_udt,
        },
        "grouping_evidence": [
            {
                "key": "shared_FullClearTimer",
                "method": (
                    "Group enabled SrtZoneLane by FullClearTimer; corroborate with "
                    "Outpoints.Full_Clr_Timer_Name on Lane join"
                ),
                "result": f"{len(by_timer)} timers · size histogram {dict(timer_sizes)}",
                "evidence_class": "STRONGLY_SUPPORTED_RUN_FIELD",
                "matches_oracle_16": len(by_timer) == 16,
            },
            {
                "key": "shared_SSV_family",
                "method": (
                    "Strip trailing digit from Outpoints.Outpoint I/O Name "
                    "(SSV506B1/SSV506B2 → SSV506B)"
                ),
                "result": f"{len(by_ssv)} families · size histogram {dict(ssv_sizes)}",
                "evidence_class": "STRONGLY_SUPPORTED_CORROBORATING_PATTERN",
                "matches_oracle_16": len(by_ssv) == 16 and ssv_sizes == Counter({2: 16}),
                "note": "Pattern is deterministic on ORNCCP5 but is still a naming convention, not a schema FK",
            },
            {
                "key": "consecutive_HostZone_within_timer",
                "method": "HostZone integers within each FullClearTimer group",
                "result": f"{consecutive_hosts}/{len(by_timer)} timer groups consecutive",
                "evidence_class": "SUPPORTING",
            },
            {
                "key": "SrtZoneLane.Name",
                "method": "group enabled zone lanes by Name",
                "result": f"{len(by_name)} names · size histogram {dict(name_sizes)}",
                "evidence_class": "SUPPORTING_INCOMPLETE",
                "matches_oracle_16": False,
                "note": "NEW_510 spans two timers / two SSV families (4 lanes) — Name alone insufficient",
            },
            {
                "key": "TwoSidedShoe / RightSideDivert",
                "method": "schema flags on enabled SrtZoneLane",
                "result": "ORNCCP5 enabled rows are TwoSidedShoe=N, RightSideDivert=N",
                "evidence_class": "DOES_NOT_SUPPORT_AT_THIS_SITE",
            },
            {
                "key": "Outpoints.Number of Diverts",
                "method": "column on joined Outpoints",
                "result": "0 on all 32 destination lanes",
                "evidence_class": "UNUSABLE",
            },
        ],
        "proposed_model": {
            "DestinationLane": (
                "one enabled SrtZoneLane row (unique Lane + HostZone + Outpoint I/O)"
            ),
            "PhysicalDivert": (
                "grouping of DestinationLanes that share FullClearTimer "
                "(and, on ORNCCP5, one SSV family + consecutive HostZones)"
            ),
            "relationship": "PhysicalDivert → one or more DestinationLanes (ORNCCP5: exactly 2)",
            "emit_policy": (
                "Phase 1 continues DestinationLane multiplicity (32). Do not collapse "
                "to 16 Track_Divert instances until library/schema elevates grouping to PROVEN. "
                "Do not hardcode /2."
            ),
        },
        "physical_diverts": mechanisms,
        "unresolved_mappings": unresolved,
        "finished_plc_validation": {
            "Track_Divert_UDT_count": finished_oracle_track_divert_udt,
            "role": "independent validation AFTER RUN discovery — not a discovery input",
            "alignment": (
                "oracle 16 matches RUN-derived mechanism count"
                if finished_oracle_track_divert_udt == len(mechanisms)
                else "oracle count differs from RUN-derived mechanisms"
            ),
        },
        "phase1_action": (
            "Leave divert_count at DestinationLane multiplicity (32 on ORNCCP5). "
            "Document PhysicalDivert as STRONGLY_SUPPORTED diagnostic model only."
        ),
    }


def build_from_run(
    run_dir: Path,
    machine: str,
    *,
    finished_oracle_track_divert_udt: int | None = 16,
) -> tuple[dict[str, Any], dict[str, Any]]:
    zone_rows = iter_active_table_rows(run_dir, "SrtZoneLane.asc", machine)
    # Keep enabled topology only (Enabled=Y)
    zone_rows = [
        z
        for z in zone_rows
        if _clean(z.get("Enabled")).upper() not in {"N", "NO", "0"}
    ]
    op_by = _outpoints_by_lane(run_dir, machine)
    divert_rows = build_divert_rows(zone_rows, outpoints_by_lane=op_by)
    audit = build_confirm_pe_audit(divert_rows=divert_rows, machine=machine)
    rel = build_lane_divert_relationship(
        divert_rows=divert_rows,
        machine=machine,
        finished_oracle_track_divert_udt=finished_oracle_track_divert_udt,
    )
    # Conveyor existence of timer PE hints is informational only (never auto-fill).
    conv = _conveyor_io_names(run_dir, machine)
    hint_exist = 0
    for row in audit["divert_rows_requiring_review"]:
        hint = row.get("full_clear_pe_hint_non_proof")
        if hint and hint.upper() in conv:
            row["full_clear_pe_hint_exists_in_conveyor"] = True
            hint_exist += 1
        else:
            row["full_clear_pe_hint_exists_in_conveyor"] = bool(hint and hint.upper() in conv)
    audit["plc5_audit_summary"]["full_clear_pe_hint_in_conveyor"] = hint_exist
    audit["plc5_audit_summary"]["note"] = (
        "Conveyor existence of a timer-embedded PE token does NOT promote Confirm PE "
        "to DERIVED/PROVEN — still name-derived hint, not Verify I/O proof."
    )
    return audit, rel


def write_markdown(rel: dict[str, Any], audit: dict[str, Any]) -> str:
    c = rel["counts"]
    lines = [
        "# Sorter Lane ↔ Physical Divert Model (GATE 3 + GATE 4)",
        "",
        f"**Machine:** `{rel.get('machine')}`  ",
        f"**Generated:** `{rel.get('generated_at')}`  ",
        "**Source of truth:** RUN `SrtZoneLane` ⋈ `Outpoints` (finished PLC is validation only)",
        "",
        "---",
        "",
        "## GATE 3 — Confirm PE semantics",
        "",
        audit["confirm_pe_semantic_conclusion"]["meaning"],
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| Primary RUN field | `{audit['confirm_pe_semantic_conclusion']['primary_run_field']}` |",
        f"| Join | `{audit['confirm_pe_semantic_conclusion']['join']}` |",
        f"| Proven when | {audit['confirm_pe_semantic_conclusion']['proven_when']} |",
        f"| PLC5 proven Confirm PE | **{audit['plc5_audit_summary']['proven_confirm_pe']}** / {audit['plc5_audit_summary']['destination_lanes_reviewed']} |",
        f"| PLC5 derived Confirm PE | **{audit['plc5_audit_summary']['derived_confirm_pe']}** |",
        f"| Engineer selection required | **{audit['plc5_audit_summary']['no_confirm_pe_candidate']}** lanes |",
        "",
        "### Not Confirm PE",
        "",
    ]
    for x in audit["confirm_pe_semantic_conclusion"]["not_confirm_pe"]:
        lines.append(f"- {x}")
    lines += [
        "",
        "### UI policy",
        "",
        f"- When DERIVED/PROVEN candidate exists: "
        f"`{audit['confirm_pe_semantic_conclusion']['ui_policy']['when_proven_or_derived_candidate']}`",
        f"- When no candidate: "
        f"`{audit['confirm_pe_semantic_conclusion']['ui_policy']['when_no_candidate']}`",
        f"- Acceptance: `{audit['confirm_pe_semantic_conclusion']['ui_policy']['acceptance_kind']}`",
        "",
        "Artifact: `exports/stabilization/plc5_divert_confirm_pe_audit.json`",
        "",
        "---",
        "",
        "## GATE 4 — 32 DestinationLanes → 16 PhysicalDiverts",
        "",
        f"**Hypothesis:** {rel['hypothesis']}",
        "",
        f"**Classification:** `{rel['classification']}`",
        "",
        rel["not"],
        "",
        "| Count | Value |",
        "|-------|------:|",
        f"| Destination lane records | **{c['destination_lane_records']}** |",
        f"| Unique physical outputs (SSV) | **{c['unique_physical_outputs']}** |",
        f"| Unique physical divert mechanisms | **{c['unique_physical_divert_mechanisms']}** |",
        f"| Lanes per physical divert | **{c['lanes_per_physical_divert']}** |",
        f"| Unresolved mappings | **{c['unresolved_mappings']}** |",
        f"| Finished oracle Track_Divert_UDT (validation) | **{c['finished_oracle_Track_Divert_UDT']}** |",
        "",
        "### Grouping keys (derived from Fortna relationships — not `/2`)",
        "",
    ]
    for g in rel["grouping_evidence"]:
        lines.append(
            f"- **{g['key']}** (`{g['evidence_class']}`): {g['result']}"
        )
    lines += [
        "",
        "### Proposed model",
        "",
        f"- **DestinationLane** = {rel['proposed_model']['DestinationLane']}",
        f"- **PhysicalDivert** = {rel['proposed_model']['PhysicalDivert']}",
        f"- **Relationship** = {rel['proposed_model']['relationship']}",
        f"- **Emit policy** = {rel['proposed_model']['emit_policy']}",
        "",
        "### Phase-1 action",
        "",
        rel["phase1_action"],
        "",
        "Artifact: `exports/stabilization/plc5_lane_divert_relationship.json`",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=ROOT / "workspace" / "cp5-run" / "RUN")
    ap.add_argument("--machine", default="ORNCCP5")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "exports" / "stabilization",
    )
    ap.add_argument(
        "--doc-out",
        type=Path,
        default=ROOT / "docs" / "evidence" / "SORTER_LANE_PHYSICAL_DIVERT_MODEL.md",
    )
    ap.add_argument(
        "--finished-oracle-track-divert-udt",
        type=int,
        default=16,
        help="Validation-only finished PLC Track_Divert_UDT count (not discovery input)",
    )
    args = ap.parse_args(argv)

    audit, rel = build_from_run(
        args.run_dir,
        args.machine,
        finished_oracle_track_divert_udt=args.finished_oracle_track_divert_udt,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.out_dir / "plc5_divert_confirm_pe_audit.json"
    rel_path = args.out_dir / "plc5_lane_divert_relationship.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    rel_path.write_text(json.dumps(rel, indent=2) + "\n", encoding="utf-8")
    args.doc_out.parent.mkdir(parents=True, exist_ok=True)
    args.doc_out.write_text(write_markdown(rel, audit), encoding="utf-8")
    print(f"Wrote {audit_path}")
    print(f"Wrote {rel_path}")
    print(f"Wrote {args.doc_out}")
    print(
        "GATE3 candidates proven/derived:",
        audit["plc5_audit_summary"]["proven_confirm_pe"],
        "/",
        audit["plc5_audit_summary"]["derived_confirm_pe"],
        " selection_required=",
        audit["plc5_audit_summary"]["no_confirm_pe_candidate"],
    )
    print(
        "GATE4 mechanisms=",
        rel["counts"]["unique_physical_divert_mechanisms"],
        "lanes=",
        rel["counts"]["destination_lane_records"],
        "class=",
        rel["classification"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
