#!/usr/bin/env python3
"""FortnaPlus control model — LogicalSignal / StartStop / JamZone preservation.

Gate D–H production path (architecture-first):
  RUN ASC + mnu DLIST targets + Conveyor catalog classification
  → LogicalSignalModel + StartStopModel + JamZoneModel + FortnaEngineeringGraph
  → workbook.control_build (mergeable canonical slice)

Does NOT:
  - rewrite CP1–CP4 core / frozen Transportation Mtrchain behavior
  - invent physical I/O endpoints for logical records
  - emit hollow Sorter/WCS PLC
  - classify by site names or *_MEM / CR#### name patterns

Type=INVALID on a Conveyor *row* ≠ discard (may be LOGICAL_SIGNAL).
Field value INVALID = ABSENT_REFERENCE (never fabricate a BOOL).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_asc import CONVEYOR_TYPES, read_asc
from fortna_site_model import merge_table_rows

ROOT = Path(__file__).resolve().parents[2]
MNU_RELS = ROOT / "artifacts" / "mnu-relationships.json"

ABSENT_TOKENS = frozenset({"", "INVALID", "N/A", "NONE", "NA", "N", "~"})

# Mechanical / device Conveyor.Type values that are NOT logical-memory placeholders.
PHYSICALISH_TYPES = frozenset(
    {t.upper() for t in CONVEYOR_TYPES}
    | {
        "ZEROPRESSURE",
        "ACCUMULATOR",
        "MDR",
        "MOTOR",
        "PHOTOCELL",
        "PROXPART",
        "BEACON",
        "VFD",
        "SCANNER",
        "TRIANG",
    }
)

# Field → semantic edge role (Jamzones) — meaning from Fortna field purpose, not names.
JAM_FIELD_ROLES = {
    "Latch Bit": "latched_by",
    "Jammed Bit": "jammed_signal",
    "Start Stop Timer": "timed_by",
    "Zone Owner ": "owned_by",
    "Zone Owner": "owned_by",
    "Enable Bit": "enabled_by",
    "Start Button": "start_requested_by",
    "Stop Button": "stop_requested_by",
    "Reset Button": "reset_by",
    "StartStopZone": "belongs_to_startstop_zone",
}

# Schema DLIST targets (from artifacts/mnu-relationships.json forward) — fallback map
# used when JSON artifact is unavailable. Must match SOURCE_PROVEN mnu edges.
JAM_FIELD_TARGETS_FALLBACK = {
    "Latch Bit": "Conveyor",
    "Jammed Bit": "Conveyor",
    "Start Stop Timer": "timemenu",
    "Zone Owner ": "Machine",
    "Zone Owner": "Machine",
    "Enable Bit": "Conveyor",
    "Start Button": "Conveyor",
    "Stop Button": "Conveyor",
    "Reset Button": "Conveyor",
    "StartStopZone": "StartStopZones",
}

MTR_CHAIN_FIELDS = [
    "Motor_Ndx",
    *[f"Motor_Chained{i}" for i in range(1, 11)],
    "Motor_Aux",
    "Enabled",
    "GoUntil",
    "Heater Bit",
]
MTR_TIMER_FIELDS = ["Timer_Name", "RUN Timer_Name"]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip().strip('"')


def _is_absent(v: Any) -> bool:
    return _clean(v).upper() in ABSENT_TOKENS


def _flat_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Unwrap merge_table_rows entries: {row:{fields}, identity, ...} → fields."""
    if not isinstance(entry, dict):
        return {}
    if isinstance(entry.get("row"), dict):
        return dict(entry["row"])
    # Already flat field map (tests / alternate loaders)
    skip = {
        "row",
        "identity",
        "source_table",
        "source_scope",
        "source_row",
        "source_path",
        "provenance",
        "evidence",
        "active_state_hint",
    }
    return {k: v for k, v in entry.items() if k not in skip}


def _load_forward_targets() -> dict[str, dict[str, str]]:
    """menu → {field → targetDefinition} from mnu-relationships forward graph."""
    out: dict[str, dict[str, str]] = {
        "Jamzones": dict(JAM_FIELD_TARGETS_FALLBACK),
        "Mtrchain": {
            "Motor_Ndx": "Conveyor",
            "Timer_Name": "timemenu",
            "Motor_Aux": "Conveyor",
            "Enabled": "Conveyor",
            "GoUntil": "Conveyor",
            "Horn": "horns",
            "Stop Zone": "Jamzones",
            **{f"Motor_Chained{i}": "Conveyor" for i in range(1, 11)},
            "RUN Timer_Name": "timemenu",
            "Heater Bit": "Conveyor",
        },
    }
    if not MNU_RELS.is_file():
        return out
    try:
        data = json.loads(MNU_RELS.read_text(encoding="utf-8"))
    except Exception:
        return out
    fwd = data.get("forward") or {}
    for menu in ("Jamzones", "Mtrchain", "StartStopZones"):
        rows = fwd.get(menu) or []
        if not rows:
            continue
        out.setdefault(menu, {})
        for r in rows:
            fld = _clean(r.get("sourceField"))
            tgt = _clean(r.get("targetDefinition") or r.get("rawReference"))
            if fld and tgt:
                out[menu][fld] = tgt
    return out


def classify_conveyor_row(row: dict[str, Any]) -> dict[str, Any]:
    """Classify a Conveyor-catalog row without name-pattern guessing.

    Returns semanticClass + physicalEndpoint policy.
    """
    name = _clean(row.get("IO_Name") or row.get("Name"))
    if _is_absent(name):
        return {
            "identity": None,
            "semanticClass": "ABSENT_REFERENCE",
            "physicalEndpoint": None,
            "subtype": None,
            "discard": True,
            "reason": "placeholder_identity",
        }

    typ = _clean(row.get("Type")).upper()
    mod = _clean(row.get("IO_Module_Type")).upper()
    word = _clean(row.get("IO_Address_Word"))
    bit = _clean(row.get("IO_Address_Bit"))

    # Explicit absent catalog sentinel row named INVALID
    if name.upper() == "INVALID":
        return {
            "identity": name,
            "semanticClass": "ABSENT_REFERENCE",
            "physicalEndpoint": None,
            "subtype": typ or None,
            "discard": True,
            "reason": "sentinel_identity_INVALID",
            "type": typ,
            "module": mod,
            "word": word or None,
            "bit": bit or None,
        }

    has_addr = bool(word) and word.upper() not in ABSENT_TOKENS

    if typ in PHYSICALISH_TYPES:
        # Device/equipment class — may or may not have Configio endpoint yet
        if typ == "MOTOR":
            cls = "PHYSICAL_EQUIPMENT"
            subtype = "motor"
        elif typ == "PHOTOCELL":
            cls = "PHYSICAL_INPUT"
            subtype = "photoeye"
        elif typ == "PROXPART":
            cls = "PHYSICAL_INPUT"
            subtype = "button_or_prox"
        elif typ in CONVEYOR_TYPES or typ in {"ZEROPRESSURE", "ACCUMULATOR", "MDR", "TRIANG"}:
            cls = "PHYSICAL_EQUIPMENT"
            subtype = typ.lower()
        elif typ == "BEACON":
            cls = "PHYSICAL_OUTPUT"
            subtype = "beacon"
        elif typ == "VFD":
            cls = "PHYSICAL_EQUIPMENT"
            subtype = "vfd"
        else:
            cls = "PHYSICAL_EQUIPMENT"
            subtype = typ.lower()
        return {
            "identity": name,
            "semanticClass": cls,
            "subtype": subtype,
            "physicalEndpoint": "CONFIGIO_CANDIDATE" if has_addr else None,
            "discard": False,
            "type": typ,
            "module": mod,
            "word": word or None,
            "bit": bit or None,
            "provenance": "PROVEN",
        }

    # Type=INVALID (or empty junk type) with real IO_Name:
    # Fortna uses these as named logical/control catalog objects when referenced.
    if typ in {"INVALID", "", "N/A", "NONE", "0"} or not typ:
        return {
            "identity": name,
            "semanticClass": "LOGICAL_SIGNAL",
            "subtype": "conveyor_catalog_logical",
            "physicalEndpoint": None,  # NEVER invent physical I/O
            "discard": False,
            "type": typ or "INVALID",
            "module": mod or None,
            "word": word or None,
            "bit": bit or None,
            "provenance": "PROVEN",
            "note": (
                "Conveyor.Type=INVALID means non-mechanical catalog type — "
                "not 'delete this referenceable object'."
            ),
        }

    return {
        "identity": name,
        "semanticClass": "UNKNOWN",
        "subtype": typ.lower(),
        "physicalEndpoint": "CONFIGIO_CANDIDATE" if has_addr else None,
        "discard": False,
        "type": typ,
        "module": mod,
        "word": word or None,
        "bit": bit or None,
        "provenance": "REVIEW_REQUIRED",
    }


def _ref_slot(
    raw: Any,
    *,
    source_table: str,
    source_field: str,
    target_menu: str | None,
    catalog: dict[str, dict[str, Any]],
    role: str | None = None,
) -> dict[str, Any]:
    val = _clean(raw)
    if _is_absent(val):
        return {
            "raw": val or "INVALID",
            "status": "ABSENT",
            "semanticClass": "ABSENT_REFERENCE",
            "targetMenu": target_menu,
            "targetIdentity": None,
            "role": role,
            "provenance": "PROVEN",
            "sourceTable": source_table,
            "sourceField": source_field,
            "note": "Explicit Fortna absent selection — do not fabricate BOOL",
        }
    target = catalog.get(val) if target_menu == "Conveyor" else None
    if target_menu == "Conveyor" and target:
        return {
            "raw": val,
            "status": "RESOLVED",
            "semanticClass": target.get("semanticClass"),
            "subtype": target.get("subtype"),
            "targetMenu": "Conveyor",
            "targetIdentity": val,
            "physicalEndpoint": target.get("physicalEndpoint"),
            "role": role,
            "provenance": "PROVEN",
            "sourceTable": source_table,
            "sourceField": source_field,
            "type": target.get("type"),
            "word": target.get("word"),
            "bit": target.get("bit"),
        }
    if target_menu and target_menu != "Conveyor":
        # timemenu / Machine / StartStopZones / horns — identity retained; class by menu
        cls_map = {
            "timemenu": "TIMER",
            "Machine": "MACHINE",
            "StartStopZones": "ZONE",
            "Jamzones": "ZONE",
            "horns": "HORN",
        }
        return {
            "raw": val,
            "status": "RESOLVED",
            "semanticClass": cls_map.get(target_menu, "UNKNOWN"),
            "targetMenu": target_menu,
            "targetIdentity": val,
            "physicalEndpoint": None,
            "role": role,
            "provenance": "PROVEN",
            "sourceTable": source_table,
            "sourceField": source_field,
        }
    return {
        "raw": val,
        "status": "UNRESOLVED",
        "semanticClass": "UNKNOWN_REFERENCE",
        "targetMenu": target_menu,
        "targetIdentity": val,
        "physicalEndpoint": None,
        "role": role,
        "provenance": "REVIEW_REQUIRED",
        "sourceTable": source_table,
        "sourceField": source_field,
        "note": "Value present but not found in Conveyor catalog / target index",
    }


def build_conveyor_catalog(run_dir: Path, machine: str) -> dict[str, dict[str, Any]]:
    fortna = Path(run_dir) / "FORTNA"
    merged = merge_table_rows(fortna, "Conveyor.asc", machine)
    rows = merged.get("rows") or []
    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        flat = _flat_row(row)
        cls = classify_conveyor_row(flat)
        ident = cls.get("identity")
        if not ident or cls.get("discard"):
            continue
        catalog[ident] = cls
    return catalog


def decode_startstop_zones(run_dir: Path, machine: str) -> dict[str, Any]:
    fortna = Path(run_dir) / "FORTNA"
    merged = merge_table_rows(fortna, "StartStopZones.asc", machine)
    rows = merged.get("rows") or []
    zones = []
    for row in rows:
        flat = _flat_row(row)
        name = _clean(flat.get("Zone Name"))
        if _is_absent(name):
            continue
        zones.append(
            {
                "name": name,
                "startReqFlag": _clean(flat.get("StartReqFlag")),
                "stopReqFlag": _clean(flat.get("StopReqFlag")),
                "state": _clean(flat.get("State")),
                "wasState": _clean(flat.get("WasState")),
                "startOwnerCtl": _clean(flat.get("StartOwnerCtl")),
                "stopOwnerCtl": _clean(flat.get("StopOwnerCtl")),
                "authority": "PROVEN",
                "sourceTable": "StartStopZones",
                "notes": [
                    "State/WasState are runtime-ish fields persisted in RUN ASC",
                    "OwnerCtl values are configuration strings when not N",
                ],
            }
        )
    return {
        "model": "StartStopModel",
        "version": 1,
        "machine": machine,
        "zone_count": len(zones),
        "zones": zones,
        "provenance": "RUN StartStopZones.asc (+ overlay when present)",
    }


def decode_jam_zones(
    run_dir: Path,
    machine: str,
    catalog: dict[str, dict[str, Any]],
    field_targets: dict[str, dict[str, str]],
) -> dict[str, Any]:
    fortna = Path(run_dir) / "FORTNA"
    merged = merge_table_rows(fortna, "Jamzones.asc", machine)
    rows = merged.get("rows") or []
    jam_targets = field_targets.get("Jamzones") or JAM_FIELD_TARGETS_FALLBACK
    zones = []
    unresolved = 0
    logical_refs = 0
    physical_refs = 0
    absent_refs = 0

    for row in rows:
        flat = _flat_row(row)
        name = _clean(flat.get("Zone Name"))
        if _is_absent(name):
            continue
        refs: dict[str, Any] = {}
        for field, role in JAM_FIELD_ROLES.items():
            # tolerate trailing-space schema variant
            raw = flat.get(field)
            if raw is None and field == "Zone Owner":
                raw = flat.get("Zone Owner ")
            if raw is None and field.endswith(" "):
                raw = flat.get(field.strip())
            tgt_menu = jam_targets.get(field) or jam_targets.get(field.strip())
            slot = _ref_slot(
                raw,
                source_table="Jamzones",
                source_field=field.strip(),
                target_menu=tgt_menu,
                catalog=catalog,
                role=role,
            )
            refs[field.strip()] = slot
            if slot["status"] == "ABSENT":
                absent_refs += 1
            elif slot["status"] == "UNRESOLVED":
                unresolved += 1
            elif slot.get("semanticClass") == "LOGICAL_SIGNAL":
                logical_refs += 1
            elif str(slot.get("semanticClass") or "").startswith("PHYSICAL"):
                physical_refs += 1

        zones.append(
            {
                "name": name,
                "startRequestFlag": _clean(flat.get("Start Request Flag")),
                "stopRequestFlag": _clean(flat.get("Stop Request Flag")),
                "jamEnableDontDelay": _clean(flat.get("JamEnableDontDelay")),
                "references": refs,
                "authority": "PROVEN",
                "sourceTable": "Jamzones",
            }
        )

    return {
        "model": "JamZoneModel",
        "version": 1,
        "machine": machine,
        "zone_count": len(zones),
        "zones": zones,
        "coverage": {
            "unresolved_references": unresolved,
            "absent_references": absent_refs,
            "logical_signal_references": logical_refs,
            "physicalish_references": physical_refs,
        },
        "provenance": "RUN Jamzones.asc + mnu DLIST targets + Conveyor catalog classification",
    }


def build_logical_signal_model(
    catalog: dict[str, dict[str, Any]],
    jam_model: dict[str, Any],
    mtr_rows: list[dict[str, Any]] | None = None,
    field_targets: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Preserve LOGICAL_SIGNAL objects that are referenced OR stand in catalog.

    Referenced-first: any Conveyor identity used by Jamzones/Mtrchain with
    semanticClass=LOGICAL_SIGNAL must survive even if Type=INVALID.
    """
    referenced: set[str] = set()
    for z in jam_model.get("zones") or []:
        for slot in (z.get("references") or {}).values():
            if slot.get("targetMenu") == "Conveyor" and slot.get("targetIdentity"):
                referenced.add(slot["targetIdentity"])

    field_targets = field_targets or {}
    mtr_targets = field_targets.get("Mtrchain") or {}
    mtr_enriched = []
    for row in mtr_rows or []:
        flat = _flat_row(row)
        motor = _clean(flat.get("Motor_Name") or flat.get("Motor_Ndx"))
        entry = {"motorName": motor, "members": []}
        for fld in MTR_CHAIN_FIELDS + MTR_TIMER_FIELDS + ["Horn", "Stop Zone"]:
            if fld not in flat and fld not in mtr_targets:
                continue
            raw = flat.get(fld)
            if raw is None:
                continue
            tgt = mtr_targets.get(fld) or (
                "timemenu" if "Timer" in fld else ("horns" if fld == "Horn" else ("Jamzones" if fld == "Stop Zone" else "Conveyor"))
            )
            slot = _ref_slot(
                raw,
                source_table="Mtrchain",
                source_field=fld,
                target_menu=tgt,
                catalog=catalog,
                role="motor_chain_relationship",
            )
            entry["members"].append(slot)
            if slot.get("targetMenu") == "Conveyor" and slot.get("targetIdentity"):
                referenced.add(slot["targetIdentity"])
        if motor and not _is_absent(motor):
            referenced.add(motor)
        mtr_enriched.append(entry)

    signals = []
    for ident, cls in sorted(catalog.items()):
        if cls.get("semanticClass") != "LOGICAL_SIGNAL":
            continue
        # Preserve all logical catalog rows that are referenced; also keep
        # unreferenced logical rows as REVIEW inventory (not discarded).
        signals.append(
            {
                "name": ident,
                "semanticClass": "LOGICAL_SIGNAL",
                "subtype": cls.get("subtype"),
                "type": cls.get("type"),
                "module": cls.get("module"),
                "word": cls.get("word"),
                "bit": cls.get("bit"),
                "physicalEndpoint": None,
                "referenced": ident in referenced,
                "provenance": "PROVEN",
                "sourceTable": "Conveyor",
            }
        )

    referenced_logical = [s for s in signals if s["referenced"]]
    return {
        "model": "LogicalSignalModel",
        "version": 1,
        "signal_count": len(signals),
        "referenced_count": len(referenced_logical),
        "signals": signals,
        "mtrchain_enriched": mtr_enriched[:200],  # bound size
        "mtrchain_enriched_count": len(mtr_enriched),
        "invariant": (
            "LogicalSignal.physicalEndpoint is always null; "
            "Physical I/O identity is a separate HardwareIOModel concern"
        ),
        "type_invalid_semantics": {
            "field_value_INVALID": "ABSENT_REFERENCE",
            "conveyor_row_Type_INVALID": "may_be_LOGICAL_SIGNAL_if_named",
        },
    }


def build_control_graph(
    startstop: dict[str, Any],
    jam: dict[str, Any],
    logical: dict[str, Any],
) -> dict[str, Any]:
    """Higher-level engineering graph ON TOP OF generic references."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(nid: str, cls: str, **extra: Any) -> None:
        if not nid or _is_absent(nid):
            return
        cur = nodes.get(nid)
        if not cur:
            nodes[nid] = {"id": nid, "semanticClass": cls, **extra}
        else:
            # prefer more specific non-UNKNOWN
            if cur.get("semanticClass") in {None, "UNKNOWN", "UNKNOWN_REFERENCE"} and cls:
                cur["semanticClass"] = cls
            cur.update({k: v for k, v in extra.items() if v is not None})

    for z in startstop.get("zones") or []:
        add_node(z["name"], "ZONE", subtype="StartStopZone", sourceTable="StartStopZones")

    for z in jam.get("zones") or []:
        add_node(z["name"], "ZONE", subtype="JamZone", sourceTable="Jamzones")
        for field, slot in (z.get("references") or {}).items():
            role = slot.get("role") or "references"
            tgt = slot.get("targetIdentity")
            if slot.get("status") == "ABSENT":
                continue
            if not tgt:
                continue
            add_node(
                tgt,
                slot.get("semanticClass") or "UNKNOWN",
                targetMenu=slot.get("targetMenu"),
                physicalEndpoint=slot.get("physicalEndpoint"),
            )
            edges.append(
                {
                    "from": z["name"],
                    "to": tgt,
                    "type": role if role != "references" else "references",
                    "sourceField": field,
                    "provenance": slot.get("provenance") or "PROVEN",
                    "targetClass": slot.get("semanticClass"),
                    "status": slot.get("status"),
                }
            )

    for s in logical.get("signals") or []:
        add_node(
            s["name"],
            "LOGICAL_SIGNAL",
            physicalEndpoint=None,
            referenced=s.get("referenced"),
            word=s.get("word"),
            bit=s.get("bit"),
        )

    return {
        "model": "FortnaEngineeringGraph",
        "version": 1,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "notes": [
            "Semantic edge types only where Fortna field roles prove meaning",
            "Otherwise retain generic 'references'",
            "Does not fork CP3 — consumes resolved selections + catalog classes",
        ],
    }


def build_control_models(run_dir: Path | str, machine: str) -> dict[str, Any]:
    """Full control_build payload for canonical workbook merge."""
    run_dir = Path(run_dir)
    field_targets = _load_forward_targets()
    catalog = build_conveyor_catalog(run_dir, machine)
    startstop = decode_startstop_zones(run_dir, machine)
    jam = decode_jam_zones(run_dir, machine, catalog, field_targets)

    fortna = run_dir / "FORTNA"
    mtr_merged = merge_table_rows(fortna, "Mtrchain.asc", machine)
    mtr_rows = mtr_merged.get("rows") or []
    logical = build_logical_signal_model(catalog, jam, mtr_rows, field_targets)
    graph = build_control_graph(startstop, jam, logical)

    class_counts: dict[str, int] = defaultdict(int)
    for c in catalog.values():
        class_counts[str(c.get("semanticClass"))] += 1

    return {
        "version": 1,
        "source": "control_build",
        "generated_at": _ts(),
        "machine": machine,
        "catalog_class_counts": dict(class_counts),
        "catalog_size": len(catalog),
        "startstop": startstop,
        "jam": jam,
        "logical_signals": logical,
        "control_graph": graph,
        "plc_generation": "NOT_STARTED",
        "invariants": [
            "LogicalSignal.physicalEndpoint is null",
            "Field INVALID remains ABSENT_REFERENCE",
            "Conveyor.Type=INVALID does not discard named referenceable objects",
            "Frozen Transportation Mtrchain topology proofs unchanged",
        ],
    }


def merge_control_into_workbook(disk: dict, mem: dict, control: dict | None = None) -> dict:
    """Canonical merge: control_build is its own slice; never hollow siblings."""
    out = {**disk, **mem}
    out["conveyors"] = (
        disk.get("conveyors")
        if isinstance(disk.get("conveyors"), list) and disk.get("conveyors")
        else mem.get("conveyors") or disk.get("conveyors") or []
    )
    for key in ("safety_build", "sorter_build", "sawtooth_build", "areas"):
        if mem.get(key) is not None:
            out[key] = mem[key]
        elif disk.get(key) is not None:
            out[key] = disk[key]
    if control is not None:
        out["control_build"] = control
    else:
        out["control_build"] = mem.get("control_build") or disk.get("control_build")
    return out


def write_control_reports(model: dict[str, Any], out_dir: Path | str) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    ls = model.get("logical_signals") or {}
    jam = model.get("jam") or {}
    ss = model.get("startstop") or {}
    cg = model.get("control_graph") or {}

    # Compact summary only (full graph can be multi-MB)
    summary = {
        "generated_at": model.get("generated_at"),
        "machine": model.get("machine"),
        "plc_generation": model.get("plc_generation"),
        "catalog_size": model.get("catalog_size"),
        "catalog_class_counts": model.get("catalog_class_counts"),
        "startstop_zone_count": ss.get("zone_count"),
        "startstop_zone_names": [z.get("name") for z in (ss.get("zones") or [])],
        "jam_zone_count": jam.get("zone_count"),
        "jam_coverage": jam.get("coverage"),
        "logical_signal_count": ls.get("signal_count"),
        "logical_referenced_count": ls.get("referenced_count"),
        "logical_referenced_sample": [
            s.get("name") for s in (ls.get("signals") or []) if s.get("referenced")
        ][:40],
        "control_graph_nodes": cg.get("node_count"),
        "control_graph_edges": cg.get("edge_count"),
        "invariants": model.get("invariants"),
    }
    jp = out_dir / "plc5_control_model.json"
    jp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    paths["json"] = str(jp)

    md = out_dir / "plc5_control_model.md"
    lines = [
        "# FortnaPlus Control Model Report",
        "",
        f"**Machine:** `{model.get('machine')}`  ",
        f"**Generated:** `{model.get('generated_at')}`  ",
        f"**PLC generation:** `{model.get('plc_generation')}`",
        "",
        "## Counts",
        "",
        f"- Conveyor catalog classified: **{model.get('catalog_size')}**",
        f"- Class counts: `{json.dumps(model.get('catalog_class_counts'))}`",
        f"- StartStop zones: **{ss.get('zone_count')}**",
        f"- Jam zones: **{jam.get('zone_count')}**",
        f"- Logical signals: **{ls.get('signal_count')}** (referenced **{ls.get('referenced_count')}**)",
        f"- Control graph nodes/edges: **{cg.get('node_count')}** / **{cg.get('edge_count')}**",
        "",
        "## Jam coverage",
        "",
        f"`{json.dumps(jam.get('coverage'))}`",
        "",
        "## Referenced logical sample",
        "",
        ", ".join(summary["logical_referenced_sample"][:20]) or "(none)",
        "",
        "## Invariants",
        "",
    ]
    for inv in model.get("invariants") or []:
        lines.append(f"- {inv}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths["md"] = str(md)
    return paths


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--out", default=str(ROOT / "exports" / "stabilization"))
    args = ap.parse_args()
    model = build_control_models(args.run, args.machine)
    paths = write_control_reports(model, args.out)
    print(json.dumps({"ok": True, "paths": paths, "counts": {
        "startstop": model["startstop"]["zone_count"],
        "jam": model["jam"]["zone_count"],
        "logical": model["logical_signals"]["signal_count"],
        "referenced_logical": model["logical_signals"]["referenced_count"],
    }}, indent=2))
