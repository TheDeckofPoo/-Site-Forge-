#!/usr/bin/env python3
"""CP4 RUN discovery — inventory only (no PLC generation).

SOURCE OF TRUTH: CP4 RUN extract only. Never reads finished / reference PLC4 L5X.
Does not implement CP4 PLC generation or autogen changes.

Usage:
  python tools/scripts/fortna_cp4_discovery.py \\
    --run-dir workspace/cp4-run/RUN \\
    --machine ORNCCP4 \\
    --out exports/cp4-discovery
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

from fortna_asc import read_asc  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _anchors,
    _angle_delta,
    _clean,
    _dist,
    _f,
    _is_mech_conveyor,
    _is_motor_row,
    _is_pe_row,
    _load_mtrchain,
    _load_word_map,
    _row_on_controller,
)

try:
    from fortna_physical_geometry import build_equipment_geometry
except Exception:  # pragma: no cover
    build_equipment_geometry = None  # type: ignore

PROVENANCE_RUN_EXPLICIT = "RUN_EXPLICIT"
PROVENANCE_RUN_DERIVED = "RUN_DERIVED"
PROVENANCE_RUN_INFERRED = "RUN_INFERRED"  # legacy alias → prefer RUN_DERIVED in new fields
PROVENANCE_ENGINEER_CONFIGURED = "ENGINEER_CONFIGURED"
PROVENANCE_ENGINEER_REQUIRED = "ENGINEER_REQUIRED"
PROVENANCE_UNKNOWN = "UNKNOWN"

BLANK = {"", "N/A", "INVALID", "NONE", "~", "N/A~", "n/a"}
TAR_PROVENANCE = (
    r"C:\Users\curtiskricke\Desktop\ORielly Green\Greensboro Tar.gz"
    r"\20251016-0933-OReillyGreensboro-ORNCCP4-RUN.tar.gz"
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_name(v: str) -> bool:
    s = _clean(v)
    if not s:
        return False
    if s.upper() in BLANK or s.startswith("==="):
        return False
    return True


def _float_or_none(v: Any) -> float | None:
    return _f(v)


def resolve_asc(fortna: Path, basename: str, machine: str) -> tuple[Path | None, str]:
    """Prefer controller-scoped overlay (File.asc.MACHINE) over base File.asc."""
    overlay = fortna / f"{basename}.{machine}"
    base = fortna / basename
    if overlay.is_file() and overlay.stat().st_size > 0:
        return overlay, "controller_overlay"
    if base.is_file():
        return base, "base"
    return None, "missing"


def _vfd_base(name: str) -> str:
    m = re.match(r"^(VFD\d+[A-Z]?)", (name or "").upper())
    return m.group(1) if m else (name or "").upper()


def _extract_p_from_name(name: str) -> str:
    """Extract P### from an explicit RUN name token (lane name, etc.)."""
    m = re.search(r"(P\d{2,4}[A-Za-z]?)", name or "", re.I)
    return m.group(1).upper() if m else ""


def _extract_p_from_pe(name: str) -> str:
    m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _extract_p_from_vfd(name: str) -> str:
    m = re.match(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _extract_p_from_motor(name: str) -> str:
    m = re.match(r"^M[\s\-_]*(\d{2,4}[A-Za-z]?)", name or "", re.I)
    return ("P" + m.group(1).upper()) if m else ""


def _rel(path: Path | None, run_dir: Path) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def _read_table(path: Path | None) -> tuple[list[str], list[dict[str, str]]]:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return [], []
    return read_asc(path)


# ---------------------------------------------------------------------------
# Sawtooth
# ---------------------------------------------------------------------------

def discover_sawtooth(run_dir: Path, machine: str) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    sources: dict[str, Any] = {}

    merge_path, merge_src = resolve_asc(fortna, "SawMerge.asc", machine)
    lane_path, lane_src = resolve_asc(fortna, "SawLane.asc", machine)
    sources["SawMerge"] = {"path": _rel(merge_path, run_dir), "resolution": merge_src}
    sources["SawLane"] = {"path": _rel(lane_path, run_dir), "resolution": lane_src}

    hs_tables = {}
    for name in ("HSSawMerge.asc", "HSSawLane.asc", "HSSawParm.asc", "HSSawState.asc", "SawState.asc"):
        p, src = resolve_asc(fortna, name, machine)
        headers, rows = _read_table(p)
        active = [r for r in rows if _valid_name(r.get("Name") or r.get(headers[0] if headers else "") or "")]
        # HSSawState / SawState are enum tables — count non-blank names
        if name in ("HSSawState.asc", "SawState.asc"):
            active = [r for r in rows if _valid_name(r.get("Name"))]
        hs_tables[name] = {
            "path": _rel(p, run_dir),
            "resolution": src,
            "row_count": len(rows),
            "active_named_rows": len(active),
            "sample_names": [_clean(r.get("Name")) for r in active[:12]],
        }
    sources["hs_and_state"] = hs_tables

    _mh, merge_rows = _read_table(merge_path)
    merges: list[dict[str, Any]] = []
    for r in merge_rows:
        name = _clean(r.get("Name"))
        if not _valid_name(name):
            continue
        merges.append(
            {
                "name": name,
                "motor_io": _clean(r.get("MotorIO")),
                "reservation": _clean(r.get("ReserveIN")),
                "lane_enable_delay_tm": _clean(r.get("LaneEnableDelayTM")),
                "slice_seconds": _float_or_none(r.get("pSliceSeconds")),
                "lanes": [],  # filled after lane parse
                "source_file": _rel(merge_path, run_dir),
                "provenance": PROVENANCE_RUN_EXPLICIT,
            }
        )

    _lh, lane_rows = _read_table(lane_path)
    lanes: list[dict[str, Any]] = []
    for r in lane_rows:
        name = _clean(r.get("Name"))
        if not _valid_name(name):
            continue
        # Conveyor identity comes from explicit lane Name (e.g. LANE_0_P219 → P219).
        # Never invent identity from LaneNdx / P-number ordering.
        conveyor = _extract_p_from_name(name)
        lane_index_raw = _clean(r.get("LaneNdx"))
        try:
            lane_index = int(float(lane_index_raw)) if lane_index_raw else None
        except ValueError:
            lane_index = None

        drive = _clean(r.get("DisableIO"))
        photoeye = _clean(r.get("PhotoEyeIO"))
        merge_name = _clean(r.get("SawMerge"))

        conveyor_provenance = (
            PROVENANCE_RUN_EXPLICIT
            if conveyor
            else PROVENANCE_ENGINEER_REQUIRED
        )
        if not conveyor:
            conveyor_note = "Lane Name has no embedded P-tag; engineer must supply conveyor"
        else:
            conveyor_note = "Conveyor taken from explicit lane Name token (not LaneNdx order)"

        lane = {
            "name": name,
            "conveyor": conveyor or None,
            "conveyor_provenance": conveyor_provenance,
            "conveyor_note": conveyor_note,
            "lane_index": lane_index,
            "lane_index_provenance": (
                PROVENANCE_RUN_EXPLICIT if lane_index is not None else PROVENANCE_UNKNOWN
            ),
            "approach": _clean(r.get("ApproachUP")),
            "collision": _clean(r.get("CollisionUP")),
            "lane_input": _clean(r.get("LaneIN")),
            "photoeye": photoeye,
            "drive": drive,
            "vfd": drive if drive.upper().startswith("VFD") else None,
            "slice_seconds": _float_or_none(r.get("SliceSeconds")),
            "reserve_seconds": _float_or_none(r.get("ReserveSeconds")),
            "saw_merge": merge_name,
            "allowed_to_run": _clean(r.get("AllowedToRun")),
            "source_file": _rel(lane_path, run_dir),
            "provenance": PROVENANCE_RUN_EXPLICIT,
            "relationships": [
                {
                    "type": "lane_to_merge",
                    "from": name,
                    "to": merge_name,
                    "provenance": PROVENANCE_RUN_EXPLICIT if merge_name else PROVENANCE_UNKNOWN,
                },
                {
                    "type": "lane_to_conveyor",
                    "from": name,
                    "to": conveyor or None,
                    "provenance": conveyor_provenance,
                },
                {
                    "type": "lane_to_vfd",
                    "from": name,
                    "to": drive if drive.upper().startswith("VFD") else None,
                    "provenance": (
                        PROVENANCE_RUN_EXPLICIT
                        if drive.upper().startswith("VFD")
                        else PROVENANCE_UNKNOWN
                    ),
                },
                {
                    "type": "lane_to_photoeye",
                    "from": name,
                    "to": photoeye or None,
                    "provenance": PROVENANCE_RUN_EXPLICIT if photoeye else PROVENANCE_UNKNOWN,
                },
            ],
        }
        lanes.append(lane)

    merge_by_name = {m["name"]: m for m in merges}
    for lane in lanes:
        mn = lane.get("saw_merge") or ""
        if mn in merge_by_name:
            merge_by_name[mn]["lanes"].append(lane["name"])

    # HSSaw active content (usually empty on this site)
    hs_active = {
        k: v
        for k, v in hs_tables.items()
        if v["active_named_rows"] > 0 and k.startswith("HS")
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC4 L5X not read",
        "sources": sources,
        "merges": merges,
        "lanes": lanes,
        "hs_tables_active": hs_active,
        "counts": {
            "merges": len(merges),
            "lanes": len(lanes),
            "lanes_with_conveyor_in_name": sum(1 for ln in lanes if ln.get("conveyor")),
            "lanes_missing_conveyor": sum(1 for ln in lanes if not ln.get("conveyor")),
            "hs_active_tables": len(hs_active),
        },
        "notes": [
            "Lane conveyor identity is taken only from explicit tokens in SawLane Name "
            "(e.g. LANE_0_P219 → P219). LaneNdx / P-number order is never used as identity.",
            "HSSaw* tables are inventoried; active configuration on this RUN lives in "
            "SawMerge.asc.ORNCCP4 / SawLane.asc.ORNCCP4.",
        ],
    }


# ---------------------------------------------------------------------------
# VFD
# ---------------------------------------------------------------------------

def discover_vfd(
    run_dir: Path,
    machine: str,
    sawtooth: dict[str, Any],
) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    conv_path, conv_src = resolve_asc(fortna, "Conveyor.asc", machine)
    if conv_path is None:
        raise FileNotFoundError(f"Missing Conveyor.asc under {fortna}")

    word_map = _load_word_map(run_dir)
    mtrchain = _load_mtrchain(run_dir)
    # Invert mtrchain: motor → conveyors
    motor_to_convs: dict[str, list[str]] = defaultdict(list)
    for conv, motors in mtrchain.items():
        for mot in motors:
            motor_to_convs[mot.upper()].append(conv.upper())

    _h, rows = read_asc(conv_path)

    # Collect VFD device rows scoped to machine
    device_rows: list[dict[str, Any]] = []
    by_base: dict[str, dict[str, Any]] = {}

    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name or not name.upper().startswith("VFD"):
            continue
        if not _row_on_controller(r, machine, word_map):
            continue
        base = _vfd_base(name)
        rec = {
            "io_name": name,
            "vfd_base": base,
            "type": _clean(r.get("Type")),
            "machine_name": _clean(r.get("Machine_Name")),
            "description": _clean(r.get("General_Description")),
            "io_address_word": _clean(r.get("IO_Address_Word")),
            "drawing_page": _clean(r.get("Electrical Drawing Page No.")),
            "source_file": _rel(conv_path, run_dir),
            "provenance": PROVENANCE_RUN_EXPLICIT,
        }
        device_rows.append(rec)
        bucket = by_base.setdefault(
            base,
            {
                "vfd": base,
                "device_points": [],
                "machine_name": _clean(r.get("Machine_Name")),
                "conveyors": [],
                "conveyor_mapping_provenance": PROVENANCE_UNKNOWN,
                "conveyor_mapping_evidence": [],
                "saw_lanes": [],
                "saw_lane_mapping_provenance": PROVENANCE_UNKNOWN,
                "saw_lane_mapping_evidence": [],
            },
        )
        bucket["device_points"].append(name)

    # Explicit Mtrchain mapping: VFD*_EN / VFD* → Motor_Chained* P-tags
    for base, bucket in by_base.items():
        evidence = []
        convs: list[str] = []
        # Match any mtrchain motor whose base equals this VFD
        for motor, linked in motor_to_convs.items():
            if _vfd_base(motor) != base:
                continue
            for c in linked:
                if c not in convs:
                    convs.append(c)
                evidence.append(
                    {
                        "method": "Mtrchain.asc",
                        "motor_name": motor,
                        "conveyor": c,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
        # Also Motor column on mechanical rows (rare)
        for r in rows:
            if not _is_mech_conveyor(r):
                continue
            mot_col = _clean(r.get("Motor"))
            if mot_col and _vfd_base(mot_col) == base:
                tag = _clean(r.get("IO_Name")).upper()
                if tag not in convs:
                    convs.append(tag)
                evidence.append(
                    {
                        "method": "Conveyor.asc Motor column",
                        "motor_name": mot_col,
                        "conveyor": tag,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
        bucket["conveyors"] = convs
        bucket["conveyor_mapping_evidence"] = evidence
        if evidence:
            bucket["conveyor_mapping_provenance"] = PROVENANCE_RUN_EXPLICIT
        else:
            bucket["conveyor_mapping_provenance"] = PROVENANCE_UNKNOWN

    # Saw-lane mapping from DisableIO / merge MotorIO (explicit saw tables only)
    for lane in sawtooth.get("lanes") or []:
        drive = (lane.get("vfd") or lane.get("drive") or "").upper()
        if not drive.startswith("VFD"):
            continue
        base = _vfd_base(drive)
        if base not in by_base:
            # Lane references a VFD not present as ORNCCP4 Conveyor.asc device
            by_base[base] = {
                "vfd": base,
                "device_points": [],
                "machine_name": "",
                "conveyors": [],
                "conveyor_mapping_provenance": PROVENANCE_UNKNOWN,
                "conveyor_mapping_evidence": [],
                "saw_lanes": [],
                "saw_lane_mapping_provenance": PROVENANCE_UNKNOWN,
                "saw_lane_mapping_evidence": [],
                "note": "Referenced by SawLane but no ORNCCP4 VFD* device row found",
            }
        bucket = by_base[base]
        if lane["name"] not in bucket["saw_lanes"]:
            bucket["saw_lanes"].append(lane["name"])
        bucket["saw_lane_mapping_evidence"].append(
            {
                "method": "SawLane.DisableIO",
                "lane": lane["name"],
                "drive": drive,
                "provenance": PROVENANCE_RUN_EXPLICIT,
            }
        )
        bucket["saw_lane_mapping_provenance"] = PROVENANCE_RUN_EXPLICIT

    for merge in sawtooth.get("merges") or []:
        mio = (merge.get("motor_io") or "").upper()
        if not mio.startswith("VFD"):
            continue
        base = _vfd_base(mio)
        if base not in by_base:
            continue
        bucket = by_base[base]
        bucket.setdefault("merge_motor_io", [])
        if merge["name"] not in bucket["merge_motor_io"]:
            bucket["merge_motor_io"].append(merge["name"])
        bucket.setdefault("merge_mapping_evidence", []).append(
            {
                "method": "SawMerge.MotorIO",
                "merge": merge["name"],
                "motor_io": mio,
                "provenance": PROVENANCE_RUN_EXPLICIT,
            }
        )

    vfds = [by_base[k] for k in sorted(by_base)]
    unknown_conveyor = [v for v in vfds if v["conveyor_mapping_provenance"] == PROVENANCE_UNKNOWN]
    unknown_lane = [
        v
        for v in vfds
        if not v.get("saw_lanes") and v["conveyor_mapping_provenance"] != PROVENANCE_UNKNOWN
    ]

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC4 L5X not read",
        "source_file": _rel(conv_path, run_dir),
        "source_resolution": conv_src,
        "devices": device_rows,
        "vfds": vfds,
        "unknown_conveyor_mappings": [
            {"vfd": v["vfd"], "provenance": PROVENANCE_UNKNOWN}
            for v in unknown_conveyor
        ],
        "counts": {
            "device_rows": len(device_rows),
            "unique_vfd_bases": len(vfds),
            "mapped_to_conveyor_explicit": sum(
                1 for v in vfds if v["conveyor_mapping_provenance"] == PROVENANCE_RUN_EXPLICIT
            ),
            "unknown_conveyor_mapping": len(unknown_conveyor),
            "mapped_to_saw_lane_explicit": sum(
                1 for v in vfds if v["saw_lane_mapping_provenance"] == PROVENANCE_RUN_EXPLICIT
            ),
        },
        "notes": [
            "VFD→conveyor mapped only via explicit RUN relationships "
            "(Mtrchain Motor_Chained*, Conveyor Motor column, SawMerge/SawLane tables).",
            "Number-only guesses (VFD414 → P414 by digits alone without Mtrchain/saw evidence) "
            "are not emitted as mappings.",
        ],
    }


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

def discover_encoders(
    run_dir: Path,
    machine: str,
    sawtooth: dict[str, Any],
    vfd: dict[str, Any],
) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    path, src = resolve_asc(fortna, "Encoders.asc", machine)
    headers, rows = _read_table(path)

    merge_names = {m["name"].upper() for m in (sawtooth.get("merges") or [])}
    merge_motor = {
        _vfd_base(m.get("motor_io") or ""): m["name"]
        for m in (sawtooth.get("merges") or [])
        if (m.get("motor_io") or "").upper().startswith("VFD")
    }
    vfd_bases = {v["vfd"] for v in (vfd.get("vfds") or [])}

    encoders: list[dict[str, Any]] = []
    for r in rows:
        name = _clean(r.get("Encoder Name") or r.get("Name"))
        if not _valid_name(name):
            continue
        io = _clean(r.get("Encoder I/O"))
        enable = _clean(r.get("EnableBit"))
        jamzone = _clean(r.get("Jamzone"))
        desc = jamzone  # Jamzone doubles as functional description on this table

        associations: list[dict[str, Any]] = []

        # Explicit EnableBit → VFD
        if enable.upper().startswith("VFD"):
            base = _vfd_base(enable)
            associations.append(
                {
                    "type": "encoder_enable_vfd",
                    "to": enable,
                    "vfd_base": base,
                    "on_machine_vfd_inventory": base in vfd_bases,
                    "provenance": PROVENANCE_RUN_EXPLICIT,
                }
            )
            if base in merge_motor:
                associations.append(
                    {
                        "type": "encoder_to_saw_merge_via_motor_io",
                        "to": merge_motor[base],
                        "via": enable,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )

        # Explicit Jamzone text referencing sawtooth merge
        jam_u = jamzone.upper()
        if "SAWTOOTH" in jam_u or jam_u in merge_names or jam_u.replace(" ", "_") in merge_names:
            associations.append(
                {
                    "type": "encoder_jamzone_sawtooth",
                    "to": jamzone,
                    "provenance": PROVENANCE_RUN_EXPLICIT,
                }
            )

        encoders.append(
            {
                "encoder": name,
                "io": io,
                "ticks_per_foot": _float_or_none(r.get("Ticks Per Foot")),
                "target_fpm": _float_or_none(r.get("Target FPM")),
                "calculated_fpm": _float_or_none(r.get("Calculated FPM")),
                "enable": enable,
                "jamzone": jamzone,
                "description": desc,
                "tolerance_fpm": _float_or_none(r.get("Tolerance_FPM")),
                "sample_seconds": _float_or_none(r.get("SampleSeconds")),
                "source_file": _rel(path, run_dir),
                "provenance": PROVENANCE_RUN_EXPLICIT,
                "associations": associations,
            }
        )

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC4 L5X not read",
        "source_file": _rel(path, run_dir),
        "source_resolution": src,
        "headers": headers,
        "encoders": encoders,
        "counts": {
            "encoders": len(encoders),
            "with_vfd_enable": sum(
                1
                for e in encoders
                if any(a["type"] == "encoder_enable_vfd" for a in e["associations"])
            ),
            "with_sawtooth_association": sum(
                1
                for e in encoders
                if any(
                    a["type"] in ("encoder_jamzone_sawtooth", "encoder_to_saw_merge_via_motor_io")
                    for a in e["associations"]
                )
            ),
        },
        "notes": [
            "Encoder↔sawtooth / Encoder↔VFD associations emitted only when RUN fields "
            "explicitly support them (EnableBit, Jamzone, SawMerge.MotorIO).",
        ],
    }


# ---------------------------------------------------------------------------
# Tracking / WCS
# ---------------------------------------------------------------------------

def _meaningful(v: str) -> bool:
    """True for non-placeholder tracking values (rejects 0 / N/A / blank)."""
    s = _clean(v)
    if not s or not _valid_name(s):
        return False
    if s in {"0", "0.000", "New"}:
        return False
    # WCS topic paths are meaningful even without alphanumeric identity tokens
    if s.startswith("/"):
        return True
    return True


def _table_inventory(
    run_dir: Path,
    rel_name: str,
    name_cols: tuple[str, ...],
    extra_cols: tuple[str, ...] = (),
    *,
    require_name: bool = True,
) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    path = fortna / rel_name
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    headers, rows = _read_table(path if exists else None)

    def row_active(r: dict) -> bool:
        # Primary identity columns must be real names (R1, event names, …).
        named = any(_meaningful(r.get(c) or "") for c in name_cols)
        if require_name:
            if not named:
                return False
            return True
        # MsgWCS: Destination topic is the active signal (MsgText often blank)
        if named:
            return True
        return any(_meaningful(r.get(c) or "") for c in extra_cols)

    active = [r for r in rows if row_active(r)]
    samples = []
    for r in active[:8]:
        samples.append(
            {c: _clean(r.get(c)) for c in list(name_cols) + list(extra_cols) if c in r}
        )

    relationships: list[dict[str, Any]] = []
    # Characterize exposed relationship columns when populated
    for r in active[:50]:
        for col in (
            "ScanZoneID",
            "SorterLane",
            "HostZone",
            "Destination",
            "WCSDestination",
            "WCSCategory",
            "WCSService",
            "RouteBossRec",
            "RouteTableRec",
            "XfrZoneID",
            "ConfirmScan",
        ):
            val = _clean(r.get(col))
            if _meaningful(val) or (col == "Destination" and val.startswith("/")):
                relationships.append(
                    {
                        "column": col,
                        "value": val,
                        "row_name": _clean(r.get(name_cols[0])) if name_cols else "",
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
                break

    return {
        "table": rel_name,
        "path": _rel(path, run_dir) if exists else "",
        "exists": exists,
        "byte_size": size,
        "row_count": len(rows),
        "active_rows": len(active),
        "active_on_cp4_records": len(active) > 0 and size > 0,
        "headers": headers[:40],
        "samples": samples,
        "relationship_samples": relationships[:30],
        "provenance": PROVENANCE_RUN_EXPLICIT if exists else PROVENANCE_UNKNOWN,
    }


def discover_tracking_wcs(run_dir: Path, machine: str) -> dict[str, Any]:
    tables = [
        _table_inventory(run_dir, "MsgTrack.asc", ("Name", "ConfirmScan")),
        _table_inventory(
            run_dir,
            "MsgWCS.asc",
            ("MsgText",),
            ("Destination",),
            require_name=False,
        ),
        _table_inventory(
            run_dir,
            "SrtTrack1.asc",
            ("Name",),
            ("ScanZoneID", "SorterLane", "HostZone", "ConfirmScan"),
        ),
        _table_inventory(
            run_dir,
            "SrtTrack2.asc",
            ("Name",),
            ("ScanZoneID", "SorterLane", "HostZone"),
        ),
        _table_inventory(
            run_dir,
            "SrtTrack3.asc",
            ("Name",),
            ("ScanZoneID", "SorterLane", "HostZone"),
        ),
        _table_inventory(
            run_dir,
            "SrtTrack4.asc",
            ("Name",),
            ("ScanZoneID", "SorterLane", "HostZone"),
        ),
        _table_inventory(
            run_dir,
            "SrtTrack5.asc",
            ("Name",),
            ("ScanZoneID", "SorterLane", "HostZone"),
        ),
        _table_inventory(
            run_dir,
            "XfrTrack.asc",
            ("Name",),
            ("ScanZoneID", "XfrZoneID", "HostZone"),
        ),
        _table_inventory(
            run_dir,
            "WCSEvents.asc",
            ("EventName",),
            ("WCSEnable", "WCSDestination", "WCSCategory", "WCSService", "WCSMachProc"),
        ),
    ]

    # WCSEvents enable summary
    wcs_path = run_dir / "FORTNA" / "WCSEvents.asc"
    enabled_events = []
    if wcs_path.is_file() and wcs_path.stat().st_size > 0:
        _h, wrows = read_asc(wcs_path)
        for r in wrows:
            if _clean(r.get("WCSEnable")).upper() in ("Y", "YES"):
                enabled_events.append(
                    {
                        "event": _clean(r.get("EventName")),
                        "destination": _clean(r.get("WCSDestination")),
                        "category": _clean(r.get("WCSCategory")),
                        "service": _clean(r.get("WCSService")),
                        "mach_proc": _clean(r.get("WCSMachProc")),
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )

    by_name = {t["table"]: t for t in tables}
    srt_active = {
        i: by_name[f"SrtTrack{i}.asc"]["active_rows"] for i in range(1, 6)
    }
    characterization = {
        "MsgTrack": (
            "Empty / zero-byte on this CP4 RUN — no active tracking message records."
            if by_name["MsgTrack.asc"]["byte_size"] == 0
            else (
                f"Populated MsgTrack records present "
                f"({by_name['MsgTrack.asc']['active_rows']} active)."
            )
        ),
        "MsgWCS": (
            f"Active outbound WCS message queue with {by_name['MsgWCS.asc']['active_rows']} "
            "rows carrying Destination topics. Runtime event traffic, not static topology."
        ),
        "SrtTrack": (
            "SrtTrack named-slot counts: "
            + ", ".join(f"SrtTrack{i}={srt_active[i]}" for i in range(1, 6))
            + ". Relationships exposed when active: ScanZoneID, ConfirmScan, SorterLane."
        ),
        "XfrTrack": (
            "No named active transfer-track rows on this RUN."
            if by_name["XfrTrack.asc"]["active_rows"] == 0
            else (
                f"Active XfrTrack rows present ({by_name['XfrTrack.asc']['active_rows']}); "
                "exposes XfrZoneID / ScanZoneID when populated."
            )
        ),
        "WCSEvents": (
            f"{len(enabled_events)} events with WCSEnable=Y. Exposes event→topic "
            "(WCSDestination) and category/service relationships. Not conveyor topology."
        ),
    }

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC4 L5X not read; inventory only (not implemented)",
        "tables": tables,
        "wcs_enabled_events": enabled_events,
        "wcs_enabled_count": len(enabled_events),
        "characterization": characterization,
        "counts": {
            "tables_inventoried": len(tables),
            "tables_with_active_rows": sum(1 for t in tables if t["active_rows"] > 0),
            "msgtrack_active": by_name["MsgTrack.asc"]["active_rows"],
            "msgwcs_active": by_name["MsgWCS.asc"]["active_rows"],
            "srttrack_active_total": sum(
                by_name[f"SrtTrack{i}.asc"]["active_rows"] for i in range(1, 6)
            ),
            "xfrtrack_active": by_name["XfrTrack.asc"]["active_rows"],
            "wcs_events_enabled": len(enabled_events),
        },
        "notes": [
            "Tracking/WCS tables are inventoried and characterized only — no generation "
            "or Autogen implementation is performed by this discovery pass.",
            "Active-row detection requires a real Name/EventName (or MsgWCS Destination "
            "topic); numeric placeholder slots are not counted as active.",
        ],
    }


# ---------------------------------------------------------------------------
# Equipment + layout
# ---------------------------------------------------------------------------

def _controller_linked_tags(
    rows: list[dict],
    machine: str,
    word_map: dict,
    mtrchain: dict[str, list[str]],
    mech_tags: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Map mechanical P-tag → ownership evidence for this controller (RUN only)."""
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    motor_owners: dict[str, bool] = {}

    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        on = _row_on_controller(r, machine, word_map)
        nu = name.upper()

        if _is_mech_conveyor(r):
            mn = _clean(r.get("Machine_Name"))
            if mn.upper() == machine.upper():
                evidence[nu].append(
                    {
                        "method": "explicit_machine_name",
                        "detail": mn,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
            continue

        if not on:
            continue

        if _is_pe_row(r):
            link = _extract_p_from_pe(name)
            if link in mech_tags:
                evidence[link].append(
                    {
                        "method": "pe_name_link",
                        "detail": name,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
            continue

        if nu.startswith("VFD"):
            link = _extract_p_from_vfd(name)
            if link in mech_tags:
                evidence[link].append(
                    {
                        "method": "vfd_name_link",
                        "detail": name,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )
            motor_owners[nu] = True
            continue

        if _is_motor_row(r):
            motor_owners[nu] = True
            link = _extract_p_from_motor(name)
            if link in mech_tags:
                evidence[link].append(
                    {
                        "method": "motor_name_link",
                        "detail": name,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )

    # Mtrchain: motors owned by this controller transfer ownership to chained P-tags
    for conv, motors in mtrchain.items():
        if conv not in mech_tags:
            continue
        for mot in motors:
            if motor_owners.get(mot.upper()):
                evidence[conv].append(
                    {
                        "method": "mtrchain",
                        "detail": mot,
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )

    return dict(evidence)


def _connection_candidates(equipment: list[dict]) -> list[dict[str, Any]]:
    usable = [
        e
        for e in equipment
        if e.get("entry_anchor") and e.get("exit_anchor") and e.get("width")
    ]
    candidates: list[dict[str, Any]] = []
    inbound: dict[str, list] = defaultdict(list)

    for a in usable:
        for b in usable:
            if a["conveyor_tag"].upper() == b["conveyor_tag"].upper():
                continue
            d = _dist(a["exit_anchor"], b["entry_anchor"])
            wref = min(float(a["width"] or 1), float(b["width"] or 1))
            a_out = a.get("angle_out")
            if a_out is None:
                a_out = a.get("angle") or 0
            ang_err = _angle_delta(float(a_out), float(b.get("angle") or 0))
            if d > max(3.0 * wref, 1200.0):
                continue
            if d <= max(0.25 * wref, 50.0) and ang_err <= 15.0:
                level = "CONFIRMED"
            elif d <= max(1.0 * wref, 250.0) and ang_err <= 30.0:
                level = "HIGH-CONFIDENCE CANDIDATE"
            elif d <= max(3.0 * wref, 1200.0):
                level = "AMBIGUOUS"
            else:
                continue
            rec = {
                "from_conveyor": a["conveyor_tag"],
                "to_conveyor": b["conveyor_tag"],
                "exit_to_entry_distance": round(d, 3),
                "angle_delta_deg": round(ang_err, 2),
                "classification": level,
                "method": "geometry_exit_to_entry",
                "provenance": PROVENANCE_RUN_INFERRED,
                "note": "Not inferred from P-tag numerical order",
            }
            candidates.append(rec)
            inbound[b["conveyor_tag"].upper()].append(rec)

    for _tag, hits in inbound.items():
        strong = [h for h in hits if h["classification"] in {"CONFIRMED", "HIGH-CONFIDENCE CANDIDATE"}]
        if len(strong) > 1:
            for h in strong:
                h["classification"] = "AMBIGUOUS"
                h["ambiguity"] = f"{len(strong)} inbound geometric candidates"

    candidates.sort(key=lambda c: (c["classification"], c["exit_to_entry_distance"]))
    return candidates


def discover_equipment(
    run_dir: Path,
    machine: str,
    sawtooth: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fortna = run_dir / "FORTNA"
    conv_path, conv_src = resolve_asc(fortna, "Conveyor.asc", machine)
    if conv_path is None:
        raise FileNotFoundError(conv_path)

    word_map = _load_word_map(run_dir)
    mtrchain = _load_mtrchain(run_dir)
    _h, rows = read_asc(conv_path)

    mech_by_tag: dict[str, dict] = {}
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        tag = _clean(r.get("IO_Name")).upper()
        if tag not in mech_by_tag:
            mech_by_tag[tag] = r

    evidence = _controller_linked_tags(
        rows, machine, word_map, mtrchain, set(mech_by_tag)
    )

    # Always include saw-lane conveyors when Name embeds a P-tag (explicit)
    saw_conveyors: dict[str, str] = {}
    for lane in sawtooth.get("lanes") or []:
        c = (lane.get("conveyor") or "").upper()
        if c:
            saw_conveyors[c] = lane["name"]
            if c in mech_by_tag and c not in evidence:
                evidence[c] = [
                    {
                        "method": "saw_lane_name",
                        "detail": lane["name"],
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                ]
            elif c in mech_by_tag:
                evidence[c].append(
                    {
                        "method": "saw_lane_name",
                        "detail": lane["name"],
                        "provenance": PROVENANCE_RUN_EXPLICIT,
                    }
                )

    target_tags = sorted(evidence.keys())
    equipment: list[dict[str, Any]] = []

    for tag in target_tags:
        r = mech_by_tag.get(tag)
        if not r:
            equipment.append(
                {
                    "conveyor_tag": tag,
                    "equipment_type": None,
                    "placed": False,
                    "has_geometry": False,
                    "ownership_evidence": evidence.get(tag, []),
                    "provenance": PROVENANCE_ENGINEER_REQUIRED,
                    "note": "Referenced by CP4 RUN links but no mechanical Conveyor.asc row",
                }
            )
            continue

        name = _clean(r.get("IO_Name"))
        typ = _clean(r.get("Type")).upper()
        x, y = _f(r.get("X_cord")), _f(r.get("Y_cord"))
        ang, length, width = _f(r.get("Angle")), _f(r.get("Length")), _f(r.get("Width"))

        geom = None
        if build_equipment_geometry is not None:
            try:
                geom = build_equipment_geometry(r)
            except Exception:
                geom = None

        anchors = None
        angle_out = ang
        if geom and geom.get("entry") and geom.get("exit"):
            anchors = {"entry": geom["entry"], "exit": geom["exit"]}
            angle_out = geom.get("angle_out", ang)
        elif x is not None and y is not None and ang is not None and length and length > 0:
            anchors = _anchors(x, y, length, ang)

        motors = list(mtrchain.get(tag, []))
        mot_col = _clean(r.get("Motor"))
        if mot_col and mot_col not in motors:
            motors.append(mot_col)

        placed = anchors is not None
        equipment.append(
            {
                "conveyor_tag": name,
                "equipment_type": typ,
                "x": x,
                "y": y,
                "angle": ang,
                "angle_out": angle_out,
                "length": length,
                "width": width,
                "entry_anchor": anchors["entry"] if anchors else None,
                "exit_anchor": anchors["exit"] if anchors else None,
                "geometry": geom,
                "geometry_model": "infeed_origin_v1",
                "has_geometry": placed,
                "placed": placed,
                "motors": motors,
                "machine_name_field": _clean(r.get("Machine_Name")),
                "saw_lane": saw_conveyors.get(tag),
                "ownership_evidence": evidence.get(tag, []),
                "ownership_provenance": (
                    PROVENANCE_RUN_EXPLICIT
                    if evidence.get(tag)
                    else PROVENANCE_UNKNOWN
                ),
                "provenance": PROVENANCE_RUN_EXPLICIT,
            }
        )

    # Refine curve mates (same approach as CP2 geometry investigate)
    if build_equipment_geometry is not None:
        mate_entries = [
            (float(e["entry_anchor"]["x"]), float(e["entry_anchor"]["y"]))
            for e in equipment
            if e.get("entry_anchor")
        ]
        for e in equipment:
            if (e.get("equipment_type") or "").upper() not in {"CURVE", "TRIANG"}:
                continue
            r = mech_by_tag.get(e["conveyor_tag"].upper())
            if not r or not e.get("entry_anchor"):
                continue
            others = [
                p
                for p in mate_entries
                if abs(p[0] - float(e["entry_anchor"]["x"])) > 1e-6
                or abs(p[1] - float(e["entry_anchor"]["y"])) > 1e-6
            ]
            try:
                geom = build_equipment_geometry(r, mate_entries=others)
            except Exception:
                continue
            if geom and geom.get("entry") and geom.get("exit"):
                e["geometry"] = geom
                e["entry_anchor"] = geom["entry"]
                e["exit_anchor"] = geom["exit"]
                e["angle_out"] = geom.get("angle_out")
                e["has_geometry"] = True
                e["placed"] = True

    candidates = _connection_candidates(equipment)

    # Saw lane physical locate-ability via conveyor geometry
    saw_lane_geom = []
    for lane in sawtooth.get("lanes") or []:
        conv = (lane.get("conveyor") or "").upper()
        eq = next((e for e in equipment if e["conveyor_tag"].upper() == conv), None)
        saw_lane_geom.append(
            {
                "lane": lane["name"],
                "conveyor": conv or None,
                "conveyor_in_equipment": eq is not None,
                "has_geometry": bool(eq and eq.get("has_geometry")),
                "x": eq.get("x") if eq else None,
                "y": eq.get("y") if eq else None,
                "provenance": (
                    PROVENANCE_RUN_EXPLICIT
                    if eq and eq.get("has_geometry")
                    else (
                        PROVENANCE_ENGINEER_REQUIRED
                        if not conv
                        else PROVENANCE_UNKNOWN
                    )
                ),
                "note": (
                    "Lane can be located physically via its RUN conveyor geometry"
                    if eq and eq.get("has_geometry")
                    else "Lane conveyor geometry missing or conveyor not in CP4 equipment set"
                ),
            }
        )

    placed = sum(1 for e in equipment if e.get("placed"))
    unplaced = len(equipment) - placed
    class_counts = Counter(c["classification"] for c in candidates)

    equipment_doc = {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "RUN only — finished PLC4 L5X not read",
        "source_file": _rel(conv_path, run_dir),
        "source_resolution": conv_src,
        "geometry_model": "infeed_origin + fortna_physical_geometry (same as CP2)",
        "topology_rule": "P-tag numerical order is NEVER used as physical adjacency evidence.",
        "equipment": equipment,
        "saw_lane_geometry": saw_lane_geom,
        "connection_candidates": candidates,
        "counts": {
            "equipment": len(equipment),
            "placed": placed,
            "unplaced": unplaced,
            "with_xy": sum(
                1 for e in equipment if e.get("x") is not None and e.get("y") is not None
            ),
            "saw_lanes_with_geometry": sum(1 for s in saw_lane_geom if s["has_geometry"]),
            "saw_lanes_without_geometry": sum(
                1 for s in saw_lane_geom if not s["has_geometry"]
            ),
            "connection_candidates": len(candidates),
            "confirmed_connections": class_counts.get("CONFIRMED", 0),
            "high_confidence_candidates": class_counts.get("HIGH-CONFIDENCE CANDIDATE", 0),
            "ambiguous_connections": class_counts.get("AMBIGUOUS", 0),
        },
    }

    layout_metrics = {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "RUN only — finished PLC4 L5X not read",
        "geometry_model": "infeed_origin_v1",
        "topology_rule": "P-tag numerical order is NEVER used as physical adjacency evidence.",
        "placed": placed,
        "unplaced": unplaced,
        "equipment_total": len(equipment),
        "connection_candidates": {
            "total": len(candidates),
            "confirmed": class_counts.get("CONFIRMED", 0),
            "high_confidence": class_counts.get("HIGH-CONFIDENCE CANDIDATE", 0),
            "ambiguous": class_counts.get("AMBIGUOUS", 0),
        },
        "saw_lanes_with_geometry": sum(1 for s in saw_lane_geom if s["has_geometry"]),
        "saw_lanes_without_geometry": sum(
            1 for s in saw_lane_geom if not s["has_geometry"]
        ),
        "saw_lane_geometry_detail": saw_lane_geom,
        "provenance_mix": {
            "equipment_ownership": dict(
                Counter(e.get("ownership_provenance", PROVENANCE_UNKNOWN) for e in equipment)
            ),
            "connection_candidates": PROVENANCE_RUN_INFERRED,
            "saw_lane_geometry": dict(
                Counter(s.get("provenance", PROVENANCE_UNKNOWN) for s in saw_lane_geom)
            ),
        },
    }
    return equipment_doc, layout_metrics


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _provenance_mix(*docs: dict) -> Counter:
    mix: Counter = Counter()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("provenance",) and isinstance(v, str):
                    mix[v] += 1
                elif k.endswith("_provenance") and isinstance(v, str):
                    mix[v] += 1
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    for d in docs:
        walk(d)
    return mix


def build_report(
    machine: str,
    run_dir: Path,
    out_dir: Path,
    sawtooth: dict,
    vfd: dict,
    encoders: dict,
    tracking: dict,
    equipment: dict,
    layout: dict,
) -> str:
    mix = _provenance_mix(sawtooth, vfd, encoders, tracking, equipment, layout)
    eng = []
    for lane in sawtooth.get("lanes") or []:
        if lane.get("conveyor_provenance") == PROVENANCE_ENGINEER_REQUIRED:
            eng.append(f"Saw lane {lane['name']}: conveyor identity not in Name")
    for v in vfd.get("unknown_conveyor_mappings") or []:
        eng.append(f"VFD {v['vfd']}: no explicit RUN conveyor mapping (Mtrchain/Motor/saw)")
    for s in layout.get("saw_lane_geometry_detail") or []:
        if s.get("provenance") == PROVENANCE_ENGINEER_REQUIRED:
            eng.append(f"Saw lane {s['lane']}: cannot locate physically without conveyor")

    lines = [
        f"# CP4 Discovery Report — {machine}",
        "",
        f"Generated: { _ts() }",
        f"RUN dir: `{run_dir}`",
        f"Output: `{out_dir}`",
        f"Tar provenance (extract source only): `{TAR_PROVENANCE}`",
        "",
        "## Firewall / scope",
        "",
        "- **Finished PLC4 L5X was not read, parsed, or used.**",
        "- **CP4 PLC generation / autogen was not implemented.**",
        "- Discovery uses **CP4 RUN only** (controller-scoped overlays when present).",
        "",
        "## Executive summary",
        "",
        f"| Item | Count |",
        f"|------|------:|",
        f"| Mechanical equipment (CP4-linked) | {equipment['counts']['equipment']} |",
        f"| Placed (has geometry) | {layout['placed']} |",
        f"| Unplaced | {layout['unplaced']} |",
        f"| VFD device rows | {vfd['counts']['device_rows']} |",
        f"| Unique VFD bases | {vfd['counts']['unique_vfd_bases']} |",
        f"| VFD→conveyor explicit mappings | {vfd['counts']['mapped_to_conveyor_explicit']} |",
        f"| VFD unknown conveyor mapping | {vfd['counts']['unknown_conveyor_mapping']} |",
        f"| Sawtooth merges | {sawtooth['counts']['merges']} |",
        f"| Sawtooth lanes | {sawtooth['counts']['lanes']} |",
        f"| Saw lanes with conveyor in Name | {sawtooth['counts']['lanes_with_conveyor_in_name']} |",
        f"| Saw lanes with physical geometry | {layout['saw_lanes_with_geometry']} |",
        f"| Saw lanes without geometry | {layout['saw_lanes_without_geometry']} |",
        f"| Encoders | {encoders['counts']['encoders']} |",
        f"| Tracking tables with active rows | {tracking['counts']['tables_with_active_rows']} |",
        f"| SrtTrack active rows (all) | {tracking['counts']['srttrack_active_total']} |",
        f"| WCSEvents enabled | {tracking['counts']['wcs_events_enabled']} |",
        f"| Connection candidates | {layout['connection_candidates']['total']} |",
        "",
        "## Provenance mix",
        "",
        "Codes used on relationships: `RUN_EXPLICIT` | `RUN_INFERRED` | "
        "`ENGINEER_REQUIRED` | `UNKNOWN`.",
        "",
    ]
    for code, n in sorted(mix.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- **{code}**: {n}")
    lines += ["", "## ENGINEER_REQUIRED / gaps", ""]
    if eng:
        for item in eng:
            lines.append(f"- {item}")
    else:
        lines.append(
            "- No hard ENGINEER_REQUIRED gaps on saw-lane conveyor identity; "
            "review UNKNOWN VFD mappings and unplaced equipment before generation."
        )
        for v in vfd.get("unknown_conveyor_mappings") or []:
            lines.append(
                f"- UNKNOWN mapping: {v['vfd']} (no Mtrchain / Motor column / saw table link)"
            )

    lines += [
        "",
        "## Sawtooth",
        "",
        f"Controller overlay used for merges: "
        f"`{sawtooth['sources']['SawMerge']['path']}` "
        f"({sawtooth['sources']['SawMerge']['resolution']}).",
        f"Controller overlay used for lanes: "
        f"`{sawtooth['sources']['SawLane']['path']}` "
        f"({sawtooth['sources']['SawLane']['resolution']}).",
        "",
        "Lane identity is **not** inferred from LaneNdx or P-number order; conveyor "
        "comes from the explicit Name token (e.g. `LANE_0_P219` → `P219`).",
        "",
    ]
    for m in sawtooth.get("merges") or []:
        lines.append(
            f"- Merge **{m['name']}** motor_io=`{m['motor_io']}` "
            f"reservation=`{m['reservation']}` lanes={m['lanes']}"
        )
    for ln in sawtooth.get("lanes") or []:
        lines.append(
            f"- Lane **{ln['name']}** conveyor=`{ln.get('conveyor')}` "
            f"index={ln.get('lane_index')} pe=`{ln.get('photoeye')}` "
            f"drive=`{ln.get('drive')}` slice={ln.get('slice_seconds')}s "
            f"reserve={ln.get('reserve_seconds')}s"
        )

    lines += [
        "",
        "## VFD",
        "",
        "Scoped to ORNCCP4 via Machine_Name / EIP word map. Conveyor links only when "
        "Mtrchain, Motor column, or saw tables explicitly relate them.",
        "",
    ]
    for v in vfd.get("vfds") or []:
        lines.append(
            f"- **{v['vfd']}** devices={v['device_points']} "
            f"conveyors={v.get('conveyors')} "
            f"(prov={v.get('conveyor_mapping_provenance')}) "
            f"saw_lanes={v.get('saw_lanes')}"
        )

    lines += ["", "## Encoders", ""]
    for e in encoders.get("encoders") or []:
        assoc = ", ".join(
            f"{a['type']}→{a.get('to')}" for a in (e.get("associations") or [])
        ) or "none"
        lines.append(
            f"- **{e['encoder']}** io=`{e['io']}` tpf={e['ticks_per_foot']} "
            f"target_fpm={e['target_fpm']} enable=`{e['enable']}` "
            f"jamzone=`{e['jamzone']}` assoc=[{assoc}]"
        )

    lines += [
        "",
        "## Tracking / WCS (inventory only)",
        "",
    ]
    for k, text in (tracking.get("characterization") or {}).items():
        lines.append(f"- **{k}**: {text}")

    lines += [
        "",
        "## Equipment / layout",
        "",
        f"Geometry uses `fortna_physical_geometry` infeed-origin model (same as CP2). "
        f"Placed={layout['placed']} unplaced={layout['unplaced']}. "
        f"Saw lanes with geometry={layout['saw_lanes_with_geometry']} / "
        f"without={layout['saw_lanes_without_geometry']}.",
        "",
        "Connection candidates are geometric exit→entry only; P-number order is never "
        "used as adjacency evidence.",
        "",
        "## Artifacts",
        "",
        "- `equipment.json`",
        "- `vfd.json`",
        "- `sawtooth.json`",
        "- `encoders.json`",
        "- `tracking_wcs.json`",
        "- `layout_metrics.json`",
        "- `report.md`",
        "",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def discover(run_dir: Path, machine: str, out_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    machine = (machine or "ORNCCP4").strip().upper()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not (run_dir / "FORTNA").is_dir():
        raise FileNotFoundError(f"Missing FORTNA under {run_dir}")

    sawtooth = discover_sawtooth(run_dir, machine)
    vfd = discover_vfd(run_dir, machine, sawtooth)
    encoders = discover_encoders(run_dir, machine, sawtooth, vfd)
    tracking = discover_tracking_wcs(run_dir, machine)
    equipment, layout = discover_equipment(run_dir, machine, sawtooth)
    report = build_report(
        machine, run_dir, out_dir, sawtooth, vfd, encoders, tracking, equipment, layout
    )

    site_model = build_site_model(
        machine, run_dir, equipment, vfd, sawtooth, encoders, tracking, layout
    )
    unknowns = build_unknowns(equipment, vfd, sawtooth, encoders, tracking, layout)

    artifacts = {
        "equipment.json": equipment,
        "site_model.json": site_model,
        "vfd.json": vfd,
        "sawtooth.json": sawtooth,
        "encoders.json": encoders,
        "tracking_wcs.json": tracking,
        "layout_metrics.json": layout,
        "unknowns.json": unknowns,
    }
    for name, doc in artifacts.items():
        (out_dir / name).write_text(
            json.dumps(doc, indent=2, default=str), encoding="utf-8"
        )
    report = report.replace(
        "- `layout_metrics.json`\n- `report.md`",
        "- `layout_metrics.json`\n- `site_model.json`\n- `unknowns.json`\n- `report.md`",
    )
    # Ensure report lists required headline counts
    if "site_model.json" not in report:
        report = report.rstrip() + (
            "\n\n## Site model / unknowns\n\n"
            f"- Canonical site model: `site_model.json` "
            f"({site_model['counts'].get('conveyors', 0)} conveyors, "
            f"{site_model['counts'].get('relationships', 0)} relationships)\n"
            f"- Unknowns / gaps: `unknowns.json` "
            f"({unknowns['counts'].get('total', 0)} items)\n"
            "- Finished PLC4 L5X was **not** read.\n"
            "- Sawtooth PLC generation was **not** implemented.\n"
        )
    (out_dir / "report.md").write_text(report, encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "counts": {
            "equipment": equipment["counts"]["equipment"],
            "conveyors": site_model["counts"].get("conveyors", 0),
            "vfd_bases": vfd["counts"]["unique_vfd_bases"],
            "vfd_devices": vfd["counts"]["device_rows"],
            "saw_merges": sawtooth["counts"]["merges"],
            "saw_lanes": sawtooth["counts"]["lanes"],
            "encoders": encoders["counts"]["encoders"],
            "tracking_active_tables": tracking["counts"]["tables_with_active_rows"],
            "placed": layout["placed"],
            "unplaced": layout["unplaced"],
            "unknowns": unknowns["counts"].get("total", 0),
        },
        "artifacts": [str(out_dir / n) for n in list(artifacts) + ["report.md"]],
    }


def build_site_model(
    machine: str,
    run_dir: Path,
    equipment: dict,
    vfd: dict,
    sawtooth: dict,
    encoders: dict,
    tracking: dict,
    layout: dict,
) -> dict[str, Any]:
    """Canonical CP4 Site Model (discovery only — no PLC generation)."""
    conveyors = []
    for e in equipment.get("equipment") or []:
        tag = e.get("conveyor_tag") or e.get("tag") or e.get("conveyor")
        entry = e.get("entry_anchor") or e.get("entry")
        exit_pt = e.get("exit_anchor") or e.get("exit")
        conveyors.append(
            {
                "tag": tag,
                "type": e.get("equipment_type") or e.get("type"),
                "geometry": {
                    "x": e.get("x"),
                    "y": e.get("y"),
                    "angle": e.get("angle"),
                    "length": e.get("length"),
                    "width": e.get("width"),
                    "entry": entry,
                    "exit": exit_pt,
                },
                "has_geometry": bool(e.get("has_geometry") or (entry and exit_pt)),
                "placed": bool(e.get("placed")),
                "motors": e.get("motors") or [],
                "saw_lane": e.get("saw_lane"),
                "provenance": e.get("provenance") or e.get("ownership_provenance") or PROVENANCE_RUN_EXPLICIT,
                "controller": machine,
            }
        )
    relationships = []
    vfd_map = vfd.get("by_base") or vfd.get("vfds") or {}
    if isinstance(vfd_map, dict):
        for base, info in vfd_map.items():
            if not isinstance(info, dict):
                continue
            for conv in info.get("conveyors") or []:
                relationships.append(
                    {
                        "from": base,
                        "to": conv,
                        "kind": "vfd_to_conveyor",
                        "provenance": info.get("provenance") or PROVENANCE_RUN_EXPLICIT,
                    }
                )
    if isinstance(vfd.get("mappings"), list):
        for m in vfd["mappings"]:
            relationships.append(
                {
                    "from": m.get("vfd") or m.get("from"),
                    "to": m.get("conveyor") or m.get("to"),
                    "kind": "vfd_to_conveyor",
                    "provenance": m.get("provenance") or PROVENANCE_RUN_EXPLICIT,
                }
            )
    for lane in sawtooth.get("lanes") or []:
        if lane.get("conveyor"):
            relationships.append(
                {
                    "from": lane.get("name"),
                    "to": lane.get("conveyor"),
                    "kind": "saw_lane_to_conveyor",
                    "provenance": lane.get("conveyor_provenance") or PROVENANCE_RUN_EXPLICIT,
                }
            )
        if lane.get("photoeye"):
            relationships.append(
                {
                    "from": lane.get("name"),
                    "to": lane.get("photoeye"),
                    "kind": "saw_lane_to_pe",
                    "provenance": PROVENANCE_RUN_EXPLICIT,
                }
            )
        drive = lane.get("drive") or lane.get("drive/vfd") or lane.get("disable_io")
        if drive:
            relationships.append(
                {
                    "from": lane.get("name"),
                    "to": drive,
                    "kind": "saw_lane_to_drive",
                    "provenance": PROVENANCE_RUN_EXPLICIT,
                }
            )
    for enc in encoders.get("encoders") or []:
        name = enc.get("encoder") or enc.get("name")
        for tgt in enc.get("associations") or enc.get("linked") or []:
            relationships.append(
                {
                    "from": name,
                    "to": tgt.get("target") if isinstance(tgt, dict) else tgt,
                    "kind": "encoder_association",
                    "provenance": (tgt.get("provenance") if isinstance(tgt, dict) else None)
                    or enc.get("provenance")
                    or PROVENANCE_UNKNOWN,
                }
            )

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "CP4 RUN only — finished PLC4 L5X not read; no sawtooth PLC generation",
        "run_dir": str(run_dir),
        "counts": {
            "conveyors": len(conveyors),
            "vfd_bases": (vfd.get("counts") or {}).get("unique_vfd_bases", 0),
            "encoders": (encoders.get("counts") or {}).get("encoders", 0),
            "saw_merges": (sawtooth.get("counts") or {}).get("merges", 0),
            "saw_lanes": (sawtooth.get("counts") or {}).get("lanes", 0),
            "relationships": len(relationships),
            "placed": layout.get("placed", 0),
            "unplaced": layout.get("unplaced", 0),
        },
        "conveyors": conveyors,
        "sawtooth": {
            "merges": sawtooth.get("merges") or [],
            "lanes": sawtooth.get("lanes") or [],
        },
        "vfds": vfd,
        "encoders": encoders.get("encoders") or [],
        "tracking_wcs_summary": {
            "tables_with_active_rows": (tracking.get("counts") or {}).get(
                "tables_with_active_rows", 0
            ),
            "characterization": tracking.get("characterization") or {},
        },
        "relationships": relationships,
        "controller_area_safety_evidence": {
            "note": "Area/ES zone names are not inventable from RUN alone for CP4 — ENGINEER_CONFIGURED required before generation",
            "provenance": PROVENANCE_UNKNOWN,
        },
    }


def build_unknowns(
    equipment: dict,
    vfd: dict,
    sawtooth: dict,
    encoders: dict,
    tracking: dict,
    layout: dict,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for e in equipment.get("equipment") or []:
        tag = e.get("conveyor_tag") or e.get("tag") or e.get("conveyor")
        entry = e.get("entry_anchor") or e.get("entry")
        exit_pt = e.get("exit_anchor") or e.get("exit")
        if e.get("has_geometry") is False or (not entry or not exit_pt):
            if not e.get("placed"):
                items.append(
                    {
                        "kind": "geometry",
                        "tag": tag,
                        "reason": "missing entry/exit geometry or unplaced",
                        "provenance": PROVENANCE_UNKNOWN,
                    }
                )
    unk_vfd = (vfd.get("counts") or {}).get("unknown_conveyor_mapping", 0)
    if unk_vfd:
        for row in vfd.get("unknown_mappings") or vfd.get("devices") or []:
            if isinstance(row, dict) and (
                row.get("conveyors") in (None, [], "") or row.get("unknown")
            ):
                items.append(
                    {
                        "kind": "vfd_mapping",
                        "tag": row.get("name") or row.get("vfd") or row.get("base"),
                        "reason": "VFD without explicit conveyor mapping",
                        "provenance": PROVENANCE_UNKNOWN,
                    }
                )
    for lane in sawtooth.get("lanes") or []:
        if not lane.get("conveyor"):
            items.append(
                {
                    "kind": "saw_lane",
                    "tag": lane.get("name"),
                    "reason": "lane missing conveyor identity",
                    "provenance": PROVENANCE_UNKNOWN,
                }
            )
    for enc in encoders.get("encoders") or []:
        assoc = enc.get("associations") or enc.get("linked") or []
        if not assoc:
            items.append(
                {
                    "kind": "encoder",
                    "tag": enc.get("encoder") or enc.get("name"),
                    "reason": "encoder has no explicit sawtooth/VFD association",
                    "provenance": PROVENANCE_UNKNOWN,
                }
            )
    # Area / ES always unknown from RUN for discovery freeze
    items.append(
        {
            "kind": "area_es",
            "tag": "*",
            "reason": "Area / ES zone not recoverable from CP4 RUN — engineer configuration required before generation",
            "provenance": PROVENANCE_UNKNOWN,
        }
    )
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {
        "generated_at": _ts(),
        "source_of_truth": "CP4 RUN discovery gaps — finished PLC4 not consulted",
        "counts": {"total": len(items), "by_kind": by_kind},
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 RUN discovery (no PLC generation)")
    ap.add_argument("--run-dir", required=True, help="Path to RUN root (contains FORTNA/)")
    ap.add_argument("--machine", default="ORNCCP4", help="Controller name (default ORNCCP4)")
    ap.add_argument("--out", required=True, help="Output directory for discovery JSON/md")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()

    result = discover(run_dir, args.machine, out_dir)
    print(json.dumps({"status": "ok", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
