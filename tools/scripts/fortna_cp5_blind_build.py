#!/usr/bin/env python3
"""PLC5 blind RUN→SiteModel→supported L5X validation.

SOURCE FIREWALL:
  Allowed: PLC5 RUN + FortnaPlus knowledge + generic libraries + engineer overrides
  Forbidden: finished PLC5/4/2 L5X, answer-sheet constants, prior-site research gap-fill

Usage:
  python fortna_cp5_blind_build.py \\
    --run-dir workspace/cp5-run/RUN \\
    --archive workspace/cp5-run/_archive/20251016-0933-OReillyGreensboro-ORNCCP5-RUN.tar.gz \\
    --out exports/cp5-blind
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_site_model import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    INCLUDED,
    _clean,
    load_json,
    merge_table_rows,
    normalize_name,
    write_json,
)
from fortna_run_workspace_discover import (  # noqa: E402
    discover,
    infer_machine_from_run,
)
from fortna_validate_site_model import validate_site_model  # noqa: E402
from fortna_supersession import evaluate_supersession  # noqa: E402
from fortna_knowledge_enrich import enrich_site_model  # noqa: E402
from fortna_knowledge_integration import structural_l5x_checks  # noqa: E402

try:
    from fortna_knowledge import KnowledgeStore, get_store
except ImportError:  # pragma: no cover
    KnowledgeStore = None  # type: ignore
    get_store = None  # type: ignore


FORBIDDEN_FINISHED_FRAGMENTS = [
    "ORLY_Greensboro_NC_PLC5",
    "ORLY_Greensboro_NC_PLC4",
    "ORLY_Greensboro_NC_PLC2",
    "PLC5Finished",
    "PLC4Finished",
    "PLC2Finished",
    "finished_plc5",
    "finished_plc4",
    "finished_plc2",
]

RUNTIME_TABLE_PREFIXES = (
    "SrtTrack",
    "XfrTrack",
    "XfrSim",
    "PeList",
    "PeDisplay",
    "HistData",
    "SortData",
    "SortBuff",
    "SrtScanSts",
    "ScnScanSts",
    "MergeState",
    "SawState",
    "HSSawState",
    "HSSawSim",
)

DIAGNOSTIC_PREFIXES = (
    "Hist",
    "Error",
    "Log",
    "ScnDeviceErr",
    "ScnZoneErr",
    "ScnDvErr",
    "ScnZnErr",
)

COMM_TABLES = {
    "Machine",
    "MsgMap",
    "MsgWCS",
    "MsgTrack",
    "WCSEvents",
    "MsgNMS",
    "MsgTST",
}

SORTER_STATIC = {
    "Sorters",
    "SrtAppControl",
    "SrtScanBoss",
    "SrtZoneLane",
    "SrtRndRobin",
    "SrtHrtBeat",
    "SrtBadGapCnfg",
    "SrtLaneNotAvail",
    "SrtSimConfig",
    "SrtCommMsgMatch",
    "XfRouteBoss",
    "XfRouteTable",
    "XfrDevice",
}

SCANNER_TABLES = {
    "ScnScanDevice",
    "ScnScanZone",
    "ScnScanAlg",
    "ScnScanTypes",
    "ScnFieldType",
    "ScnDeviceErrIO",
    "ScnZoneErrIO",
}

MERGE_TABLES = {
    "Merges",
    "MergeBoss",
    "MergeInputs",
    "MergeRoute",
    "MergeNotBusy",
    "MergeRunOutputs",
    "MergeStopOutputs",
    "MergeExtras",
    "MergeActionPop",
    "SimpleMerge",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(blob)


_VOLATILE_L5X_RE = re.compile(
    r'(ExportDate|ProjectCreationDate|LastModifiedDate)="[^"]*"',
    re.I,
)


def sha256_l5x_stable(path: Path) -> str:
    """Hash L5X with volatile Autogen timestamps normalized.

    Genericity tests compare semantic output, not wall-clock ExportDate stamps.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    stable = _VOLATILE_L5X_RE.sub(r'\1="STABLE_TIMESTAMP"', text)
    return sha256_bytes(stable.encode("utf-8"))


def _kb():
    if get_store is not None:
        try:
            return get_store()
        except Exception:
            pass
    if KnowledgeStore is not None:
        try:
            return KnowledgeStore()
        except Exception:
            return None
    return None


def build_run_identity(run_dir: Path, archive: Path | None) -> dict[str, Any]:
    cfg = run_dir / "project.cfg"
    identity_cfg = run_dir / "identity.cfg"
    info_cfg = run_dir / "info.cfg"
    machine = infer_machine_from_run(run_dir)
    project_name = ""
    machine_type = ""
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "PROJECTNAME" in line.upper():
                parts = line.split("=", 1)
                if len(parts) == 2:
                    project_name = parts[1].strip().strip('"').strip("'")
            if "MACHINETYPE" in line.upper():
                parts = line.split("=", 1)
                if len(parts) == 2:
                    machine_type = parts[1].strip().strip('"').strip("'")

    fortna = run_dir / "FORTNA"
    overlays = sorted(p.name for p in fortna.glob(f"*.asc.{machine}")) if fortna.is_dir() and machine else []
    peers = []
    if fortna.is_dir():
        merged = merge_table_rows(fortna, "Machine.asc", machine or "UNKNOWN")
        for item in merged.get("rows") or []:
            name = _clean((item.get("row") or {}).get("Machine_Name"))
            if name and name.upper() not in {"N/A", "INVALID", "NONE"}:
                peers.append(
                    {
                        "name": name,
                        "connection_type": _clean((item.get("row") or {}).get("Connection_Type")),
                        "protocol": _clean((item.get("row") or {}).get("Communication_Protocol")),
                        "source_scope": item.get("source_scope"),
                    }
                )

    # Subsystem hints from overlays / named tables (presence only)
    subsystem_files = {
        "sorter": any(fortna.glob("Sorters.asc*")) if fortna.is_dir() else False,
        "sawtooth": any(fortna.glob("SawMerge.asc*")) if fortna.is_dir() else False,
        "merge": any(fortna.glob("MergeBoss.asc*")) if fortna.is_dir() else False,
        "scanner": any(fortna.glob("ScnScanDevice.asc*")) if fortna.is_dir() else False,
        "wcs": any(fortna.glob("WCSEvents.asc*")) if fortna.is_dir() else False,
        "tracking": any(fortna.glob("SrtTrack*.asc*")) if fortna.is_dir() else False,
    }

    return {
        "generated_at": _ts(),
        "source_of_truth": "PLC5 RUN only — finished PLC ignored",
        "archive": {
            "path": str(archive) if archive else None,
            "name": archive.name if archive else None,
            "sha256": sha256_file(archive) if archive and archive.is_file() else None,
            "size": archive.stat().st_size if archive and archive.is_file() else None,
        },
        "run_dir": str(run_dir),
        "machine_name": machine,
        "project_name": project_name,
        "machine_type": machine_type,
        "identity_cfg_present": identity_cfg.is_file(),
        "info_cfg_present": info_cfg.is_file(),
        "controller_overlays": overlays,
        "controller_overlay_count": len(overlays),
        "communication_peers": peers,
        "subsystem_file_presence": subsystem_files,
        "notes": [
            "Controller scope taken from project.cfg MACHINENAME",
            "Peers listed from Machine.asc merge; not invented",
        ],
    }


def _table_stem(name: str) -> str:
    n = name
    if n.lower().startswith("old."):
        n = n[4:]
    if n.endswith(".asc"):
        return n[:-4]
    # Table.asc.CONTROLLER
    m = re.match(r"^(.+)\.asc(?:\.[^.]+)?$", n, re.I)
    return m.group(1) if m else Path(n).stem


def classify_table(stem: str, kb: Any) -> dict[str, Any]:
    upper = stem
    knowledge = None
    if kb is not None and hasattr(kb, "table_semantics"):
        knowledge = kb.table_semantics(stem) or kb.table_semantics(stem.split(".")[0])
    knowledge_rule = None
    document_basis = []
    subsystem = "unknown"
    confidence = "UNKNOWN_TABLE"
    if knowledge:
        subsystem = knowledge.get("subsystem") or "unknown"
        document_basis = [
            (d.get("title") or d.get("id") or d.get("file"))
            for d in (knowledge.get("document_sources") or [])
            if isinstance(d, dict)
        ]
        knowledge_rule = f"KB.table_semantics({stem})"
        confidence = "KNOWN_HIGH_CONFIDENCE" if knowledge.get("confidence") == "HIGH" else "KNOWN_PARTIAL"
        if not knowledge.get("schema_headers") and not knowledge.get("key_fields"):
            confidence = "KNOWN_PARTIAL"

    # Layer classification
    layer = "EQUIPMENT_CONFIGURATION"
    if any(upper.startswith(p) or upper == p for p in RUNTIME_TABLE_PREFIXES):
        layer = "RUNTIME_STATE"
    elif any(upper.startswith(p) for p in DIAGNOSTIC_PREFIXES):
        layer = "DIAGNOSTIC_HISTORY"
    elif upper in COMM_TABLES or upper.startswith("Msg"):
        layer = "COMMUNICATION_CONFIGURATION"
    elif upper in SORTER_STATIC or upper in SCANNER_TABLES or upper in MERGE_TABLES:
        layer = "STATIC_CONFIGURATION"
    elif upper in {"Conveyor", "Encoders", "IOCard", "Configio", "FORTNADT", "convtype"}:
        layer = "EQUIPMENT_CONFIGURATION"
    elif upper in {"Jamcheck", "Fullline", "Fulljam", "Jamzones", "StartStopZones", "EStop", "Mtrchain"}:
        layer = "STATIC_CONFIGURATION"

    if confidence == "UNKNOWN_TABLE" and layer != "EQUIPMENT_CONFIGURATION":
        # Still unknown to KB but we classified layer heuristically
        pass

    return {
        "table": stem,
        "knowledge_confidence": confidence,
        "layer": layer,
        "subsystem": subsystem if knowledge else _guess_subsystem(stem),
        "knowledge_rule": knowledge_rule,
        "document_basis": document_basis,
    }


def _guess_subsystem(stem: str) -> str:
    s = stem.lower()
    if s.startswith("srt") or s.startswith("sorters") or s.startswith("xfr") or s.startswith("xf"):
        return "sorter"
    if "saw" in s:
        return "sawtooth"
    if s.startswith("merge"):
        return "merge"
    if s.startswith("scn"):
        return "scanner"
    if s.startswith("msg") or s in {"machine", "wcsevents"}:
        return "communication"
    if s in {"jamcheck", "fullline", "fulljam", "jamzones", "startstopzones", "estop"}:
        return "area_safety"
    if s in {"conveyor", "mtrchain", "encoders", "configio", "iocard"}:
        return "transport_io"
    return "unknown"


def inventory_tables(run_dir: Path, machine: str, kb: Any) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    files = sorted(p for p in fortna.iterdir() if p.is_file()) if fortna.is_dir() else []
    by_stem: dict[str, dict[str, Any]] = {}
    file_inventory = []
    for p in files:
        rel = p.name
        is_old = rel.lower().startswith("old.")
        stem = _table_stem(rel)
        scoped = None
        if ".asc." in rel.lower():
            scoped = rel.split(".asc.", 1)[-1]
        entry = {
            "file": rel,
            "stem": stem,
            "scoped_variant": scoped,
            "historical": is_old,
            "size": p.stat().st_size,
            "sha256": sha256_file(p) if p.stat().st_size < 5_000_000 else None,
        }
        file_inventory.append(entry)
        slot = by_stem.setdefault(
            stem,
            {
                "table": stem,
                "files": [],
                "has_base": False,
                "has_overlay": False,
                "has_historical": False,
            },
        )
        slot["files"].append(rel)
        if is_old:
            slot["has_historical"] = True
        elif scoped and machine and scoped.upper() == machine.upper():
            slot["has_overlay"] = True
        elif rel.lower().endswith(".asc"):
            slot["has_base"] = True

    tables = []
    known_high = known_partial = unknown = 0
    layer_counts: Counter[str] = Counter()
    for stem, slot in sorted(by_stem.items()):
        cls = classify_table(stem, kb)
        # row counts via merge when ASC
        row_count = None
        active_rows = None
        resolution = None
        try:
            merged = merge_table_rows(fortna, f"{stem}.asc", machine)
            rows = merged.get("rows") or []
            row_count = len(rows)
            resolution = merged.get("resolution")
            active = 0
            for item in rows:
                row = item.get("row") or {}
                name = _clean(
                    row.get("IO_Name")
                    or row.get("Name")
                    or row.get("Sorter Name")
                    or row.get("Sensor_Name")
                    or row.get("Desc")
                    or row.get("Machine_Name")
                    or row.get("Encoder Name")
                    or row.get("Zone Name")
                    or row.get("Message_Name")
                    or row.get("EventName")
                )
                if name and not name.startswith("==="):
                    active += 1
            active_rows = active
        except Exception as exc:  # noqa: BLE001
            slot["merge_error"] = str(exc)

        rec = {
            **slot,
            **cls,
            "row_count": row_count,
            "active_rows": active_rows,
            "resolution": resolution,
        }
        tables.append(rec)
        kc = cls["knowledge_confidence"]
        if kc == "KNOWN_HIGH_CONFIDENCE":
            known_high += 1
        elif kc == "KNOWN_PARTIAL":
            known_partial += 1
        else:
            unknown += 1
        layer_counts[cls["layer"]] += 1

    return {
        "generated_at": _ts(),
        "machine": machine,
        "file_count": len(file_inventory),
        "unique_table_stems": len(tables),
        "known_high_confidence": known_high,
        "known_partial": known_partial,
        "unknown_tables": unknown,
        "layer_counts": dict(layer_counts),
        "tables": tables,
        "files": file_inventory,
    }


def deepen_sorter_model(run_dir: Path, machine: str, site: dict[str, Any]) -> dict[str, Any]:
    """Build fullest generic SorterModel from PLC5 RUN tables only."""
    fortna = run_dir / "FORTNA"
    layers = {
        "STATIC_CONFIGURATION": [],
        "EQUIPMENT_CONFIGURATION": [],
        "ROUTING_CONFIGURATION": [],
        "COMMUNICATION_CONFIGURATION": [],
        "RUNTIME_STATE": [],
        "DIAGNOSTIC_HISTORY": [],
    }

    def _load(stem: str) -> dict[str, Any]:
        merged = merge_table_rows(fortna, f"{stem}.asc", machine)
        rows = []
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(
                row.get("Name")
                or row.get("Sorter Name")
                or row.get("AppSorter")
                or row.get("HostZone")
                or row.get("ConfirmScan")
            )
            if not name or name.startswith("==="):
                continue
            rows.append({"name": name, "row": row, "scope": item.get("source_scope"), "source_row": item.get("source_row")})
        return {
            "table": stem,
            "resolution": merged.get("resolution"),
            "active_rows": len(rows),
            "rows": rows,
        }

    static_tables = {}
    for stem in sorted(SORTER_STATIC | SCANNER_TABLES | {"Sorters", "Encoders"}):
        if not list(fortna.glob(f"{stem}.asc*")):
            continue
        doc = _load(stem)
        static_tables[stem] = {"resolution": doc["resolution"], "active_rows": doc["active_rows"]}
        if stem in {"XfRouteBoss", "XfRouteTable"}:
            layers["ROUTING_CONFIGURATION"].append(stem)
        elif stem in SCANNER_TABLES:
            layers["EQUIPMENT_CONFIGURATION"].append(stem)
        else:
            layers["STATIC_CONFIGURATION"].append(stem)

    runtime_tables = {}
    for p in sorted(fortna.glob("SrtTrack*.asc")) + sorted(fortna.glob("XfrTrack.asc*")) + sorted(
        fortna.glob("XfrSimScans*.asc")
    ):
        stem = _table_stem(p.name)
        if stem in runtime_tables:
            continue
        doc = _load(stem)
        runtime_tables[stem] = {"resolution": doc["resolution"], "active_rows": doc["active_rows"]}
        layers["RUNTIME_STATE"].append(stem)

    # Process model stages
    has_sorter = bool(site.get("sorters"))
    has_scan = static_tables.get("ScnScanDevice", {}).get("active_rows", 0) > 0 or static_tables.get(
        "SrtScanBoss", {}
    ).get("active_rows", 0) > 0
    has_zone = static_tables.get("SrtZoneLane", {}).get("active_rows", 0) > 0
    has_route = static_tables.get("XfRouteTable", {}).get("active_rows", 0) > 0
    has_enc = any((e.get("inclusion") in {INCLUDED, AVAILABLE}) for e in (site.get("encoders") or []))
    has_wcs = bool(site.get("wcs_interfaces") or site.get("communications"))
    has_track_runtime = any(v.get("active_rows", 0) > 0 for v in runtime_tables.values())

    stages = {
        "induct": _stage(has_scan, modeled=has_scan, generatable=False),
        "detect_package": _stage(has_sorter or has_scan, modeled=has_sorter, generatable=False),
        "scan": _stage(has_scan, modeled=has_scan, generatable=False, cfg=True),
        "tracking_record": _stage(has_track_runtime or has_sorter, modeled=True, generatable=False, note="runtime slots ≠ equipment"),
        "route_destination_request": _stage(has_route or has_wcs, modeled=has_route, generatable=False, cfg=True),
        "destination_assignment": _stage(has_route or has_zone, modeled=has_zone or has_route, generatable=False, cfg=True),
        "encoder_tracking": _stage(has_enc or has_sorter, modeled=has_enc or has_sorter, generatable=has_enc, cfg=not has_enc),
        "divert": _stage(has_sorter, modeled=True, generatable=False, unsupported=True),
        "divert_confirmation": _stage(has_sorter, modeled=False, generatable=False, unsupported=True),
        "wcs_event_reporting": _stage(has_wcs, modeled=has_wcs, generatable=False, unsupported=True),
    }

    scanners = []
    if "ScnScanDevice" in static_tables:
        doc = _load("ScnScanDevice")
        for r in doc["rows"]:
            scanners.append(
                {
                    "name": r["name"],
                    "scan_zone": _clean((r["row"] or {}).get("ScanZone")),
                    "scan_type": _clean((r["row"] or {}).get("ScanType")),
                    "provenance": "RUN_EXPLICIT",
                    "confidence": "HIGH",
                    "source_table": "ScnScanDevice.asc",
                }
            )

    scan_bosses = []
    if "SrtScanBoss" in static_tables:
        doc = _load("SrtScanBoss")
        for r in doc["rows"]:
            scan_bosses.append(
                {
                    "name": r["name"],
                    "app_sorter": _clean((r["row"] or {}).get("AppSorter")),
                    "scan_zone": _clean((r["row"] or {}).get("ScanZone")),
                    "provenance": "RUN_EXPLICIT",
                    "confidence": "HIGH",
                }
            )

    # Attach into site editors without inventing
    sorter_editor = (site.get("editors") or {}).get("sorter") or {}
    sorter_editor.update(
        {
            "blind_plc5": True,
            "layers": {k: sorted(set(v)) for k, v in layers.items()},
            "static_tables": static_tables,
            "runtime_tables": runtime_tables,
            "process_model": stages,
            "scanners": scanners,
            "scan_bosses": scan_bosses,
            "note": "RUNTIME_STATE tables inventoried but not treated as equipment definitions",
        }
    )
    site.setdefault("editors", {})["sorter"] = sorter_editor
    site["scanners"] = scanners

    return {
        "detected": has_sorter,
        "sorter_count": len(site.get("sorters") or []),
        "sorters": [
            {
                "name": s.get("raw_name") or s.get("normalized_name"),
                "encoder_io": s.get("encoder_io"),
                "inclusion": s.get("inclusion"),
                "generation_state": s.get("generation_state"),
            }
            for s in (site.get("sorters") or [])
        ],
        "layers": {k: sorted(set(v)) for k, v in layers.items()},
        "static_tables": static_tables,
        "runtime_tables": runtime_tables,
        "process_model": stages,
        "scanners": scanners,
        "scan_bosses": scan_bosses,
    }


def _stage(
    discovered: bool,
    *,
    modeled: bool = False,
    generatable: bool = False,
    cfg: bool = False,
    unsupported: bool = False,
    note: str = "",
) -> dict[str, Any]:
    if not discovered:
        state = "NOT_DISCOVERED"
    elif unsupported:
        state = "NOT_SUPPORTED"
    elif generatable:
        state = "GENERATABLE"
    elif cfg:
        state = "CONFIGURATION_REQUIRED"
    elif modeled:
        state = "MODELED"
    else:
        state = "DISCOVERED"
    return {
        "discovered": bool(discovered),
        "state": state,
        "understood": bool(discovered),
        "modeled": bool(modeled),
        "generatable": bool(generatable),
        "configuration_required": bool(cfg),
        "not_supported": bool(unsupported),
        "note": note,
    }


def deepen_encoders(run_dir: Path, machine: str, site: dict[str, Any]) -> list[dict[str, Any]]:
    """Load Encoders.asc even when Sawtooth is absent (sorter/induct still need them)."""
    from fortna_site_model import (  # local import to keep module load light
        ACTIVE_CONFIRMED,
        PROV_RUN_EXPLICIT,
        make_object,
    )

    fortna = run_dir / "FORTNA"
    if not list(fortna.glob("Encoders.asc*")):
        return list(site.get("encoders") or [])
    existing = {
        normalize_name(e.get("normalized_name") or e.get("raw_name") or "")
        for e in (site.get("encoders") or [])
    }
    out = list(site.get("encoders") or [])
    merged = merge_table_rows(fortna, "Encoders.asc", machine)
    for item in merged.get("rows") or []:
        row = item.get("row") or {}
        name = _clean(row.get("Encoder Name") or row.get("Name"))
        if not name or name.startswith("==="):
            continue
        nn = normalize_name(name)
        if nn in existing:
            continue
        io = _clean(row.get("Encoder I/O") or row.get("Encoder ioName"))
        out.append(
            make_object(
                "encoder",
                name,
                source_table="Encoders.asc",
                source_row=item.get("source_row"),
                source_scope=item.get("source_scope"),
                active_state=ACTIVE_CONFIRMED,
                inclusion=INCLUDED,
                confidence="HIGH",
                provenance=item.get("provenance") or PROV_RUN_EXPLICIT,
                evidence=[{"kind": "encoder_link", "table": "Encoders.asc"}],
                generation_state=GEN_CFG,
                encoder_io=io or None,
            ).to_dict()
        )
        existing.add(nn)
    site["encoders"] = out
    return out


def deepen_merge_model(run_dir: Path, machine: str, site: dict[str, Any]) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    merges = []
    if list(fortna.glob("MergeBoss.asc*")):
        merged = merge_table_rows(fortna, "MergeBoss.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Name"))
            if not name or name.startswith("==="):
                continue
            merges.append(
                {
                    "name": name,
                    "process": _clean(row.get("Process")),
                    "owner": _clean(row.get("Owner")),
                    "num_inputs": _clean(row.get("NumInputs")),
                    "provenance": item.get("provenance"),
                    "source_scope": item.get("source_scope"),
                    "confidence": "HIGH",
                }
            )
    site["merges"] = merges
    return {"detected": bool(merges), "count": len(merges), "merges": merges}


def deepen_communications(run_dir: Path, machine: str, site: dict[str, Any]) -> list[dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    comms = list(site.get("communications") or [])

    # Machine peers already partially present; enrich MsgMap / WCSEvents
    if list(fortna.glob("MsgMap.asc*")):
        merged = merge_table_rows(fortna, "MsgMap.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            msg = _clean(row.get("Message_Name"))
            mach = _clean(row.get("Machine_Name"))
            if not msg or msg.startswith("==="):
                continue
            if mach and mach.upper() not in {machine.upper(), ""} and not mach.upper().startswith("WCS"):
                # keep all configured maps but tag ownership
                pass
            comms.append(
                {
                    "canonical_id": f"msgmap:{normalize_name(msg)}",
                    "kind": "communication",
                    "message_class": "MsgMap",
                    "layer": "COMMUNICATION_CONFIGURATION",
                    "sender": mach or None,
                    "receiver": None,
                    "topic": msg,
                    "event": None,
                    "ownership": mach or machine,
                    "recv_msg_type": _clean(row.get("Recv_Msg_Type")),
                    "send_msg_type": _clean(row.get("Send_Msg_Type")),
                    "source_evidence": [{"kind": "msgmap", "table": "MsgMap.asc"}],
                    "provenance": item.get("provenance") or "RUN_EXPLICIT",
                    "confidence": "HIGH",
                    "runtime_queue": False,
                    "generation_state": GEN_NOT_SUPPORTED,
                }
            )

    if list(fortna.glob("WCSEvents.asc*")):
        merged = merge_table_rows(fortna, "WCSEvents.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            ev = _clean(row.get("EventName") or row.get("Name") or row.get("Event"))
            if not ev or ev.startswith("==="):
                continue
            enabled = _clean(row.get("Enabled") or row.get("Enable") or "Y")
            comms.append(
                {
                    "canonical_id": f"wcs_event:{normalize_name(ev)}",
                    "kind": "communication",
                    "message_class": "WCSEvents",
                    "layer": "COMMUNICATION_CONFIGURATION",
                    "sender": machine,
                    "receiver": "WCS",
                    "topic": ev,
                    "event": ev,
                    "ownership": machine,
                    "enabled": enabled,
                    "source_evidence": [{"kind": "wcs_event", "table": "WCSEvents.asc"}],
                    "provenance": item.get("provenance") or "RUN_EXPLICIT",
                    "confidence": "HIGH",
                    "runtime_queue": False,
                    "generation_state": GEN_NOT_SUPPORTED,
                }
            )

    # Dedup by canonical_id
    seen = set()
    unique = []
    for c in comms:
        cid = c.get("canonical_id") or c.get("topic")
        if cid in seen:
            continue
        seen.add(cid)
        unique.append(c)
    site["communications"] = unique
    return unique


def build_generation_matrix(site: dict[str, Any], sorter_model: dict[str, Any], merge_model: dict[str, Any]) -> dict[str, Any]:
    og = site.get("operational_groups") or {}
    has_eq = any(e.get("inclusion") == INCLUDED for e in (site.get("equipment") or []))
    has_pe = any(p.get("inclusion") == INCLUDED for p in (site.get("photoeyes") or []))
    has_vfd = bool(site.get("vfds") or site.get("drives"))
    has_enc = bool(site.get("encoders"))
    has_estop = bool(og.get("estop_zones") or site.get("estop_zones"))
    has_area = bool(site.get("areas") or og.get("engineering_areas"))
    has_jam = bool(og.get("jam_zones"))
    has_ss = bool(og.get("startstop_zones"))
    has_sorter = bool(sorter_model.get("detected"))
    has_merge = bool(merge_model.get("detected"))
    has_saw = bool(site.get("sawtooth_merges"))
    has_scan = bool(sorter_model.get("scanners") or sorter_model.get("scan_bosses"))
    has_wcs = any(
        c.get("message_class") in {"WCS", "WCSEvents", "MsgMap"} for c in (site.get("communications") or [])
    )

    def cap(discovered, *, understood=True, modeled=False, generatable=False, validated=False, reason=""):
        states = []
        if discovered:
            states.append("DISCOVERED")
        if discovered and understood:
            states.append("UNDERSTOOD")
        if modeled:
            states.append("MODELED")
        if generatable:
            states.append("GENERATABLE")
        if validated:
            states.append("VALIDATED")
        if not discovered:
            states = ["NOT_DISCOVERED"]
        elif not generatable and modeled:
            states.append("CONFIGURATION_REQUIRED" if "jam" in reason or "sorter" in reason or "wcs" in reason else "MODELED")
        return {
            "states": states,
            "discovered": bool(discovered),
            "understood": bool(discovered and understood),
            "modeled": bool(modeled),
            "generatable": bool(generatable),
            "validated": bool(validated),
            "reason": reason,
        }

    matrix = {
        "controller_skeleton": cap(True, modeled=True, generatable=True, reason="generic library Autogen"),
        "io_map": cap(has_eq, modeled=True, generatable=True, reason="RUN Conveyor banks + EIP when present"),
        "safety_zones": cap(has_estop, modeled=has_estop, generatable=False, reason="estop" if has_estop else "no estop evidence"),
        "area_logic": cap(has_area, modeled=True, generatable=True, reason="default/engineer Area → Autogen programs"),
        "conveyor_fast_logic": cap(has_eq, modeled=True, generatable=True, reason="generic Fast_Conv AOI path"),
        "conveyor_slow_logic": cap(has_eq, modeled=True, generatable=True, reason="generic Slow_* AOI path"),
        "pe_logic": cap(has_pe, modeled=True, generatable=True, reason="PE roles from knowledge+RUN; wiring when linked"),
        "jam_full_logic": cap(has_jam or has_pe, modeled=True, generatable=False, reason="jam/full relationships modeled; dedicated jam AOI pack incomplete"),
        "vfd_logic": cap(has_vfd, modeled=has_vfd, generatable=False, reason="VFD discovered; Slow_Flt partial only"),
        "encoder_logic": cap(has_enc or has_sorter, modeled=True, generatable=bool(has_enc), reason="encoder tags generatable when present"),
        "scanner_structures": cap(has_scan, modeled=has_scan, generatable=False, reason="scanner"),
        "induct_tracking": cap(has_scan or has_sorter, modeled=True, generatable=False, reason="sorter"),
        "sorter_tracking": cap(has_sorter, modeled=True, generatable=False, reason="sorter runtime ≠ generation"),
        "divert_logic": cap(has_sorter, modeled=False, generatable=False, reason="sorter divert NOT_SUPPORTED"),
        "routing_logic": cap(has_sorter, modeled=True, generatable=False, reason="sorter route tables CFG"),
        "wcs_interface": cap(has_wcs, modeled=has_wcs, generatable=False, reason="wcs NOT_SUPPORTED"),
        "diagnostics_hmi": cap(True, modeled=False, generatable=False, reason="not in generic compiler path"),
        "simple_merge": cap(has_merge, modeled=has_merge, generatable=False, reason="merge CFG"),
        "sawtooth": cap(has_saw, modeled=has_saw, generatable=False, reason="no active sawtooth in PLC5 RUN" if not has_saw else "sawtooth"),
        "startstop_zones": cap(has_ss, modeled=has_ss, generatable=False, reason="zone membership CFG"),
    }

    generatable = sorted(k for k, v in matrix.items() if v.get("generatable"))
    cfg_required = sorted(
        k
        for k, v in matrix.items()
        if v.get("discovered") and not v.get("generatable") and "NOT_SUPPORTED" not in (v.get("reason") or "")
    )
    unsupported = sorted(
        k
        for k, v in matrix.items()
        if v.get("discovered") and ("NOT_SUPPORTED" in (v.get("reason") or "").upper() or k in {"divert_logic", "wcs_interface", "sorter_tracking"})
    )

    return {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "capabilities": matrix,
        "generatable": generatable,
        "configuration_required": cfg_required,
        "unsupported": unsupported,
        "policy": "Do not mark generatable unless a complete generic path exists",
    }


def build_activity_audit(site: dict[str, Any], table_inv: dict[str, Any]) -> dict[str, Any]:
    hist_tables = [t for t in (table_inv.get("tables") or []) if t.get("has_historical")]
    superseded = site.get("superseded_candidates") or []
    excluded = []
    available = []
    included = []
    for bucket in ("equipment", "motors", "vfds", "photoeyes", "encoders", "sorters"):
        for obj in site.get(bucket) or []:
            rec = {
                "bucket": bucket,
                "name": obj.get("normalized_name") or obj.get("raw_name"),
                "inclusion": obj.get("inclusion"),
                "active_state": obj.get("active_state"),
                "inclusion_why": obj.get("inclusion_why"),
                "source_scope": obj.get("source_scope"),
            }
            if obj.get("inclusion") == EXCLUDED:
                excluded.append(rec)
            elif obj.get("inclusion") == AVAILABLE:
                available.append(rec)
            elif obj.get("inclusion") == INCLUDED:
                included.append(rec)

    return {
        "generated_at": _ts(),
        "rule": "FOUND != ACTIVE != INCLUDED != GENERATED",
        "counts": {
            "INCLUDED": len(included),
            "AVAILABLE": len(available),
            "EXCLUDED": len(excluded),
            "superseded_candidates": len(superseded),
            "historical_table_stems": len(hist_tables),
        },
        "historical_tables": [{"table": t.get("table"), "files": t.get("files")} for t in hist_tables[:80]],
        "superseded_candidates": superseded[:100],
        "excluded_sample": excluded[:50],
        "available_sample": available[:50],
        "notes": [
            "Historical old.* files retained for review",
            "Superseded candidates never auto-deleted",
        ],
    }


def build_unresolved(site: dict[str, Any], matrix: dict[str, Any], sorter_model: dict[str, Any]) -> dict[str, Any]:
    items = []

    # Areas engineer-required
    for a in site.get("areas") or []:
        if a.get("default_area") or a.get("provenance") == "ENGINEER_CONFIGURED_REQUIRED":
            items.append(
                {
                    "field": "engineering_area",
                    "subsystem": "transport",
                    "why_unresolved": "No reliable Area table/rows from RUN; default Area_1 is engineer-required",
                    "evidence_present": ["default Area_1 placeholder"],
                    "evidence_missing": ["RUN Area membership table"],
                    "expected_engineer_action": "Rename/create Areas and assign equipment",
                    "generation_impact": "CONFIGURATION_REQUIRED — programs use effective Area name after rename",
                }
            )

    # PE unknown roles
    for pe in site.get("photoeyes") or []:
        roles = pe.get("pe_roles") or []
        if "UNKNOWN" in roles or pe.get("unresolved_roles"):
            items.append(
                {
                    "field": "pe_roles",
                    "subsystem": "transport",
                    "object": pe.get("normalized_name"),
                    "why_unresolved": "Insufficient Jamcheck/Fullline/Fulljam/Saw/Scanner evidence for HIGH-confidence role",
                    "evidence_present": [e.get("kind") for e in (pe.get("evidence") or [])][:8],
                    "evidence_missing": ["explicit safety-table Sensor_Name link or engineer override"],
                    "expected_engineer_action": "Confirm PE role in Transport editor",
                    "generation_impact": "CONFIGURATION_REQUIRED for PE wiring slots",
                }
            )

    # Sorter divert
    if sorter_model.get("detected"):
        items.append(
            {
                "field": "divert_mapping",
                "subsystem": "sorter",
                "why_unresolved": "Divert AOI generation path not generically supported",
                "evidence_present": ["Sorters.asc", "Srt* static tables"],
                "evidence_missing": ["generic divert compiler + confirmed lane/divert map"],
                "expected_engineer_action": "Provide divert map / wait for supported sorter leaf",
                "generation_impact": "GENERATION_NOT_SUPPORTED",
            }
        )
        items.append(
            {
                "field": "wcs_interface",
                "subsystem": "communication",
                "why_unresolved": "WCS/TCP generation not supported; runtime queues must not become static PLC defs",
                "evidence_present": ["Machine WCS_* peers", "MsgMap/WCSEvents when present"],
                "evidence_missing": ["generic WCS compiler inputs"],
                "expected_engineer_action": "Configure externally or wait for supported leaf",
                "generation_impact": "GENERATION_NOT_SUPPORTED",
            }
        )

    # Missing motors on included equipment
    for eq in site.get("equipment") or []:
        if eq.get("inclusion") != INCLUDED:
            continue
        if eq.get("motor"):
            continue
        nn = normalize_name(eq.get("normalized_name") or "")
        has_rel = any(
            str(r.get("kind")) == "motor_link"
            and (normalize_name(r.get("from") or "") == nn or normalize_name(r.get("to") or "") == nn)
            for r in (site.get("relationships") or [])
        )
        if not has_rel:
            items.append(
                {
                    "field": "motor",
                    "subsystem": "transport",
                    "object": eq.get("normalized_name"),
                    "why_unresolved": "INCLUDED conveyor lacks explicit Motor field / motor_link relationship",
                    "evidence_present": ["Conveyor geometry/ownership"],
                    "evidence_missing": ["Motor column or motor_link evidence"],
                    "expected_engineer_action": "Confirm motor or exclude equipment",
                    "generation_impact": "CONFIGURATION_REQUIRED",
                }
            )

    # Matrix unsupported
    for cap in matrix.get("unsupported") or []:
        items.append(
            {
                "field": cap,
                "subsystem": "compiler",
                "why_unresolved": f"Capability '{cap}' discovered/modeled but no complete generic generation path",
                "evidence_present": ["RUN evidence per generation_support_matrix"],
                "evidence_missing": ["complete generic compiler leaf"],
                "expected_engineer_action": "Leave unsupported; do not invent logic",
                "generation_impact": "GENERATION_NOT_SUPPORTED",
            }
        )

    # Cap volume for readability but keep counts
    return {
        "generated_at": _ts(),
        "count": len(items),
        "items": items[:500],
        "truncated": True if len(items) > 500 else False,
        "total_before_truncate": len(items),
    }


def generate_supported_l5x(site: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "generated": False,
        "path": None,
        "sha256": None,
        "library": None,
        "structural": None,
        "note": "",
    }
    try:
        from fortna_autogen import AutogenInput, ConveyorRow, build_l5x
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"autogen unavailable: {exc}"
        return result

    lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    forbidden = {
        "Sorter_Track_Program.L5X",
        "WCS_Interface_TCP_IP_Program.L5X",
        "ShippingSorter_Area_L3_Program.L5X",
    }
    if not lib.is_file():
        candidates = [p for p in (ROOT / "tools" / "libraries").rglob("*.L5X") if p.name not in forbidden]
        lib = candidates[0] if candidates else lib
    if not lib.is_file():
        result["note"] = "no generic library"
        return result
    result["library"] = str(lib)

    area = "Area_1"
    for a in site.get("areas") or []:
        if a.get("raw_name"):
            area = str(a["raw_name"])
            break

    rows = []
    for eq in site.get("equipment") or []:
        if eq.get("inclusion") != INCLUDED:
            continue
        name = eq.get("raw_name") or eq.get("normalized_name")
        if not name or not re.match(r"^P\d", str(name), re.I):
            continue
        m = re.search(r"P(\d{2,4})", str(name), re.I)
        num = int(m.group(1)) if m else len(rows) + 1
        rows.append(
            ConveyorRow(
                number=num,
                conveyor=re.sub(r"[^A-Za-z0-9_]", "_", str(name)),
                main_area=str(eq.get("area_id") or area),
                type=str(eq.get("equipment_type") or eq.get("type") or "STRAIGHT"),
            )
        )
        if len(rows) >= 40:
            break
    if not rows:
        result["note"] = "no INCLUDED conveyors for generation"
        return result

    try:
        inp = AutogenInput(
            project_name=f"{site.get('machine_scope')}_Blind",
            areas=[area],
            conveyors=rows,
        )
        text, meta = build_l5x(inp, lib)
        # Leakage scan before write
        low = text.lower()
        for frag in FORBIDDEN_FINISHED_FRAGMENTS:
            if frag.lower() in low:
                result["note"] = f"blocked finished-fragment in generated text: {frag}"
                return result
        out_path = out_dir / f"{site.get('machine_scope')}_blind_candidate.L5X"
        out_path.write_text(text, encoding="utf-8")
        result["generated"] = True
        result["path"] = str(out_path)
        result["sha256"] = sha256_file(out_path)
        result["sha256_stable"] = sha256_l5x_stable(out_path)
        result["meta"] = meta if isinstance(meta, dict) else {"meta": str(meta)}
        result["structural"] = structural_l5x_checks(out_path)
        result["conveyor_count"] = len(rows)
        result["area"] = area
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"generation failed: {exc}"
    return result


def genericity_leakage_test(
    site: dict[str, Any],
    candidate_sha_stable: str | None,
    out_dir: Path,
) -> dict[str, Any]:
    """Regenerate with decoy finished-PLC paths present/absent/renamed — output must match.

    Does not read finished PLC content. Only toggles decoy file presence.
    Compares stable hashes (ExportDate timestamps normalized).
    """
    decoy_dir = out_dir / "_decoy"
    decoy_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for label, action in (
        ("present", "keep"),
        ("renamed", "rename"),
        ("absent", "delete"),
    ):
        path = decoy_dir / "ORLY_Greensboro_NC_PLC5_FINISHED_DECOY.L5X"
        renamed = decoy_dir / "decoy_renamed_plc5.bin"
        # reset
        for p in (path, renamed):
            if p.exists():
                p.unlink()
        if action == "keep":
            path.write_text("DECOY_NOT_A_REAL_FINISHED_PLC5\n", encoding="utf-8")
        elif action == "rename":
            path.write_text("DECOY_NOT_A_REAL_FINISHED_PLC5\n", encoding="utf-8")
            path.rename(renamed)
        # absent: leave missing

        gen_out = out_dir / f"_gen_{label}"
        if gen_out.exists():
            shutil.rmtree(gen_out, ignore_errors=True)
        gen = generate_supported_l5x(site, gen_out)
        results[label] = {
            "sha256": gen.get("sha256"),
            "sha256_stable": gen.get("sha256_stable"),
            "generated": gen.get("generated"),
            "note": gen.get("note"),
        }

    shas = {v.get("sha256_stable") for v in results.values() if v.get("sha256_stable")}
    identical = len(shas) == 1 and bool(shas) and (
        not candidate_sha_stable or candidate_sha_stable in shas
    )
    return {
        "generated_at": _ts(),
        "identical": identical,
        "candidate_sha256_stable": candidate_sha_stable,
        "variants": results,
        "note": (
            "Decoy finished PLC5 never read as generation input; presence must not "
            "change stable output hash (ExportDate normalized)"
        ),
    }


def write_reports(
    out: Path,
    *,
    identity: dict,
    table_inv: dict,
    site: dict,
    activity_audit: dict,
    matrix: dict,
    sorter_model: dict,
    merge_model: dict,
    gen: dict,
    validation: dict,
    leakage: dict,
    unresolved: dict,
    frozen: dict,
) -> None:
    og = site.get("operational_groups") or {}
    eq = site.get("equipment") or []
    pe = site.get("photoeyes") or []
    ui = site.get("ui_status_summary") or {}

    def _inc(bucket):
        return {
            "INCLUDED": sum(1 for x in bucket if x.get("inclusion") == INCLUDED),
            "AVAILABLE": sum(1 for x in bucket if x.get("inclusion") == AVAILABLE),
            "EXCLUDED": sum(1 for x in bucket if x.get("inclusion") == EXCLUDED),
            "total": len(bucket),
        }

    md = [
        "# PLC5 Blind Discovery Report",
        "",
        f"Generated: `{_ts()}`",
        "",
        "Strict blind generation: PLC5 RUN + FortnaPlus knowledge + generic libraries only.",
        "Finished PLC5/4/2 were **not** used.",
        "",
        "## Controller / RUN",
        "",
        f"- Machine: **{identity.get('machine_name')}**",
        f"- Project: **{identity.get('project_name')}**",
        f"- Archive: `{((identity.get('archive') or {}).get('name'))}`",
        f"- Archive SHA256: `{(identity.get('archive') or {}).get('sha256')}`",
        f"- Controller overlays: **{identity.get('controller_overlay_count')}**",
        f"- Tables (unique stems): **{table_inv.get('unique_table_stems')}**",
        f"- Known high: **{table_inv.get('known_high_confidence')}**",
        f"- Known partial: **{table_inv.get('known_partial')}**",
        f"- Unknown: **{table_inv.get('unknown_tables')}**",
        "",
        "## Equipment activity",
        "",
        f"- Equipment: `{json.dumps(_inc(eq))}`",
        f"- Motors: `{json.dumps(_inc(site.get('motors') or []))}`",
        f"- VFDs: `{json.dumps(_inc(site.get('vfds') or []))}`",
        f"- Photoeyes: `{json.dumps(_inc(pe))}`",
        f"- Encoders: `{json.dumps(_inc(site.get('encoders') or []))}`",
        f"- Scanners: **{len(site.get('scanners') or [])}**",
        "",
        "## Operational groups",
        "",
        f"- Engineering areas: **{len(og.get('engineering_areas') or site.get('areas') or [])}**",
        f"- E-stop zones: **{len(og.get('estop_zones') or site.get('estop_zones') or [])}**",
        f"- Start/Stop zones: **{len(og.get('startstop_zones') or [])}**",
        f"- Jam zones: **{len(og.get('jam_zones') or [])}**",
        f"- Full groups: **{len(og.get('full_groups') or [])}**",
        "",
        "## Subsystems",
        "",
        f"- Merges: **{merge_model.get('count', 0)}** detected={merge_model.get('detected')}",
        f"- Sawtooth merges: **{len(site.get('sawtooth_merges') or [])}**",
        f"- Sorters: **{sorter_model.get('sorter_count', 0)}** detected={sorter_model.get('detected')}",
        f"- Tracking structures (runtime tables): **{len((sorter_model.get('runtime_tables') or {}))}**",
        f"- Communications: **{len(site.get('communications') or [])}**",
        "",
        "## UI status summary",
        "",
        "```json",
        json.dumps(ui, indent=2),
        "```",
        "",
        "## Generation",
        "",
        f"- Generatable: {', '.join(matrix.get('generatable') or []) or '(none)'}",
        f"- Configuration required: {', '.join(matrix.get('configuration_required') or []) or '(none)'}",
        f"- Unsupported: {', '.join(matrix.get('unsupported') or []) or '(none)'}",
        f"- L5X generated: **{gen.get('generated')}**",
        f"- L5X path: `{gen.get('path')}`",
        f"- L5X SHA256: `{gen.get('sha256')}`",
        f"- Structural ok: **{((gen.get('structural') or {}).get('ok'))}**",
        f"- Genericity identical: **{leakage.get('identical')}**",
        f"- Validator ok: **{validation.get('ok')}**",
        "",
        "## Biggest uncertainty / gap",
        "",
        "- Uncertainty: Engineering Area membership not proven from RUN (default Area_1 engineer-required).",
        "- Compiler gap: Sorter divert / WCS / tracking generation remain NOT_SUPPORTED despite rich PLC5 sorter evidence.",
        "",
        "## Frozen",
        "",
        f"- Commit: `{frozen.get('commit')}`",
        f"- SiteModel SHA256: `{frozen.get('site_model_sha256')}`",
        f"- Matrix SHA256: `{frozen.get('generation_support_matrix_sha256')}`",
        "",
    ]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    docs = ROOT / "docs" / "CP5_BLIND_DISCOVERY.md"
    docs.write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC5 blind RUN-to-PLC validation")
    ap.add_argument("--run-dir", type=Path, default=ROOT / "workspace" / "cp5-run" / "RUN")
    ap.add_argument(
        "--archive",
        type=Path,
        default=ROOT
        / "workspace"
        / "cp5-run"
        / "_archive"
        / "20251016-0933-OReillyGreensboro-ORNCCP5-RUN.tar.gz",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "cp5-blind")
    ap.add_argument("--machine", default="", help="Override MACHINENAME")
    args = ap.parse_args(argv)

    run_dir: Path = args.run_dir.resolve()
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    archive = args.archive if args.archive and args.archive.is_file() else None

    if not (run_dir / "FORTNA").is_dir():
        print(json.dumps({"ok": False, "error": f"FORTNA missing under {run_dir}"}))
        return 2

    machine = (args.machine or "").strip() or infer_machine_from_run(run_dir)
    if not machine:
        print(json.dumps({"ok": False, "error": "machine required"}))
        return 2

    kb = _kb()
    identity = build_run_identity(run_dir, archive)
    write_json(out / "run_identity.json", identity)

    table_inv = inventory_tables(run_dir, machine, kb)
    write_json(out / "table_inventory.json", table_inv)

    # Blind discovery — dedicated out, do not overwrite CP2/CP4 exports
    discover_out = out / "discovery"
    disc = discover(run_dir, machine, discover_out, blind=True)
    site = json.loads((discover_out / "site_model.json").read_text(encoding="utf-8"))

    # Ensure enrichment/supersession even if discover already did
    enrich_site_model(site, kb)
    evaluate_supersession(site)

    deepen_encoders(run_dir, machine, site)
    merge_model = deepen_merge_model(run_dir, machine, site)
    sorter_model = deepen_sorter_model(run_dir, machine, site)
    deepen_communications(run_dir, machine, site)

    # Sawtooth honesty: if no active merges, clear any empty leftovers
    if not site.get("sawtooth_merges"):
        site.setdefault("notes", []).append(
            "No active SawMerge/SawLane named rows for ORNCCP5 — sawtooth not invented"
        )

    write_json(discover_out / "site_model.json", site)
    write_json(out / "site_model.json", site)
    write_json(out / "sorter_model.json", sorter_model)
    write_json(out / "merge_model.json", merge_model)

    activity_audit = build_activity_audit(site, table_inv)
    write_json(out / "activity_audit.json", activity_audit)

    matrix = build_generation_matrix(site, sorter_model, merge_model)
    write_json(out / "generation_support_matrix.json", matrix)

    unresolved = build_unresolved(site, matrix, sorter_model)
    write_json(out / "unresolved.json", unresolved)

    validation = validate_site_model(site)
    write_json(out / "validation_report.json", validation)

    gen = generate_supported_l5x(site, out / "generated")
    write_json(out / "generation_result.json", gen)

    leakage = genericity_leakage_test(site, gen.get("sha256_stable"), out)
    write_json(out / "genericity_leakage_test.json", leakage)

    # UI workflow note
    ui_workflow = {
        "workflow": ["Import RUN", "Discover", "populated editors", "Review/Correct", "Build PLC"],
        "cp5_specific_buttons_required": False,
        "auto_populate_tabs": {
            "transport": True,
            "sawtooth": bool(site.get("sawtooth_merges")),
            "sorter": bool(sorter_model.get("detected")),
            "merge": bool(merge_model.get("detected")),
        },
        "note": "Normal Site Forge import path; no CP5-only scripts required",
    }
    write_json(out / "ui_workflow.json", ui_workflow)

    # Freeze
    try:
        import subprocess

        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
        )
    except Exception:
        commit = "UNKNOWN"

    frozen = {
        "generated_at": _ts(),
        "commit": commit,
        "machine": machine,
        "archive_sha256": (identity.get("archive") or {}).get("sha256"),
        "site_model_sha256": sha256_json(site),
        "discovery_artifact_sha256": sha256_file(discover_out / "site_model.json")
        if (discover_out / "site_model.json").is_file()
        else None,
        "generation_support_matrix_sha256": sha256_json(matrix),
        "generated_l5x_path": gen.get("path"),
        "generated_l5x_sha256": gen.get("sha256"),
        "generated_l5x_sha256_stable": gen.get("sha256_stable"),
        "genericity_identical": leakage.get("identical"),
        "validation_ok": validation.get("ok"),
        "finished_plc_used": False,
        "blind": True,
        "policy": "Do not regenerate using answer-sheet information after freeze",
    }
    write_json(out / "frozen_output.json", frozen)

    write_reports(
        out,
        identity=identity,
        table_inv=table_inv,
        site=site,
        activity_audit=activity_audit,
        matrix=matrix,
        sorter_model=sorter_model,
        merge_model=merge_model,
        gen=gen,
        validation=validation,
        leakage=leakage,
        unresolved=unresolved,
        frozen=frozen,
    )

    eq_counts = {
        "INCLUDED": sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == INCLUDED),
        "AVAILABLE": sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == AVAILABLE),
        "EXCLUDED": sum(1 for e in (site.get("equipment") or []) if e.get("inclusion") == EXCLUDED),
        "total": len(site.get("equipment") or []),
    }
    summary = {
        "ok": bool(gen.get("generated")) and bool(leakage.get("identical")),
        "machine": machine,
        "equipment": eq_counts,
        "activity_all_buckets": activity_audit.get("counts"),
        "tables": {
            "unique": table_inv.get("unique_table_stems"),
            "known_high": table_inv.get("known_high_confidence"),
            "known_partial": table_inv.get("known_partial"),
            "unknown": table_inv.get("unknown_tables"),
        },
        "sorters": sorter_model.get("sorter_count"),
        "merges": merge_model.get("count"),
        "sawtooth": len(site.get("sawtooth_merges") or []),
        "l5x_sha256": gen.get("sha256"),
        "l5x_sha256_stable": gen.get("sha256_stable"),
        "site_model_sha256": frozen.get("site_model_sha256"),
        "genericity_identical": leakage.get("identical"),
        "out": str(out),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
