#!/usr/bin/env python3
"""Generic sorter / tracking / WCS discovery from a FortnaPlus RUN extract.

Inventory + subsystem skeleton only. Does NOT generate PLC / L5X.
Does NOT read finished PLC4/PLC5 reference files.

Usage:
  python tools/scripts/fortna_sorter_discovery.py \\
    --run-dir workspace/cp4-run/RUN \\
    --machine ORNCCP4 \\
    --out exports/sorter-research

  # Emit only subsystem_model.json
  python tools/scripts/fortna_sorter_discovery.py \\
    --run-dir workspace/cp4-run/RUN --machine ORNCCP4 \\
    --out exports/sorter-research --subsystem-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402

PROV_RUN = "RUN_EXPLICIT"
PROV_DERIVED = "RUN_DERIVED"
PROV_UNKNOWN = "UNKNOWN"
PROV_ENGINEER = "ENGINEER_REQUIRED"

BLANK = {
    "",
    "N/A",
    "INVALID",
    "NONE",
    "~",
    "N/A~",
    "n/a",
    "Invalid",
    "RECZERO",
    "==inactive==",
}
PLACEHOLDER_PREFIXES = ("===",)


# Basename patterns (no machine overlay suffix). Scanned under FORTNA/ and PROJECT/.
TABLE_PATTERNS: list[tuple[str, str]] = [
    # (glob / exact basename class, category)
    ("Sorters.asc", "sorter_config"),
    ("Encoders.asc", "encoder"),
    ("SrtTrack1.asc", "srt_track"),
    ("SrtTrack2.asc", "srt_track"),
    ("SrtTrack3.asc", "srt_track"),
    ("SrtTrack4.asc", "srt_track"),
    ("SrtTrack5.asc", "srt_track"),
    ("XfrTrack.asc", "xfr_track"),
    ("MsgTrack.asc", "msg_track"),
    ("MsgWCS.asc", "msg_wcs"),
    ("WCSEvents.asc", "wcs_events"),
    ("wcsAlarm.asc", "wcs_lookup"),
    ("wcsSeverity.asc", "wcs_lookup"),
    ("SrtAppControl.asc", "sorter_app"),
    ("SrtScanBoss.asc", "sorter_scan"),
    ("SrtZoneLane.asc", "sorter_lane"),
    ("SrtHrtBeat.asc", "sorter_comm"),
    ("SrtRndRobin.asc", "sorter_assign"),
    ("SrtLaneNotAvail.asc", "sorter_assign"),
    ("SrtBadGapCnfg.asc", "sorter_gap"),
    ("SrtSimConfig.asc", "sorter_sim"),
    ("SrtCommMsgMatch.asc", "sorter_comm"),
    ("SrtScanSts.asc", "sorter_lookup"),
    ("SrtDevice1.asc", "sorter_device"),
    ("SrtDevice2.asc", "sorter_device"),
    ("SrtDevice3.asc", "sorter_device"),
    ("SrtDevice4.asc", "sorter_device"),
    ("SrtDevice5.asc", "sorter_device"),
    ("SortBuff.asc", "sort_buffer"),
    ("SortData.asc", "sort_data"),
    ("LogSort.asc", "sort_log"),
    ("SortSimScans1.asc", "sorter_sim"),
    ("SortSimScans2.asc", "sorter_sim"),
    ("SortSimScans3.asc", "sorter_sim"),
    ("SortSimScans4.asc", "sorter_sim"),
    ("SortSimScans5.asc", "sorter_sim"),
    ("Inpoints.asc", "sorter_induct"),
    ("Outpoints.asc", "sorter_divert"),
    ("ScnScanDevice.asc", "scanner"),
    ("ScnScanZone.asc", "scanner"),
    ("Mtrchain.asc", "motor_chain"),
    ("XfRouteBoss.asc", "xfr_route"),
    ("XfRouteTable.asc", "xfr_route"),
    ("XfrDevice.asc", "xfr_device"),
    ("XfrSimScans1.asc", "xfr_sim"),
    ("XfrSimScans2.asc", "xfr_sim"),
    ("XfrSimScans3.asc", "xfr_sim"),
    ("XfrSimScans4.asc", "xfr_sim"),
    ("XfrSimScans5.asc", "xfr_sim"),
    ("MergeRoute.asc", "merge_route"),
    ("CombLane.asc", "lane"),
    ("ZipperLane.asc", "lane"),
    ("ZprLaneState.asc", "lane_lookup"),
    ("ZprStatusMsgs.asc", "lane_lookup"),
    ("SawLane.asc", "sawtooth_lane"),
    ("HSSawLane.asc", "sawtooth_lane"),
    ("MsgMap.asc", "comm_map"),
]


NAME_COLS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "Sorters.asc": ("Sorter Name",),
    "Encoders.asc": ("Encoder Name",),
    "MsgWCS.asc": ("Destination",),
    "WCSEvents.asc": ("EventName",),
    "SortBuff.asc": ("Sorter",),
    "SortData.asc": ("Sorter",),
    "Inpoints.asc": ("Inpoint Name", "Sorter"),
    "Outpoints.asc": ("Outpoint Name", "Sorter"),
    "ScnScanDevice.asc": ("Name",),
    "ScnScanZone.asc": ("Name",),
    "Mtrchain.asc": ("Motor_Name",),
    "MsgMap.asc": ("Message_Name",),
    "wcsAlarm.asc": ("Alarm_Category",),
    "wcsSeverity.asc": ("wcsSeverity",),
    "SrtScanSts.asc": ("Scan_Status",),
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip().strip('"')


def _meaningful(v: Any) -> bool:
    s = _clean(v)
    if not s:
        return False
    if s.upper() in {b.upper() for b in BLANK}:
        return False
    if any(s.startswith(p) for p in PLACEHOLDER_PREFIXES):
        return False
    return True


def _read_machine(run_dir: Path, explicit: str = "") -> str:
    if explicit:
        return explicit.strip()
    cfg = run_dir / "project.cfg"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if "MACHINENAME" in line.upper() or "MachineName" in line:
                parts = re.split(r"[=:]", line, maxsplit=1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    # Display.config.* fallback
    for p in sorted(run_dir.glob("Display.config.*")):
        suf = p.name.split("Display.config.", 1)[-1]
        if suf and suf.upper() not in ("CP1", "CP2"):
            return suf
    return ""


def resolve_asc(folder: Path, basename: str, machine: str) -> tuple[Path | None, str]:
    """Prefer File.asc.MACHINE overlay over File.asc."""
    if machine:
        overlay = folder / f"{basename}.{machine}"
        if overlay.is_file() and overlay.stat().st_size > 0:
            return overlay, "controller_overlay"
    base = folder / basename
    if base.is_file():
        return base, "base"
    if machine:
        overlay = folder / f"{basename}.{machine}"
        if overlay.is_file():
            return overlay, "controller_overlay_empty"
    return None, "missing"


def _name_cols(basename: str, headers: list[str]) -> list[str]:
    preferred = NAME_COLS_BY_TABLE.get(basename)
    if preferred:
        return [c for c in preferred if c in headers] or list(preferred)
    for c in (
        "Name",
        "Sorter Name",
        "Encoder Name",
        "EventName",
        "Message_Name",
        "Destination",
    ):
        if c in headers:
            return [c]
    return [headers[0]] if headers else []


def _row_active(basename: str, row: dict[str, str], name_cols: list[str]) -> bool:
    if basename == "MsgWCS.asc":
        dest = _clean(row.get("Destination"))
        return dest.startswith("/") or _meaningful(dest)
    if basename == "SortBuff.asc":
        return _meaningful(row.get("Sorter")) and _clean(row.get("Index")) not in ("", "0")
    if basename == "Inpoints.asc":
        return _meaningful(row.get("Sorter")) and _meaningful(
            row.get("Induct I/O Name") or row.get("Inpoint Name")
        )
    if basename == "Outpoints.asc":
        return _meaningful(row.get("Sorter")) and _meaningful(row.get("Outpoint Name"))
    if basename == "Mtrchain.asc":
        return _meaningful(row.get("Motor_Name"))
    named = any(_meaningful(row.get(c)) for c in name_cols)
    if not named:
        return False
    # Sorters / Encoders: require real device-ish name
    if basename in ("Sorters.asc", "Encoders.asc"):
        primary = _clean(row.get(name_cols[0]))
        return _meaningful(primary)
    return True


def inventory_table(
    run_dir: Path,
    folder: Path,
    basename: str,
    category: str,
    machine: str,
) -> dict[str, Any]:
    path, resolution = resolve_asc(folder, basename, machine)
    exists = path is not None and path.is_file()
    size = path.stat().st_size if exists else 0
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    if exists and size > 0:
        headers, rows = read_asc(path)
    name_cols = _name_cols(basename, headers)
    active = [r for r in rows if _row_active(basename, r, name_cols)]
    samples: list[dict[str, str]] = []
    for r in active[:6]:
        sample: dict[str, str] = {}
        for c in name_cols:
            sample[c] = _clean(r.get(c))
        # Relationship / config highlights
        for c in (
            "Encoder ioName",
            "Encoder Name",
            "Encoder I/O",
            "EnableBit",
            "Jamzone",
            "Machine",
            "AppSorter",
            "ScanZone",
            "ScanZoneID",
            "SorterLane",
            "HostZone",
            "Lane",
            "ConfirmScan",
            "WCSEnable",
            "WCSDestination",
            "WCSCategory",
            "Destination",
            "ControlMachine",
            "Ticks Per Foot",
            "Target FPM",
            "Enabled",
            "FullClearTimer",
            "BossRecord",
            "Route",
            "ScanZone",
            "CrrMsgTable",
            "DcmMsgTable",
        ):
            if c in r and c not in sample:
                val = _clean(r.get(c))
                if _meaningful(val) or (c == "Destination" and val.startswith("/")):
                    sample[c] = val
        samples.append(sample)

    try:
        rel = path.relative_to(run_dir).as_posix() if path else ""
    except ValueError:
        rel = str(path) if path else ""

    confidence = "high" if exists and size > 0 else ("medium" if exists else "none")
    if exists and size > 0 and not active:
        confidence = "schema_only"

    return {
        "table": basename,
        "category": category,
        "path": rel,
        "resolution": resolution,
        "exists": exists,
        "byte_size": size,
        "row_count": len(rows),
        "active_rows": len(active),
        "headers": headers,
        "name_columns": name_cols,
        "samples": samples,
        "confidence": confidence,
        "provenance": PROV_RUN if exists else PROV_UNKNOWN,
    }


def _collect_extra_matches(folder: Path, already: set[str]) -> list[tuple[str, str]]:
    """Catch additional Srt*/Xfr*/Msg*/Sort*/WCS* tables not in the fixed list."""
    extras: list[tuple[str, str]] = []
    if not folder.is_dir():
        return extras
    rx = re.compile(
        r"^(Srt|Srtr|Sort|Xfr|XfRoute|MsgTrack|MsgWCS|WCS|wcs|Encoders|Sorters|"
        r"CombLane|ZipperLane|MergeRoute|SawLane|HSSawLane)",
        re.I,
    )
    for p in sorted(folder.glob("*.asc")):
        if p.name.lower().startswith("old."):
            continue
        if p.name in already:
            continue
        if rx.match(p.name):
            cat = "related"
            low = p.name.lower()
            if low.startswith("msg"):
                cat = "comm_msg"
            elif low.startswith(("xfr", "xfroute")):
                cat = "xfr_config"
            elif low.startswith(("srt", "srtr", "sort")):
                cat = "sorter_related"
            extras.append((p.name, cat))
    return extras


def inventory_run(run_dir: Path, machine: str) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fortna = run_dir / "FORTNA"
    project = run_dir / "PROJECT"
    tables: list[dict[str, Any]] = []
    seen: set[str] = set()

    for basename, category in TABLE_PATTERNS:
        for folder in (fortna, project):
            if not folder.is_dir():
                continue
            # Only inventory in FORTNA for primary equipment tables; PROJECT for Xfr* wizard etc.
            if folder.name == "PROJECT" and not basename.startswith(("Xfr", "Srtr", "Sorter")):
                # Skip most PROJECT unless it's sorter wizard / xfr config
                if basename not in (
                    "SorterSfgScrn.asc",
                ):
                    continue
            inv = inventory_table(run_dir, folder, basename, category, machine)
            key = inv["table"] + "|" + (inv["path"] or folder.name)
            if inv["exists"] and key not in seen:
                tables.append(inv)
                seen.add(key)
                break
        else:
            # Record missing FORTNA primary
            if fortna.is_dir():
                inv = inventory_table(run_dir, fortna, basename, category, machine)
                if inv["table"] not in {t["table"] for t in tables}:
                    tables.append(inv)

    # PROJECT Xfr*/Srtr* extras + FORTNA extras
    for folder in (fortna, project):
        extras = _collect_extra_matches(
            folder, {t["table"] for t in tables if t.get("path", "").startswith(folder.name)}
        )
        for basename, category in extras:
            inv = inventory_table(run_dir, folder, basename, category, machine)
            if inv["exists"] and inv["table"] not in {t["table"] for t in tables}:
                # Prefer already-listed; extras fill gaps only
                tables.append(inv)

    # Also explicitly inventory key PROJECT Xfr config tables
    if project.is_dir():
        for basename in (
            "XfrBoss.asc",
            "XfrConfig.asc",
            "XfrTree.asc",
            "XfrTrig.asc",
            "XfrCheckSet.asc",
            "XfrGoSet.asc",
            "SorterSfgScrn.asc",
            "SrtrWizardSteps.asc",
            "PrintApplySrtrLn.asc",
        ):
            if basename in {t["table"] for t in tables}:
                continue
            inv = inventory_table(run_dir, project, basename, "project_config", machine)
            if inv["exists"]:
                tables.append(inv)

    tables.sort(key=lambda t: (t.get("category") or "", t.get("table") or ""))
    core = [
        "SrtTrack1.asc",
        "SrtTrack2.asc",
        "SrtTrack3.asc",
        "SrtTrack4.asc",
        "SrtTrack5.asc",
        "XfrTrack.asc",
        "MsgTrack.asc",
        "MsgWCS.asc",
        "WCSEvents.asc",
        "Sorters.asc",
        "Encoders.asc",
    ]
    by_name = {t["table"]: t for t in tables}
    return {
        "generated_at": _ts(),
        "run_dir": str(run_dir),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC L5X not read",
        "table_count": len(tables),
        "tables_with_active_rows": sum(1 for t in tables if t.get("active_rows", 0) > 0),
        "tables": tables,
        "core_table_coverage": {
            "required": core,
            "present": [c for c in core if c in by_name],
            "missing": [c for c in core if c not in by_name],
            "complete": all(c in by_name for c in core),
        },
        "site_forge_code": site_forge_code_inventory(),
    }


def site_forge_code_inventory() -> dict[str, Any]:
    """Static inventory of Site Forge sorter-related scripts/libraries (no L5X parse)."""
    return {
        "scripts": [
            {
                "path": "tools/scripts/fortna_sorter_discovery.py",
                "role": "RUN sorter/track/WCS discovery",
                "generates_l5x": False,
            },
            {
                "path": "tools/scripts/fortna_sorter_build.py",
                "role": "Configure gold Sorter_Track_Program.L5X (divert limit + token rename)",
                "generates_l5x": True,
                "generic": False,
            },
            {
                "path": "tools/scripts/fortna_mhs_sorter.py",
                "role": "MHS Non-Con / FMS shoe-sorter guideline scaffolds",
                "generates_l5x": True,
                "generic": False,
            },
            {
                "path": "tools/scripts/fortna_cp4_discovery.py",
                "role": "CP4 blind discovery includes discover_tracking_wcs()",
                "generates_l5x": False,
            },
            {
                "path": "tools/scripts/fortna_autogen.py",
                "role": "Optional pack merge for Sorter_Track / WCS / ShippingSorter",
                "generates_l5x": True,
                "generic": False,
            },
            {
                "path": "tools/scripts/fortna_equipment_plan.py",
                "role": "Tar equipment plan flags sorter_track_pack candidate",
                "generates_l5x": False,
            },
            {
                "path": "tools/scripts/fortna_asc.py",
                "role": "ASC parse; SORT/DIVERT device categorization",
                "generates_l5x": False,
            },
        ],
        "libraries": [
            {
                "path": "tools/libraries/programs/Sorter_Track_Program.L5X",
                "role": "Gold Sorter_Track program pack (site-fixed PLC5 pattern — not generic)",
                "generic": False,
            },
            {
                "path": "tools/libraries/programs/WCS_Interface_TCP_IP_Program.L5X",
                "role": "Gold WCS TCP/IP interface pack",
                "generic": False,
            },
            {
                "path": "tools/libraries/programs/ShippingSorter_Area_L3_Program.L5X",
                "role": "Gold ShippingSorter Area L3 pack",
                "generic": False,
            },
            {
                "path": "tools/libraries/TRK_Divert_WaveFunction_AOI.L5X",
                "role": "TRK_Divert_WaveFunction AOI",
                "generic": True,
            },
            {
                "path": "tools/libraries/Enc_Routine_ST.L5X",
                "role": "Encoder routine ST pattern stub",
                "generic": False,
            },
        ],
        "ui_notes": [
            "docs/SORTER_BUILD_UI_REVERT.md — sorter build UI demo-reverted; sorter_build fields remain in autogen",
        ],
    }


def _field(value: Any, source: str, provenance: str = PROV_RUN) -> dict[str, Any]:
    return {"value": value, "source": source, "provenance": provenance}


AUTH_PROVEN = "PROVEN"
AUTH_DERIVED = "DERIVED"
AUTH_REVIEW = "REVIEW_REQUIRED"
AUTH_UNKNOWN = "UNKNOWN"


def _authority(value: Any, *, blank_is: str = AUTH_UNKNOWN) -> str:
    """Map a RUN cell to UI/model field authority (not PLC generation status)."""
    if not _meaningful(value):
        return blank_is
    s = _clean(value)
    if s.upper() in {"INVALID", "N/A", "NONE", "N/A~"}:
        return AUTH_REVIEW
    return AUTH_PROVEN


def iter_active_table_rows(
    run_dir: Path,
    basename: str,
    machine: str,
) -> list[dict[str, str]]:
    """Full active rows for a FORTNA table (not sample-capped inventory)."""
    run_dir = Path(run_dir)
    fortna = run_dir / "FORTNA"
    if not fortna.is_dir():
        return []
    path, _resolution = resolve_asc(fortna, basename, machine)
    if path is None or not path.is_file() or path.stat().st_size <= 0:
        return []
    headers, rows = read_asc(path)
    name_cols = _name_cols(basename, headers)
    return [r for r in rows if _row_active(basename, r, name_cols)]


def _conveyor_io_names(run_dir: Path, machine: str) -> set[str]:
    """Active Conveyor.IO_Name set (for validating EXPLICIT refs)."""
    fortna = Path(run_dir) / "FORTNA"
    path, _ = resolve_asc(fortna, "Conveyor.asc", machine)
    if path is None or not path.is_file() or path.stat().st_size <= 0:
        return set()
    _headers, rows = read_asc(path)
    out: set[str] = set()
    for r in rows:
        name = _clean(r.get("IO_Name") or r.get("Name"))
        if _meaningful(name):
            out.add(name.upper())
    return out


def _mtrchain_index(
    run_dir: Path, machine: str
) -> dict[str, dict[str, str]]:
    rows = iter_active_table_rows(run_dir, "Mtrchain.asc", machine)
    return {
        _clean(r.get("Motor_Name")).upper(): r
        for r in rows
        if _meaningful(r.get("Motor_Name"))
    }


def _motor_candidates_for_enable_bit(enable_bit: str) -> list[str]:
    """Generic EnableBit → Motor_Name candidates (no numeric-suffix guessing).

    Exact match first. If the bit ends with ``_AUX``, also try stem+``_EN`` and
    bare stem — only usable when those names exist as Conveyor IO *and* Mtrchain
    Motor_Name (caller enforces).
    """
    en = _clean(enable_bit)
    if not en:
        return []
    cands = [en]
    upper = en.upper()
    if upper.endswith("_AUX") and len(en) > 4:
        stem = en[:-4]
        cands.extend([f"{stem}_EN", stem])
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        key = c.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def resolve_tracking_conveyor_for_encoder(
    enable_bit: str,
    *,
    mtr_by_name: dict[str, dict[str, str]],
    conveyor_io: set[str],
) -> dict[str, Any]:
    """Encoder.EnableBit → Mtrchain.Motor_Chained* conveyors.

    PROVEN when EnableBit equals Motor_Name exactly.
    DERIVED when ``*_AUX`` pairs to a verified ``*_EN``/stem Motor_Name that
    exists in both Conveyor and Mtrchain (Fortna VFD aux/enable pairing).
    Never ENC### → P### by digit match.
    """
    enable = _clean(enable_bit)
    empty = {
        "conveyors": [],
        "motor_name": "",
        "authority": AUTH_UNKNOWN,
        "path": "",
    }
    if not _meaningful(enable):
        return empty
    candidates = _motor_candidates_for_enable_bit(enable)
    for i, cand in enumerate(candidates):
        key = cand.upper()
        if key not in mtr_by_name:
            continue
        if key not in conveyor_io and i > 0:
            # Derived candidates must be real Conveyor IO points.
            continue
        if i > 0 and enable.upper() not in conveyor_io:
            # EnableBit itself should also resolve as Conveyor IO (schema EXPLICIT).
            continue
        row = mtr_by_name[key]
        chained: list[str] = []
        for col in (
            "Motor_Chained1",
            "Motor_Chained2",
            "Motor_Chained3",
            "Motor_Chained4",
            "Motor_Chained5",
        ):
            v = _clean(row.get(col))
            if _meaningful(v) and v.upper() != "INVALID" and v.upper() in conveyor_io:
                chained.append(v)
        if not chained:
            continue
        auth = AUTH_PROVEN if i == 0 else AUTH_DERIVED
        path = (
            f"Encoders.EnableBit={enable} → Mtrchain.Motor_Name={cand} → Motor_Chained*"
            if i == 0
            else (
                f"Encoders.EnableBit={enable} → pair Motor_Name={cand} "
                f"(Conveyor+Mtrchain) → Motor_Chained*"
            )
        )
        return {
            "conveyors": chained,
            "motor_name": cand,
            "authority": auth,
            "path": path,
        }
    return empty


def _index_outpoints_by_lane(
    out_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Lane/Outpoint Name → first Outpoints row (unique lane names expected)."""
    by_lane: dict[str, dict[str, str]] = {}
    for r in out_rows:
        lane = _clean(r.get("Outpoint Name"))
        if not _meaningful(lane):
            continue
        key = lane.upper()
        if key not in by_lane:
            by_lane[key] = r
    return by_lane


def _index_inpoints_by_sorter(
    in_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    by: dict[str, list[dict[str, str]]] = {}
    for r in in_rows:
        sorter = _clean(r.get("Sorter"))
        if not _meaningful(sorter):
            continue
        by.setdefault(sorter.upper(), []).append(r)
    return by


def build_divert_rows(
    zone_rows: list[dict[str, str]],
    *,
    outpoints_by_lane: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """SrtZoneLane topology + Outpoints.Outpoint I/O when lane join proves output."""
    outpoints_by_lane = outpoints_by_lane or {}
    out: list[dict[str, Any]] = []
    for idx, z in enumerate(zone_rows):
        name = _clean(z.get("Name"))
        lane = _clean(z.get("Lane"))
        if not _meaningful(name) and not _meaningful(lane):
            continue
        enable_sig = _clean(z.get("LaneEnableSignal"))
        host = _clean(z.get("HostZone"))
        app = _clean(z.get("AppSorter"))
        enabled = _clean(z.get("Enabled"))
        topology_ok = _meaningful(lane) or _meaningful(host)
        timer = _clean(z.get("FullClearTimer"))

        divert_io_value = ""
        divert_io_auth = AUTH_REVIEW
        divert_io_source = "FORTNA/SrtZoneLane.asc LaneEnableSignal"
        divert_io_prov = PROV_ENGINEER
        section_sorter = ""
        outpoint_number = ""
        outpoint_location = ""
        verify_io = ""
        out_timer = ""

        op = outpoints_by_lane.get(lane.upper()) if lane else None
        if op:
            section_sorter = _clean(op.get("Sorter"))
            outpoint_number = _clean(op.get("Outpoint Number"))
            outpoint_location = _clean(op.get("Outpoint Location"))
            verify_io = _clean(op.get("Verify I/O Name"))
            out_timer = _clean(op.get("Full_Clr_Timer_Name"))
            op_io = _clean(op.get("Outpoint I/O Name"))
            if _meaningful(op_io) and op_io.upper() != "INVALID":
                divert_io_value = op_io
                divert_io_auth = AUTH_PROVEN
                divert_io_source = (
                    "FORTNA/Outpoints.asc Outpoint I/O Name "
                    "(join Outpoint Name == SrtZoneLane.Lane)"
                )
                divert_io_prov = PROV_RUN
            elif _meaningful(enable_sig) and enable_sig.upper() != "INVALID":
                divert_io_value = enable_sig
                divert_io_auth = AUTH_PROVEN
                divert_io_prov = PROV_RUN
            else:
                divert_io_value = op_io or enable_sig or "INVALID"
                divert_io_auth = AUTH_REVIEW
        elif _meaningful(enable_sig) and enable_sig.upper() != "INVALID":
            divert_io_value = enable_sig
            divert_io_auth = AUTH_PROVEN
            divert_io_prov = PROV_RUN
        else:
            divert_io_value = enable_sig or "INVALID"
            divert_io_auth = AUTH_REVIEW

        # Confirm / divert PE: Verify I/O only counts when distinct from divert output
        # (sites often mirror solenoid names into Verify I/O — that is not a PE).
        divert_pe = ""
        divert_pe_auth = AUTH_UNKNOWN
        divert_pe_source = "no distinct PE on SrtZoneLane/Outpoints"
        divert_pe_prov = PROV_UNKNOWN
        if (
            _meaningful(verify_io)
            and verify_io.upper() != "INVALID"
            and verify_io.upper() != _clean(divert_io_value).upper()
        ):
            divert_pe = verify_io
            divert_pe_auth = AUTH_PROVEN
            divert_pe_source = "FORTNA/Outpoints.asc Verify I/O Name (≠ Outpoint I/O)"
            divert_pe_prov = PROV_RUN
        elif _meaningful(timer) or _meaningful(out_timer):
            divert_pe_auth = AUTH_REVIEW
            divert_pe_source = (
                "FullClearTimer / Full_Clr_Timer_Name are timer names, not PE proof"
            )
            divert_pe_prov = PROV_ENGINEER

        out.append(
            {
                "name": _field(name, "FORTNA/SrtZoneLane.asc"),
                "enabled": _field(enabled, "FORTNA/SrtZoneLane.asc"),
                "app_sorter": _field(app, "FORTNA/SrtZoneLane.asc"),
                "lane": _field(lane, "FORTNA/SrtZoneLane.asc"),
                "host_zone": _field(host, "FORTNA/SrtZoneLane.asc"),
                "full_clear_timer": _field(timer, "FORTNA/SrtZoneLane.asc"),
                "lane_enable_signal": _field(enable_sig, "FORTNA/SrtZoneLane.asc"),
                "divert_output_io": _field(
                    divert_io_value, divert_io_source, divert_io_prov
                ),
                "divert_pe": _field(divert_pe, divert_pe_source, divert_pe_prov),
                "sorter_section": _field(
                    section_sorter,
                    "FORTNA/Outpoints.asc Sorter" if section_sorter else "unjoined",
                    PROV_RUN if section_sorter else PROV_UNKNOWN,
                ),
                "outpoint_number": _field(
                    outpoint_number,
                    "FORTNA/Outpoints.asc",
                    PROV_RUN if outpoint_number else PROV_UNKNOWN,
                ),
                "outpoint_location": _field(
                    outpoint_location,
                    "FORTNA/Outpoints.asc Outpoint Location",
                    PROV_RUN if outpoint_location else PROV_UNKNOWN,
                ),
                "sequence_index": _field(idx, "SrtZoneLane row order", PROV_DERIVED),
                "authority": {
                    "topology": AUTH_PROVEN if topology_ok else AUTH_REVIEW,
                    "lane": _authority(lane),
                    "host_zone": _authority(host),
                    "app_sorter": _authority(app),
                    "divert_output_io": divert_io_auth,
                    "divert_pe": divert_pe_auth,
                    "sorter_section": (
                        AUTH_PROVEN if section_sorter else AUTH_UNKNOWN
                    ),
                },
            }
        )
    return out


def build_tracking_path_rows(
    sorters: list[dict[str, Any]],
    encoders_by_name: dict[str, dict[str, Any]],
    *,
    mtr_by_name: dict[str, dict[str, str]] | None = None,
    conveyor_io: set[str] | None = None,
    inpoints_by_sorter: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    """Per-sorter tracking section: encoder + optional Mtrchain conveyor + Inpoints PE."""
    mtr_by_name = mtr_by_name or {}
    conveyor_io = conveyor_io or set()
    inpoints_by_sorter = inpoints_by_sorter or {}
    rows: list[dict[str, Any]] = []
    for seq, s in enumerate(sorters):
        name = s["name"]["value"] if isinstance(s.get("name"), dict) else s.get("name")
        enc = (
            s["encoder_io"]["value"]
            if isinstance(s.get("encoder_io"), dict)
            else s.get("encoder_io")
        )
        enc = _clean(enc)
        enc_doc = encoders_by_name.get(enc.upper()) if enc else None
        enc_auth = AUTH_PROVEN if enc and enc_doc else (
            AUTH_DERIVED if enc else AUTH_UNKNOWN
        )
        enable = ""
        if enc_doc:
            eb = enc_doc.get("enable_bit")
            enable = eb.get("value") if isinstance(eb, dict) else _clean(eb)

        resolved = resolve_tracking_conveyor_for_encoder(
            enable, mtr_by_name=mtr_by_name, conveyor_io=conveyor_io
        )
        convs = resolved.get("conveyors") or []
        primary_conv = convs[0] if convs else ""
        conv_auth = resolved.get("authority") or AUTH_UNKNOWN
        conv_path = resolved.get("path") or "no EnableBit→Mtrchain path"

        pe = ""
        pe_auth = AUTH_UNKNOWN
        pe_source = "no Inpoints row for sorter"
        pe_prov = PROV_UNKNOWN
        in_rows = inpoints_by_sorter.get(_clean(name).upper(), [])
        if in_rows:
            # Prefer induct number 0 / first active induct IO.
            in_rows_sorted = sorted(
                in_rows,
                key=lambda r: int(_clean(r.get("Induct Number")) or "999999")
                if str(_clean(r.get("Induct Number")) or "").isdigit()
                else 999999,
            )
            pe = _clean(in_rows_sorted[0].get("Induct I/O Name"))
            if _meaningful(pe) and pe.upper() != "INVALID":
                pe_auth = AUTH_PROVEN
                pe_source = "FORTNA/Inpoints.asc Induct I/O Name (Sorter join)"
                pe_prov = PROV_RUN
            else:
                pe = ""
                pe_auth = AUTH_REVIEW
                pe_source = "Inpoints present but Induct I/O Name blank/INVALID"
                pe_prov = PROV_ENGINEER

        # Induct conveyor for this section = tracking belt when Mtrchain proves it.
        induct_conv = primary_conv
        induct_conv_auth = conv_auth if primary_conv else AUTH_UNKNOWN
        induct_conv_source = (
            conv_path + " (same section belt; Inpoints has no conveyor column)"
            if primary_conv
            else "Inpoints lacks conveyor; EnableBit→Mtrchain unresolved"
        )

        data_low = (
            s.get("data_low_rec", {}).get("value")
            if isinstance(s.get("data_low_rec"), dict)
            else s.get("data_low_rec") or ""
        )

        rows.append(
            {
                "sorter": _field(name, "FORTNA/Sorters.asc"),
                "sequence": _field(
                    seq,
                    "Sorters Data LowRec ascending"
                    if data_low != ""
                    else "Sorters active row order",
                    PROV_DERIVED,
                ),
                "encoder_tag": _field(enc, "FORTNA/Sorters.asc Encoder ioName"),
                "encoder_enable_bit": _field(
                    enable, "FORTNA/Encoders.asc EnableBit", PROV_RUN if enable else PROV_UNKNOWN
                ),
                "encoder_ticks_per_foot": _field(
                    (enc_doc or {}).get("ticks_per_foot", {}).get("value")
                    if isinstance((enc_doc or {}).get("ticks_per_foot"), dict)
                    else (enc_doc or {}).get("ticks_per_foot") or "",
                    "FORTNA/Encoders.asc",
                    PROV_RUN if enc_doc else PROV_UNKNOWN,
                ),
                "conveyor": _field(
                    primary_conv,
                    conv_path,
                    PROV_RUN if conv_auth == AUTH_PROVEN else (
                        PROV_DERIVED if conv_auth == AUTH_DERIVED else PROV_UNKNOWN
                    ),
                ),
                "conveyor_chain": _field(
                    convs,
                    conv_path,
                    PROV_RUN if conv_auth == AUTH_PROVEN else (
                        PROV_DERIVED if conv_auth == AUTH_DERIVED else PROV_UNKNOWN
                    ),
                ),
                "photoeye": _field(pe, pe_source, pe_prov),
                "induct_conveyor": _field(
                    induct_conv,
                    induct_conv_source,
                    PROV_RUN if induct_conv_auth == AUTH_PROVEN else (
                        PROV_DERIVED if induct_conv_auth == AUTH_DERIVED else PROV_UNKNOWN
                    ),
                ),
                "induct_pe": _field(pe, pe_source, pe_prov),
                "mtrchain_motor": _field(
                    resolved.get("motor_name") or "",
                    "FORTNA/Mtrchain.asc",
                    PROV_RUN if resolved.get("motor_name") else PROV_UNKNOWN,
                ),
                "authority": {
                    "encoder_tag": enc_auth,
                    "conveyor": conv_auth,
                    "photoeye": pe_auth,
                    "induct_conveyor": induct_conv_auth,
                    "induct_pe": pe_auth,
                    "sequence": AUTH_DERIVED,
                },
            }
        )
    return rows


def build_canonical_sorter_model(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Full SorterModel from RUN with deep evidence joins (no L5X emit)."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN").is_dir() and not (run_dir / "FORTNA").is_dir():
        run_dir = run_dir / "RUN"
    machine = _read_machine(run_dir, machine)

    sorter_rows = iter_active_table_rows(run_dir, "Sorters.asc", machine)
    encoder_rows = iter_active_table_rows(run_dir, "Encoders.asc", machine)
    zone_rows = iter_active_table_rows(run_dir, "SrtZoneLane.asc", machine)
    app_rows = iter_active_table_rows(run_dir, "SrtAppControl.asc", machine)
    boss_rows = iter_active_table_rows(run_dir, "SrtScanBoss.asc", machine)
    inpoint_rows = iter_active_table_rows(run_dir, "Inpoints.asc", machine)
    outpoint_rows = iter_active_table_rows(run_dir, "Outpoints.asc", machine)
    scan_device_rows = iter_active_table_rows(run_dir, "ScnScanDevice.asc", machine)
    scan_zone_rows = iter_active_table_rows(run_dir, "ScnScanZone.asc", machine)
    sortbuff_rows = iter_active_table_rows(run_dir, "SortBuff.asc", machine)
    sortdata_rows = iter_active_table_rows(run_dir, "SortData.asc", machine)

    conveyor_io = _conveyor_io_names(run_dir, machine)
    mtr_by_name = _mtrchain_index(run_dir, machine)
    outpoints_by_lane = _index_outpoints_by_lane(outpoint_rows)
    inpoints_by_sorter = _index_inpoints_by_sorter(inpoint_rows)

    # Stable section order from Data LowRec when numeric (not name/suffix guess).
    def _data_low_key(row: dict[str, str]) -> tuple[int, str]:
        raw = _clean(row.get("Data LowRec"))
        try:
            return (int(raw), _clean(row.get("Sorter Name") or row.get("Name")))
        except ValueError:
            return (10**9, _clean(row.get("Sorter Name") or row.get("Name")))

    sorter_rows_sorted = sorted(sorter_rows, key=_data_low_key)

    sorters: list[dict[str, Any]] = []
    for s in sorter_rows_sorted:
        name = _clean(s.get("Sorter Name") or s.get("Name"))
        if not _meaningful(name):
            continue
        enc = _clean(s.get("Encoder ioName") or s.get("Encoder Name"))
        enc_tm = _clean(s.get("Encoder tmName"))
        mach = _clean(s.get("Machine") or machine)
        max_cartons = _clean(s.get("Max Cartons"))
        trig = _clean(s.get("TrigWndwTicks"))
        data_low = _clean(s.get("Data LowRec"))
        data_high = _clean(s.get("Data HighRec"))
        buf_low = _clean(s.get("Buffer LowRec"))
        buf_high = _clean(s.get("Buffer HighRec"))
        divert_en = _clean(s.get("DivertEnableIO"))
        sorters.append(
            {
                "name": _field(name, "FORTNA/Sorters.asc"),
                "encoder_io": _field(enc, "FORTNA/Sorters.asc"),
                "encoder_tm": _field(enc_tm, "FORTNA/Sorters.asc"),
                "machine": _field(mach, "FORTNA/Sorters.asc"),
                "max_cartons": _field(max_cartons, "FORTNA/Sorters.asc"),
                "trig_window_ticks": _field(trig, "FORTNA/Sorters.asc"),
                "data_low_rec": _field(data_low, "FORTNA/Sorters.asc"),
                "data_high_rec": _field(data_high, "FORTNA/Sorters.asc"),
                "buffer_low_rec": _field(buf_low, "FORTNA/Sorters.asc"),
                "buffer_high_rec": _field(buf_high, "FORTNA/Sorters.asc"),
                "divert_enable_io": _field(divert_en, "FORTNA/Sorters.asc"),
                "authority": {
                    "name": AUTH_PROVEN,
                    "encoder_io": _authority(enc),
                    "machine": _authority(mach) if mach else AUTH_DERIVED,
                    "max_cartons": _authority(max_cartons),
                    "trig_window_ticks": _authority(trig),
                },
            }
        )

    encoders: list[dict[str, Any]] = []
    encoders_by_name: dict[str, dict[str, Any]] = {}
    for e in encoder_rows:
        name = _clean(e.get("Encoder Name") or e.get("Name"))
        if not _meaningful(name):
            continue
        doc = {
            "name": _field(name, "FORTNA/Encoders.asc"),
            "io": _field(_clean(e.get("Encoder I/O")), "FORTNA/Encoders.asc"),
            "enable_bit": _field(_clean(e.get("EnableBit")), "FORTNA/Encoders.asc"),
            "jamzone": _field(_clean(e.get("Jamzone")), "FORTNA/Encoders.asc"),
            "ticks_per_foot": _field(
                _clean(e.get("Ticks Per Foot")), "FORTNA/Encoders.asc"
            ),
            "target_fpm": _field(_clean(e.get("Target FPM")), "FORTNA/Encoders.asc"),
            "authority": {
                "name": AUTH_PROVEN,
                "ticks_per_foot": _authority(e.get("Ticks Per Foot")),
                "target_fpm": _authority(e.get("Target FPM")),
                "enable_bit": _authority(e.get("EnableBit"), blank_is=AUTH_REVIEW),
            },
        }
        encoders.append(doc)
        encoders_by_name[name.upper()] = doc

    divert_rows = build_divert_rows(zone_rows, outpoints_by_lane=outpoints_by_lane)
    tracking_path = build_tracking_path_rows(
        sorters,
        encoders_by_name,
        mtr_by_name=mtr_by_name,
        conveyor_io=conveyor_io,
        inpoints_by_sorter=inpoints_by_sorter,
    )

    apps: list[dict[str, Any]] = []
    for a in app_rows:
        name = _clean(a.get("Name"))
        if not _meaningful(name):
            continue
        mtr = _clean(a.get("SorterCnvMtr") or a.get("Sorter Cnv Mtr"))
        apps.append(
            {
                "name": _field(name, "FORTNA/SrtAppControl.asc"),
                "control_machine": _field(
                    _clean(a.get("ControlMachine")), "FORTNA/SrtAppControl.asc"
                ),
                "crr_msg_table": _field(
                    _clean(a.get("CrrMsgTable")), "FORTNA/SrtAppControl.asc"
                ),
                "dcm_msg_table": _field(
                    _clean(a.get("DcmMsgTable")), "FORTNA/SrtAppControl.asc"
                ),
                "sorter_cnv_mtr": _field(mtr, "FORTNA/SrtAppControl.asc"),
                "err_config": _field(
                    _clean(a.get("ErrConfig")), "FORTNA/SrtAppControl.asc"
                ),
                "authority": {
                    "name": AUTH_PROVEN,
                    "sorter_cnv_mtr": _authority(mtr, blank_is=AUTH_REVIEW),
                },
            }
        )

    scan_bosses: list[dict[str, Any]] = []
    for b in boss_rows:
        name = _clean(b.get("Name"))
        if not _meaningful(name):
            continue
        scan_bosses.append(
            {
                "name": _field(name, "FORTNA/SrtScanBoss.asc"),
                "app_sorter": _field(
                    _clean(b.get("AppSorter")), "FORTNA/SrtScanBoss.asc"
                ),
                "scan_zone": _field(
                    _clean(b.get("ScanZone")), "FORTNA/SrtScanBoss.asc"
                ),
                "lane": _field(_clean(b.get("Lane")), "FORTNA/SrtScanBoss.asc"),
                "authority": {
                    "name": AUTH_PROVEN,
                    "app_sorter": _authority(b.get("AppSorter")),
                    "scan_zone": _authority(b.get("ScanZone")),
                },
            }
        )

    scanners: list[dict[str, Any]] = []
    for d in scan_device_rows:
        name = _clean(d.get("Name"))
        if not _meaningful(name):
            continue
        scanners.append(
            {
                "name": _field(name, "FORTNA/ScnScanDevice.asc"),
                "scan_zone": _field(
                    _clean(d.get("ScanZone")), "FORTNA/ScnScanDevice.asc"
                ),
                "scan_type": _field(
                    _clean(d.get("ScanType")), "FORTNA/ScnScanDevice.asc"
                ),
                "update_pt": _field(
                    _clean(d.get("UpdatePt")), "FORTNA/ScnScanDevice.asc"
                ),
                "authority": {"name": AUTH_PROVEN},
            }
        )

    scan_zones: list[dict[str, Any]] = []
    for z in scan_zone_rows:
        name = _clean(z.get("Name"))
        if not _meaningful(name):
            continue
        scan_zones.append(
            {
                "name": _field(name, "FORTNA/ScnScanZone.asc"),
                "scan_zone_id": _field(
                    _clean(z.get("ScanZoneID")), "FORTNA/ScnScanZone.asc"
                ),
                "tracking_table": _field(
                    _clean(z.get("TrackingTable")), "FORTNA/ScnScanZone.asc"
                ),
                "device_trk_table": _field(
                    _clean(z.get("DeviceTrkTable")), "FORTNA/ScnScanZone.asc"
                ),
                "authority": {"name": AUTH_PROVEN},
            }
        )

    # Sections under application: Outpoints.Sorter ∩ SrtZoneLane.Lane → AppSorter.
    # Sorters rows without divert lanes remain tracking sections (Inpoints/Encoders).
    sections_under_app: dict[str, list[str]] = {}
    for d in divert_rows:
        app = _clean(
            d["app_sorter"]["value"]
            if isinstance(d.get("app_sorter"), dict)
            else d.get("app_sorter")
        )
        section = _clean(
            d["sorter_section"]["value"]
            if isinstance(d.get("sorter_section"), dict)
            else d.get("sorter_section")
        )
        if _meaningful(app) and _meaningful(section):
            bucket = sections_under_app.setdefault(app, [])
            if section not in bucket:
                bucket.append(section)
    all_section_names = [
        s["name"]["value"] if isinstance(s.get("name"), dict) else s.get("name")
        for s in sorters
    ]
    unassigned_sections = [
        n for n in all_section_names
        if n and all(n not in secs for secs in sections_under_app.values())
    ]

    application_structure = {
        "authority": AUTH_DERIVED if (sections_under_app or (apps and sorters)) else (
            AUTH_PROVEN if apps and not sorters else AUTH_UNKNOWN
        ),
        "path": (
            "SrtZoneLane.AppSorter + Outpoints.Sorter via Outpoint Name==Lane join; "
            "Sorters rows are tracking sections"
            if (sections_under_app or sorters)
            else "insufficient zone/outpoint join"
        ),
        "apps": [
            a["name"]["value"] if isinstance(a.get("name"), dict) else a.get("name")
            for a in apps
        ],
        "sections_under_app": sections_under_app,
        "tracking_sections": all_section_names,
        "sections_without_divert_lanes": unassigned_sections,
        "note": (
            "Multiple Sorters rows are tracking sections. App ownership of divert "
            "lanes is proven via SrtZoneLane.AppSorter; section ownership of those "
            "lanes is proven via Outpoints.Sorter on the same lane name — not from "
            "name tokens alone. Sections lacking Outpoints⋈ZoneLane joins stay "
            "listed as tracking sections only."
        ),
    }

    zone_lanes = [
        {
            "name": d["name"],
            "enabled": d["enabled"],
            "app_sorter": d["app_sorter"],
            "lane": d["lane"],
            "host_zone": d["host_zone"],
            "full_clear_timer": d["full_clear_timer"],
            "sorter_section": d.get("sorter_section"),
            "authority": d["authority"],
        }
        for d in divert_rows
    ]

    # Coverage helpers
    track_conv_resolved = sum(
        1
        for t in tracking_path
        if _meaningful(
            t["conveyor"]["value"] if isinstance(t.get("conveyor"), dict) else ""
        )
    )
    track_pe_resolved = sum(
        1
        for t in tracking_path
        if _meaningful(
            t["photoeye"]["value"] if isinstance(t.get("photoeye"), dict) else ""
        )
    )
    divert_io_resolved = sum(
        1
        for d in divert_rows
        if (d.get("authority") or {}).get("divert_output_io") == AUTH_PROVEN
    )
    divert_pe_resolved = sum(
        1
        for d in divert_rows
        if (d.get("authority") or {}).get("divert_pe") == AUTH_PROVEN
    )

    # Primary induct (UI single-row): first tracking section with proven/derived values
    primary_induct_conv = ""
    primary_induct_pe = ""
    primary_induct_enc = ""
    primary_induct_conv_auth = AUTH_UNKNOWN
    primary_induct_pe_auth = AUTH_UNKNOWN
    for t in tracking_path:
        c = t["conveyor"]["value"] if isinstance(t.get("conveyor"), dict) else ""
        p = t["photoeye"]["value"] if isinstance(t.get("photoeye"), dict) else ""
        e = t["encoder_tag"]["value"] if isinstance(t.get("encoder_tag"), dict) else ""
        if not primary_induct_enc and _meaningful(e):
            primary_induct_enc = e
        if not primary_induct_pe and _meaningful(p):
            primary_induct_pe = p
            primary_induct_pe_auth = (t.get("authority") or {}).get(
                "induct_pe", AUTH_PROVEN
            )
        if not primary_induct_conv and _meaningful(c):
            primary_induct_conv = c
            primary_induct_conv_auth = (t.get("authority") or {}).get(
                "induct_conveyor", AUTH_DERIVED
            )
        if primary_induct_conv and primary_induct_pe:
            break

    track_conv_auth = (
        AUTH_DERIVED
        if track_conv_resolved
        and any(
            (t.get("authority") or {}).get("conveyor") == AUTH_DERIVED
            for t in tracking_path
        )
        else (
            AUTH_PROVEN
            if track_conv_resolved
            and all(
                (t.get("authority") or {}).get("conveyor") == AUTH_PROVEN
                for t in tracking_path
                if _meaningful(
                    t["conveyor"]["value"]
                    if isinstance(t.get("conveyor"), dict)
                    else ""
                )
            )
            else (AUTH_UNKNOWN if not track_conv_resolved else AUTH_DERIVED)
        )
    )

    field_authority = {
        "sorter_existence": AUTH_PROVEN if sorters else AUTH_UNKNOWN,
        "sorter_identity": AUTH_PROVEN if sorters else AUTH_UNKNOWN,
        "sorter_encoder_link": (
            AUTH_PROVEN
            if sorters
            and all(
                (s.get("authority") or {}).get("encoder_io") == AUTH_PROVEN
                for s in sorters
            )
            else (AUTH_DERIVED if sorters else AUTH_UNKNOWN)
        ),
        "encoder_parameters": AUTH_PROVEN if encoders else AUTH_UNKNOWN,
        "app_control": AUTH_PROVEN if apps else AUTH_UNKNOWN,
        "scan_boss": AUTH_PROVEN if scan_bosses else AUTH_UNKNOWN,
        "scan_zone": AUTH_PROVEN if (scan_zones or scan_bosses) else AUTH_UNKNOWN,
        "scanner": AUTH_PROVEN if scanners else AUTH_UNKNOWN,
        "divert_lane_topology": AUTH_PROVEN if divert_rows else AUTH_UNKNOWN,
        "divert_output_io": (
            AUTH_PROVEN
            if divert_io_resolved == len(divert_rows) and divert_rows
            else (
                AUTH_DERIVED
                if divert_io_resolved
                else AUTH_REVIEW
            )
        ),
        "divert_pe": (
            AUTH_PROVEN
            if divert_pe_resolved
            else (AUTH_REVIEW if divert_rows else AUTH_UNKNOWN)
        ),
        "tracking_conveyor_chain": track_conv_auth,
        "tracking_pe": (
            AUTH_PROVEN if track_pe_resolved == len(tracking_path) and tracking_path
            else (AUTH_PROVEN if track_pe_resolved else AUTH_UNKNOWN)
        ),
        "induct_conveyor": primary_induct_conv_auth,
        "induct_pe": primary_induct_pe_auth,
        "induct_encoder": AUTH_PROVEN if primary_induct_enc else AUTH_UNKNOWN,
        "sorter_type": AUTH_REVIEW,
        "transport_area": AUTH_UNKNOWN,
        "tracking_order": AUTH_DERIVED if tracking_path else AUTH_UNKNOWN,
        "tracking_offset": AUTH_REVIEW,
        "trig_window": (
            AUTH_PROVEN
            if any(
                _meaningful(
                    s.get("trig_window_ticks", {}).get("value")
                    if isinstance(s.get("trig_window_ticks"), dict)
                    else ""
                )
                for s in sorters
            )
            else AUTH_UNKNOWN
        ),
        "ppi_encoder_scaling": AUTH_PROVEN if encoders else AUTH_UNKNOWN,
        "max_cartons_buffer": AUTH_PROVEN if sorters else AUTH_UNKNOWN,
        "application_structure": application_structure["authority"],
        "sortbuff_link": AUTH_PROVEN if sortbuff_rows else AUTH_UNKNOWN,
        "sortdata_link": AUTH_PROVEN if sortdata_rows else AUTH_UNKNOWN,
        "plc_generation": "PHASE1_SUPPORTED" if sorters else "NOT_APPLICABLE",
    }

    gate_f = build_gate_f_field_authority(locals_bundle={
        "sorters": sorters,
        "encoders": encoders,
        "apps": apps,
        "scan_bosses": scan_bosses,
        "scanners": scanners,
        "scan_zones": scan_zones,
        "divert_rows": divert_rows,
        "tracking_path": tracking_path,
        "field_authority": field_authority,
        "primary_induct_conv": primary_induct_conv,
        "primary_induct_pe": primary_induct_pe,
        "primary_induct_enc": primary_induct_enc,
        "track_conv_resolved": track_conv_resolved,
        "track_pe_resolved": track_pe_resolved,
        "divert_io_resolved": divert_io_resolved,
        "divert_pe_resolved": divert_pe_resolved,
        "application_structure": application_structure,
    })

    return {
        "generated_at": _ts(),
        "machine": machine,
        "source_of_truth": "RUN only — finished PLC L5X not read",
        "detected": bool(sorters),
        "sorter_count": len(sorters),
        "encoder_count": len(encoders),
        "divert_count": len(divert_rows),
        "tracking_path_count": len(tracking_path),
        "sorters": sorters,
        "encoders": encoders,
        "app_controls": apps,
        "scan_bosses": scan_bosses,
        "scanners": scanners,
        "scan_zones": scan_zones,
        "zone_lanes": zone_lanes,
        "divert_rows": divert_rows,
        "tracking_path": tracking_path,
        "inpoints": [
            {
                "name": _field(_clean(r.get("Inpoint Name")), "FORTNA/Inpoints.asc"),
                "sorter": _field(_clean(r.get("Sorter")), "FORTNA/Inpoints.asc"),
                "induct_io": _field(
                    _clean(r.get("Induct I/O Name")), "FORTNA/Inpoints.asc"
                ),
                "induct_number": _field(
                    _clean(r.get("Induct Number")), "FORTNA/Inpoints.asc"
                ),
                "authority": {"induct_io": AUTH_PROVEN},
            }
            for r in inpoint_rows
        ],
        "application_structure": application_structure,
        "induct": {
            "conveyor": _field(
                primary_induct_conv,
                "first tracking section EnableBit→Mtrchain",
                PROV_DERIVED if primary_induct_conv else PROV_UNKNOWN,
            ),
            "photoeye": _field(
                primary_induct_pe,
                "FORTNA/Inpoints.asc",
                PROV_RUN if primary_induct_pe else PROV_UNKNOWN,
            ),
            "encoder": _field(
                primary_induct_enc,
                "FORTNA/Sorters.asc Encoder ioName",
                PROV_RUN if primary_induct_enc else PROV_UNKNOWN,
            ),
            "authority": {
                "conveyor": primary_induct_conv_auth,
                "photoeye": primary_induct_pe_auth,
                "encoder": AUTH_PROVEN if primary_induct_enc else AUTH_UNKNOWN,
            },
        },
        "coverage": {
            "tracking_conveyors_resolved": track_conv_resolved,
            "tracking_pes_resolved": track_pe_resolved,
            "divert_outputs_resolved": divert_io_resolved,
            "divert_pes_resolved": divert_pe_resolved,
            "divert_topology_rows": len(divert_rows),
            "inpoints_active": len(inpoint_rows),
            "outpoints_active": len(outpoint_rows),
            "sortbuff_active": len(sortbuff_rows),
            "sortdata_active": len(sortdata_rows),
        },
        "field_authority": field_authority,
        "gate_f_fields": gate_f,
        "generation_state": "GENERATABLE" if sorters else "NO_SORTERS",
        "plc_generation": "PHASE1_SUPPORTED" if sorters else "NOT_APPLICABLE",
        "note": (
            "Deep RUN evidence graph (Inpoints/Outpoints/Mtrchain/Scn*). "
            "Sorter_Track Phase 1 pack compiler emits from SorterModel multiplicity; "
            "WCS remains external."
        ),
    }


def build_gate_f_field_authority(locals_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Gate F: authority row for each PLC-generation-relevant sorter field."""
    fa = locals_bundle.get("field_authority") or {}
    tracking_path = locals_bundle.get("tracking_path") or []
    divert_rows = locals_bundle.get("divert_rows") or []
    sorters = locals_bundle.get("sorters") or []
    encoders = locals_bundle.get("encoders") or []
    apps = locals_bundle.get("apps") or []
    scan_bosses = locals_bundle.get("scan_bosses") or []
    scanners = locals_bundle.get("scanners") or []
    scan_zones = locals_bundle.get("scan_zones") or []
    app_struct = locals_bundle.get("application_structure") or {}

    def row(
        field: str,
        primary: str,
        supporting: str,
        path: str,
        authority: str,
        autopopulate: bool,
        engineer: str,
        why: str,
    ) -> dict[str, Any]:
        return {
            "field": field,
            "primary_evidence": primary,
            "supporting_evidence": supporting,
            "relationship_path": path,
            "authority": authority,
            "autopopulate": bool(autopopulate),
            "engineer_action": engineer,
            "why": why,
        }

    track_ids = [
        (
            t["conveyor"]["value"]
            if isinstance(t.get("conveyor"), dict)
            else ""
        )
        for t in tracking_path
    ]
    track_pes = [
        (
            t["photoeye"]["value"]
            if isinstance(t.get("photoeye"), dict)
            else ""
        )
        for t in tracking_path
    ]
    enc_per = [
        (
            t["encoder_tag"]["value"]
            if isinstance(t.get("encoder_tag"), dict)
            else ""
        )
        for t in tracking_path
    ]

    return [
        row(
            "1. Sorter type",
            "none (no explicit type column)",
            "Sorters.Name tokens are not proof",
            "—",
            fa.get("sorter_type", AUTH_REVIEW),
            False,
            "Select shoe/popup/etc. in UI",
            "RUN has no authoritative sorter equipment-type field",
        ),
        row(
            "2. Sorter/application identity",
            "Sorters.Sorter Name + SrtAppControl.Name",
            "SrtZoneLane.AppSorter; Outpoints.Sorter",
            "Sorters ‖ SrtAppControl; sections via Outpoints⋈SrtZoneLane",
            fa.get("sorter_identity", AUTH_UNKNOWN),
            True,
            "None when present",
            "Named active rows are PROVEN; multi-section-under-app is DERIVED via lane join",
        ),
        row(
            "3. Transport Area association",
            "none",
            "Machine / jamzone strings are not Area membership",
            "—",
            fa.get("transport_area", AUTH_UNKNOWN),
            False,
            "Assign Transport area in UI",
            "No schema edge from sorter tables to Transport Areas",
        ),
        row(
            "4. Induct conveyor",
            "Encoders.EnableBit → Mtrchain.Motor_Chained1",
            "Inpoints proves PE only (no conveyor column)",
            "Sorters.Encoder→Encoders.EnableBit→Mtrchain→Conveyor",
            fa.get("induct_conveyor", AUTH_UNKNOWN),
            bool(locals_bundle.get("primary_induct_conv")),
            "Confirm if DERIVED; enter if UNKNOWN",
            "Same-section belt from VFD enable/aux pairing when Conveyor+Mtrchain verify both names",
        ),
        row(
            "5. Induct PE",
            "Inpoints.Induct I/O Name",
            "Inpoints.Sorter == Sorters.Sorter Name",
            "Sorters → Inpoints",
            fa.get("induct_pe", AUTH_UNKNOWN),
            bool(locals_bundle.get("primary_induct_pe")),
            "None when PROVEN",
            "Explicit Induct I/O Name on Inpoints",
        ),
        row(
            "6. Induct encoder",
            "Sorters.Encoder ioName",
            "Encoders row",
            "Sorters → Encoders",
            fa.get("induct_encoder", AUTH_UNKNOWN),
            bool(locals_bundle.get("primary_induct_enc")),
            "None when PROVEN",
            "First/section encoder link is RUN-explicit",
        ),
        row(
            "7. Tracking conveyor count",
            "count(active Sorters)",
            "tracking_path length",
            "Sorters active rows",
            AUTH_DERIVED if sorters else AUTH_UNKNOWN,
            bool(sorters),
            "Adjust only if engineer merges/splits sections",
            "One tracking section stub per active Sorters row",
        ),
        row(
            "8. Tracking conveyor identities",
            "Mtrchain.Motor_Chained* via EnableBit",
            "Conveyor.IO_Name existence check",
            "Encoders.EnableBit → Mtrchain → Conveyor",
            fa.get("tracking_conveyor_chain", AUTH_UNKNOWN),
            bool(locals_bundle.get("track_conv_resolved")),
            "Fill blanks; never trust ENC###≡P###",
            f"resolved={locals_bundle.get('track_conv_resolved', 0)}/{len(tracking_path)} {track_ids}",
        ),
        row(
            "9. Tracking conveyor ORDER",
            "Sorters.Data LowRec ascending",
            "Mtrchain Motor_Aux chain (supporting)",
            "Sorters.Data LowRec",
            fa.get("tracking_order", AUTH_UNKNOWN),
            bool(tracking_path),
            "Reorder only if buffer ranges are wrong for site intent",
            "Order from record-range allocation, not name suffixes",
        ),
        row(
            "10. Tracking PE count",
            "count(Inpoints per Sorters)",
            "tracking_path photoeye fills",
            "Inpoints",
            AUTH_DERIVED if locals_bundle.get("track_pe_resolved") else AUTH_UNKNOWN,
            bool(locals_bundle.get("track_pe_resolved")),
            "Add extra PEs if needed",
            f"resolved={locals_bundle.get('track_pe_resolved', 0)}/{len(tracking_path)}",
        ),
        row(
            "11. Tracking PE identities",
            "Inpoints.Induct I/O Name",
            "Conveyor Type=PHOTOCELL existence",
            "Sorters → Inpoints",
            fa.get("tracking_pe", AUTH_UNKNOWN),
            bool(locals_bundle.get("track_pe_resolved")),
            "None when PROVEN",
            f"{track_pes}",
        ),
        row(
            "12. Tracking PE ORDER",
            "same as tracking section order",
            "Inpoints.Induct Number",
            "tracking_path sequence",
            AUTH_DERIVED if tracking_path else AUTH_UNKNOWN,
            bool(tracking_path),
            "Review if multiple inducts per section",
            "Follows section order from Data LowRec",
        ),
        row(
            "13. Encoder per tracking section",
            "Sorters.Encoder ioName",
            "Encoders.Ticks Per Foot / EnableBit",
            "Sorters → Encoders",
            fa.get("sorter_encoder_link", AUTH_UNKNOWN),
            bool(enc_per and all(enc_per)),
            "None when PROVEN",
            f"{enc_per}",
        ),
        row(
            "14. Scan zone",
            "SrtScanBoss.ScanZone / ScnScanZone.Name",
            "ScnScanZone.TrackingTable",
            "SrtScanBoss → ScnScanZone",
            fa.get("scan_zone", AUTH_UNKNOWN),
            bool(scan_zones or scan_bosses),
            "None when PROVEN",
            "Explicit scan zone names when tables populated",
        ),
        row(
            "15. Scanner / scan boss",
            "SrtScanBoss + ScnScanDevice",
            "AppSorter / ScanZone joins",
            "SrtAppControl ← SrtScanBoss → ScnScanDevice",
            fa.get("scan_boss", AUTH_UNKNOWN),
            bool(scan_bosses or scanners),
            "None when PROVEN",
            f"bosses={len(scan_bosses)} devices={len(scanners)}",
        ),
        row(
            "16. Divert count",
            "count(active SrtZoneLane)",
            "Outpoints active rows",
            "SrtZoneLane",
            AUTH_PROVEN if divert_rows else AUTH_UNKNOWN,
            bool(divert_rows),
            "None for topology count",
            f"count={len(divert_rows)}",
        ),
        row(
            "17. Divert/lane identities",
            "SrtZoneLane.Lane / Name",
            "Outpoints.Outpoint Name",
            "SrtZoneLane",
            AUTH_PROVEN if divert_rows else AUTH_UNKNOWN,
            bool(divert_rows),
            "None",
            "Topology PROVEN from SrtZoneLane",
        ),
        row(
            "18. Host zones",
            "SrtZoneLane.HostZone",
            "—",
            "SrtZoneLane",
            AUTH_PROVEN if divert_rows else AUTH_UNKNOWN,
            bool(divert_rows),
            "None",
            "HostZone column is RUN-explicit",
        ),
        row(
            "19. Divert physical output",
            "Outpoints.Outpoint I/O Name",
            "SrtZoneLane.LaneEnableSignal (often INVALID)",
            "SrtZoneLane.Lane == Outpoints.Outpoint Name",
            fa.get("divert_output_io", AUTH_REVIEW),
            bool(locals_bundle.get("divert_io_resolved")),
            "Supply IO when Outpoints also INVALID",
            f"resolved={locals_bundle.get('divert_io_resolved', 0)}/{len(divert_rows)} "
            "(LaneEnableSignal alone is not sufficient when INVALID)",
        ),
        row(
            "20. Divert PE if applicable",
            "Outpoints.Verify I/O Name when valid",
            "FullClearTimer name is hint only",
            "Outpoints / SrtZoneLane timers",
            fa.get("divert_pe", AUTH_UNKNOWN),
            bool(locals_bundle.get("divert_pe_resolved")),
            "Map confirm PE when Verify I/O INVALID",
            "Timer-name PE parsing is not treated as proof",
        ),
        row(
            "21. Tracking distance/offset",
            "Outpoints.Outpoint Location (ticks) partial",
            "no induct→divert offset field",
            "Outpoints.Outpoint Location",
            fa.get("tracking_offset", AUTH_REVIEW),
            False,
            "Enter track offsets / commissioning",
            "Locations are per-outpoint; global induct→divert offset not in RUN",
        ),
        row(
            "22. Trigger window",
            "Sorters.TrigWndwTicks",
            "—",
            "Sorters",
            fa.get("trig_window", AUTH_UNKNOWN),
            fa.get("trig_window") == AUTH_PROVEN,
            "None when PROVEN",
            "Explicit TrigWndwTicks on Sorters",
        ),
        row(
            "23. PPI / encoder scaling",
            "Encoders.Ticks Per Foot",
            "Target FPM",
            "Encoders",
            fa.get("ppi_encoder_scaling", AUTH_UNKNOWN),
            bool(encoders),
            "None when PROVEN",
            "Ticks Per Foot is RUN-explicit scale",
        ),
        row(
            "24. Maximum cartons/buffer values",
            "Sorters.Max Cartons + Data/Buffer Low/HighRec",
            "SortBuff/SortData row ranges",
            "Sorters (+ SortBuff/SortData occupancy)",
            fa.get("max_cartons_buffer", AUTH_UNKNOWN),
            bool(sorters),
            "None when PROVEN",
            "Max Cartons and record ranges are explicit",
        ),
        row(
            "25. Other Sorter_Track-critical params",
            "partial (msg tables, ErrConfig, TrackingTable)",
            "gold pack constants are NOT used",
            "SrtAppControl / ScnScanZone",
            AUTH_REVIEW,
            False,
            "Commissioning + library path still required before PLC emit",
            "plc_generation stays NOT_STARTED; no hollow Sorter_Track",
        ),
        row(
            "Application structure (sections vs apps)",
            app_struct.get("path") or "—",
            f"apps={app_struct.get('apps')}",
            "SrtZoneLane⋈Outpoints",
            app_struct.get("authority", AUTH_UNKNOWN),
            bool(app_struct.get("sections_under_app")),
            "Confirm multi-section application intent",
            app_struct.get("note") or "",
        ),
    ]


def build_subsystem_model(inventory: dict[str, Any], machine: str) -> dict[str, Any]:
    by = {t["table"]: t for t in inventory.get("tables") or []}
    run_dir = Path(inventory.get("run_dir") or "")

    # Prefer full-table reads when run_dir is known (inventory samples are capped).
    if run_dir.is_dir():
        canonical = build_canonical_sorter_model(run_dir, machine)
        sorters = canonical["sorters"]
        encoders = canonical["encoders"]
        zones = canonical["zone_lanes"]
        apps = canonical["app_controls"]
        scan_bosses = canonical["scan_bosses"]
    else:
        def active_rows(name: str) -> list[dict[str, str]]:
            t = by.get(name) or {}
            return list(t.get("samples") or [])

        sorters = []
        for s in active_rows("Sorters.asc"):
            name = s.get("Sorter Name") or ""
            if not _meaningful(name):
                continue
            sorters.append(
                {
                    "name": _field(name, "FORTNA/Sorters.asc"),
                    "encoder_io": _field(s.get("Encoder ioName") or "", "FORTNA/Sorters.asc"),
                    "machine": _field(s.get("Machine") or machine, "FORTNA/Sorters.asc"),
                }
            )

        encoders = []
        for e in active_rows("Encoders.asc"):
            name = e.get("Encoder Name") or ""
            if not _meaningful(name):
                continue
            encoders.append(
                {
                    "name": _field(name, "FORTNA/Encoders.asc"),
                    "io": _field(e.get("Encoder I/O") or "", "FORTNA/Encoders.asc"),
                    "enable_bit": _field(e.get("EnableBit") or "", "FORTNA/Encoders.asc"),
                    "jamzone": _field(e.get("Jamzone") or "", "FORTNA/Encoders.asc"),
                    "ticks_per_foot": _field(
                        e.get("Ticks Per Foot") or "", "FORTNA/Encoders.asc"
                    ),
                    "target_fpm": _field(e.get("Target FPM") or "", "FORTNA/Encoders.asc"),
                }
            )

        zones = []
        for z in active_rows("SrtZoneLane.asc"):
            name = z.get("Name") or ""
            if not _meaningful(name):
                continue
            zones.append(
                {
                    "name": _field(name, "FORTNA/SrtZoneLane.asc"),
                    "enabled": _field(z.get("Enabled") or "", "FORTNA/SrtZoneLane.asc"),
                    "app_sorter": _field(z.get("AppSorter") or "", "FORTNA/SrtZoneLane.asc"),
                    "lane": _field(z.get("Lane") or "", "FORTNA/SrtZoneLane.asc"),
                    "host_zone": _field(z.get("HostZone") or "", "FORTNA/SrtZoneLane.asc"),
                    "full_clear_timer": _field(
                        z.get("FullClearTimer") or "", "FORTNA/SrtZoneLane.asc"
                    ),
                }
            )

        apps = []
        for a in active_rows("SrtAppControl.asc"):
            name = a.get("Name") or ""
            if not _meaningful(name):
                continue
            apps.append(
                {
                    "name": _field(name, "FORTNA/SrtAppControl.asc"),
                    "control_machine": _field(
                        a.get("ControlMachine") or "", "FORTNA/SrtAppControl.asc"
                    ),
                    "crr_msg_table": _field(
                        a.get("CrrMsgTable") or "", "FORTNA/SrtAppControl.asc"
                    ),
                    "dcm_msg_table": _field(
                        a.get("DcmMsgTable") or "", "FORTNA/SrtAppControl.asc"
                    ),
                }
            )

        scan_bosses = []
        for b in active_rows("SrtScanBoss.asc"):
            name = b.get("Name") or ""
            if not _meaningful(name):
                continue
            scan_bosses.append(
                {
                    "name": _field(name, "FORTNA/SrtScanBoss.asc"),
                    "app_sorter": _field(b.get("AppSorter") or "", "FORTNA/SrtScanBoss.asc"),
                    "scan_zone": _field(b.get("ScanZone") or "", "FORTNA/SrtScanBoss.asc"),
                    "lane": _field(b.get("Lane") or "", "FORTNA/SrtScanBoss.asc"),
                }
            )

    srt_tracks: list[dict[str, Any]] = []
    for i in range(1, 6):
        tname = f"SrtTrack{i}.asc"
        t = by.get(tname) or {}
        srt_tracks.append(
            {
                "slot": i,
                "table": tname,
                "active_rows": _field(t.get("active_rows", 0), f"FORTNA/{tname}"),
                "row_count": _field(t.get("row_count", 0), f"FORTNA/{tname}"),
                "byte_size": _field(t.get("byte_size", 0), f"FORTNA/{tname}"),
                "sample_scan_zones": _field(
                    sorted(
                        {
                            s.get("ScanZoneID")
                            for s in (t.get("samples") or [])
                            if _meaningful(s.get("ScanZoneID"))
                        }
                    ),
                    f"FORTNA/{tname}",
                    PROV_DERIVED,
                ),
            }
        )

    wcs_t = by.get("WCSEvents.asc") or {}
    msgwcs = by.get("MsgWCS.asc") or {}
    msgtrack = by.get("MsgTrack.asc") or {}
    xfrtrack = by.get("XfrTrack.asc") or {}

    wcs_enabled = [
        {
            "event": _field(s.get("EventName") or "", "FORTNA/WCSEvents.asc"),
            "destination": _field(s.get("WCSDestination") or "", "FORTNA/WCSEvents.asc"),
            "category": _field(s.get("WCSCategory") or "", "FORTNA/WCSEvents.asc"),
        }
        for s in (wcs_t.get("samples") or [])
        if _clean(s.get("WCSEnable")).upper() in ("Y", "YES")
    ]

    # Characterization
    sorter_kind = "none"
    if sorters:
        names_u = " ".join(_clean(s["name"]["value"]).upper() for s in sorters)
        if "SAWTOOTH" in names_u and "CITY" in names_u:
            sorter_kind = "sawtooth_plus_city_counter"
        elif "SAWTOOTH" in names_u:
            sorter_kind = "sawtooth_merge_as_sorter"
        elif any("SHOE" in _clean(s["name"]["value"]).upper() for s in sorters):
            sorter_kind = "shoe_sorter"
        else:
            sorter_kind = "named_sorter_rows"

    model = {
        "generated_at": _ts(),
        "machine": _field(machine, "project.cfg / CLI", PROV_DERIVED),
        "source_of_truth": "RUN only — finished PLC L5X not read; discovery skeleton only",
        "generation_boundary": {
            "emits_l5x": False,
            "tracking_wcs_generation": "NOT_SUPPORTED",
            "note": (
                "Subsystem skeleton is discovery-only. Gold Sorter_Track / WCS_Interface "
                "packs exist but are site-fixed; no complete generic library path."
            ),
        },
        "characterization": {
            "sorter_kind": _field(sorter_kind, "FORTNA/Sorters.asc", PROV_DERIVED),
            "active_sorter_count": _field(len(sorters), "FORTNA/Sorters.asc", PROV_DERIVED),
            "active_encoder_count": _field(
                len(encoders), "FORTNA/Encoders.asc", PROV_DERIVED
            ),
            "active_zone_lane_count": _field(
                len(zones), "FORTNA/SrtZoneLane.asc", PROV_DERIVED
            ),
            "srttrack_active_total": _field(
                sum(int(s["active_rows"]["value"] or 0) for s in srt_tracks),
                "FORTNA/SrtTrack*.asc",
                PROV_DERIVED,
            ),
            "msgtrack_active": _field(
                msgtrack.get("active_rows", 0), "FORTNA/MsgTrack.asc"
            ),
            "msgwcs_active": _field(msgwcs.get("active_rows", 0), "FORTNA/MsgWCS.asc"),
            "xfrtrack_active": _field(
                xfrtrack.get("active_rows", 0), "FORTNA/XfrTrack.asc"
            ),
            "wcs_events_active_named": _field(
                wcs_t.get("active_rows", 0), "FORTNA/WCSEvents.asc"
            ),
        },
        "sorters": sorters,
        "encoders": encoders,
        "app_controls": apps,
        "scan_bosses": scan_bosses,
        "zone_lanes": zones,
        "divert_rows": (
            canonical.get("divert_rows") if run_dir.is_dir() else build_divert_rows([])
        ),
        "tracking_path": (
            canonical.get("tracking_path")
            if run_dir.is_dir()
            else build_tracking_path_rows(sorters, {})
        ),
        "field_authority": (
            canonical.get("field_authority")
            if run_dir.is_dir()
            else {"plc_generation": "NOT_STARTED"}
        ),
        "plc_generation": "NOT_STARTED",
        "srt_tracks": srt_tracks,
        "xfr_track": {
            "active_rows": _field(xfrtrack.get("active_rows", 0), "FORTNA/XfrTrack.asc"),
            "headers_present": _field(
                bool(xfrtrack.get("headers")), "FORTNA/XfrTrack.asc"
            ),
        },
        "messaging": {
            "msg_track": {
                "byte_size": _field(msgtrack.get("byte_size", 0), "FORTNA/MsgTrack.asc"),
                "active_rows": _field(msgtrack.get("active_rows", 0), "FORTNA/MsgTrack.asc"),
            },
            "msg_wcs": {
                "active_rows": _field(msgwcs.get("active_rows", 0), "FORTNA/MsgWCS.asc"),
                "note": _field(
                    "Runtime outbound WCS queue; Destination topics, not topology",
                    "FORTNA/MsgWCS.asc",
                    PROV_DERIVED,
                ),
            },
            "wcs_events": {
                "active_named_rows": _field(
                    wcs_t.get("active_rows", 0), "FORTNA/WCSEvents.asc"
                ),
                "enabled_samples": wcs_enabled,
            },
        },
        "gaps": [
            {
                "item": "divert_io_map",
                "detail": "RUN does not expose PLC divert output tags as a complete generic map",
                "provenance": PROV_ENGINEER,
            },
            {
                "item": "tracking_conveyor_chain",
                "detail": (
                    "Induct/tracking conveyor sequence for Sorter_Track is not fully "
                    "derivable from SrtTrack* runtime slots alone"
                ),
                "provenance": PROV_ENGINEER,
            },
            {
                "item": "wcs_tcp_endpoints",
                "detail": "WCSEvents topics discovered; TCP peer/port wiring is engineer/config",
                "provenance": PROV_ENGINEER,
            },
        ],
    }
    return model


def build_generation_support_matrix(model: dict[str, Any]) -> dict[str, Any]:
    """Capability status relative to a complete generic library path."""
    char = model.get("characterization") or {}
    has_sorters = int((char.get("active_sorter_count") or {}).get("value") or 0) > 0
    has_enc = int((char.get("active_encoder_count") or {}).get("value") or 0) > 0
    has_zones = int((char.get("active_zone_lane_count") or {}).get("value") or 0) > 0
    has_srt = int((char.get("srttrack_active_total") or {}).get("value") or 0) > 0
    has_wcs = int((char.get("wcs_events_active_named") or {}).get("value") or 0) > 0

    def row(cap: str, status: str, evidence: str, notes: str = "") -> dict[str, str]:
        return {
            "capability": cap,
            "status": status,
            "evidence": evidence,
            "notes": notes,
        }

    caps = [
        row(
            "sorter_entity_inventory",
            "DISCOVERED" if has_sorters else "MODELED",
            "Sorters.asc (+ machine overlay)",
            "Named sorter rows + encoder links",
        ),
        row(
            "encoder_parameter_inventory",
            "DISCOVERED" if has_enc else "MODELED",
            "Encoders.asc",
            "Ticks/FPM/EnableBit/Jamzone discoverable; sawtooth encoder emit is separate",
        ),
        row(
            "zone_lane_assignment",
            "DISCOVERED" if has_zones else "MODELED",
            "SrtZoneLane.asc",
            "HostZone / Lane / AppSorter relationships",
        ),
        row(
            "scan_boss_topology",
            "DISCOVERED" if (model.get("scan_bosses")) else "MODELED",
            "SrtScanBoss.asc + SrtAppControl.asc",
            "Scan zone ↔ app sorter linkage",
        ),
        row(
            "srt_track_runtime_slots",
            "DISCOVERED" if has_srt else "MODELED",
            "SrtTrack1..5.asc",
            "Runtime carton slots; not static divert topology",
        ),
        row(
            "xfr_track_runtime_slots",
            "MODELED",
            "XfrTrack.asc",
            "Schema present; often zero active named rows",
        ),
        row(
            "wcs_event_topic_map",
            "DISCOVERED" if has_wcs else "MODELED",
            "WCSEvents.asc + MsgWCS.asc + MsgMap.asc",
            "Event→topic discoverable; not PLC generation",
        ),
        row(
            "msg_track_queue",
            "MODELED",
            "MsgTrack.asc",
            "Often zero-byte on transport/sawtooth controllers",
        ),
        row(
            "sorter_model_schema",
            "MODELED",
            "docs/SORTER_COMPILER_MODEL.md + subsystem_model.json",
            "Generic SorterModel fields defined for future compilers",
        ),
        row(
            "sorter_track_plc_generation",
            "PHASE1_SUPPORTED",
            "tools/libraries/programs/Sorter_Track_Program.L5X + fortna_sorter_pack_compiler.py",
            (
                "Phase 1: pack architecture + model multiplicity (encoders/diverts/tracking). "
                "WCS external. Not byte-for-byte finished-PLC match."
            ),
        ),
        row(
            "wcs_interface_plc_generation",
            "NOT_SUPPORTED",
            "tools/libraries/programs/WCS_Interface_TCP_IP_Program.L5X",
            "Gold pack merge only; no RUN→WCS generic compiler",
        ),
        row(
            "shipping_sorter_area_l3_generation",
            "NOT_SUPPORTED",
            "tools/libraries/programs/ShippingSorter_Area_L3_Program.L5X",
            "Gold pack; site wiring engineer-required",
        ),
        row(
            "trk_divert_wave_aoi_reuse",
            "CONFIGURATION_REQUIRED",
            "tools/libraries/TRK_Divert_WaveFunction_AOI.L5X",
            "AOI available; divert count / IO mapping needs engineer or sorter_build UI",
        ),
        row(
            "encoder_routine_stub_reuse",
            "CONFIGURATION_REQUIRED",
            "tools/libraries/Enc_Routine_ST.L5X",
            "Pattern stub; site encoder tags/config required",
        ),
        row(
            "mhs_guideline_sorter_scaffolds",
            "CONFIGURATION_REQUIRED",
            "tools/scripts/fortna_mhs_sorter.py",
            "FMS/Non-Con guideline scaffolds — not FortnaPlus RUN-driven Sorter_Track",
        ),
        row(
            "divert_io_and_lane_plc_map",
            "NOT_SUPPORTED",
            "gaps.divert_io_map",
            "No complete RUN→PLC divert output map for generic emit",
        ),
        row(
            "tracking_conveyor_chain_generation",
            "NOT_SUPPORTED",
            "gaps.tracking_conveyor_chain",
            "Induct/tracking chain not fully derivable from RUN track tables alone",
        ),
    ]

    return {
        "generated_at": _ts(),
        "machine": (model.get("machine") or {}).get("value")
        if isinstance(model.get("machine"), dict)
        else model.get("machine"),
        "policy": (
            "Tracking/WCS PLC generation is NOT_SUPPORTED unless a complete generic "
            "library path already exists. Site-fixed gold packs do not qualify."
        ),
        "status_legend": [
            "DISCOVERED",
            "MODELED",
            "GENERATABLE",
            "CONFIGURATION_REQUIRED",
            "NOT_SUPPORTED",
        ],
        "capabilities": caps,
        "counts": {
            "DISCOVERED": sum(1 for c in caps if c["status"] == "DISCOVERED"),
            "MODELED": sum(1 for c in caps if c["status"] == "MODELED"),
            "GENERATABLE": sum(1 for c in caps if c["status"] == "GENERATABLE"),
            "CONFIGURATION_REQUIRED": sum(
                1 for c in caps if c["status"] == "CONFIGURATION_REQUIRED"
            ),
            "NOT_SUPPORTED": sum(1 for c in caps if c["status"] == "NOT_SUPPORTED"),
        },
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _fv(field: Any) -> Any:
    if isinstance(field, dict) and "value" in field:
        return field.get("value")
    return field


def summarize_autofill_coverage(model: dict[str, Any]) -> dict[str, Any]:
    """Count Gate F fields by authority bucket (not a fake percentage)."""
    rows = list(model.get("gate_f_fields") or [])
    buckets = {
        "PROVEN": [],
        "DERIVED": [],
        "ENGINEER_REQUIRED": [],
        "UNKNOWN": [],
        "OTHER": [],
    }
    for r in rows:
        auth = str(r.get("authority") or AUTH_UNKNOWN).upper()
        label = r.get("field") or ""
        if auth == AUTH_PROVEN:
            buckets["PROVEN"].append(label)
        elif auth == AUTH_DERIVED:
            buckets["DERIVED"].append(label)
        elif auth in {AUTH_REVIEW, "ENGINEER_REQUIRED", "REVIEW"}:
            buckets["ENGINEER_REQUIRED"].append(label)
        elif auth == AUTH_UNKNOWN:
            buckets["UNKNOWN"].append(label)
        else:
            buckets["OTHER"].append(label)
    total = len(rows)
    return {
        "total_gate_f_fields": total,
        "PROVEN": {"count": len(buckets["PROVEN"]), "fields": buckets["PROVEN"]},
        "DERIVED": {"count": len(buckets["DERIVED"]), "fields": buckets["DERIVED"]},
        "ENGINEER_REQUIRED": {
            "count": len(buckets["ENGINEER_REQUIRED"]),
            "fields": buckets["ENGINEER_REQUIRED"],
        },
        "UNKNOWN": {"count": len(buckets["UNKNOWN"]), "fields": buckets["UNKNOWN"]},
        "OTHER": {"count": len(buckets["OTHER"]), "fields": buckets["OTHER"]},
    }


def write_plc5_sorter_deep_reports(
    model: dict[str, Any],
    out_dir: Path,
) -> dict[str, str]:
    """Write Gate F authority + deep autofill coverage artifacts."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage = summarize_autofill_coverage(model)
    gate_rows = list(model.get("gate_f_fields") or [])
    cov = model.get("coverage") or {}
    induct = model.get("induct") or {}
    app = model.get("application_structure") or {}

    auth_json = {
        "generated_at": _ts(),
        "machine": model.get("machine"),
        "source_of_truth": model.get("source_of_truth"),
        "plc_generation": model.get("plc_generation") or "NOT_STARTED",
        "fields": gate_rows,
        "autofill_coverage": coverage,
    }
    auth_json_path = out_dir / "plc5_sorter_field_authority.json"
    _write_json(auth_json_path, auth_json)

    auth_md_lines = [
        "# PLC5 Sorter Field Authority (Gate F)",
        "",
        f"**Generated:** `{auth_json['generated_at']}`  ",
        f"**Machine (discovery outcome):** `{model.get('machine') or ''}`  ",
        f"**PLC generation:** **{model.get('plc_generation') or 'NOT_STARTED'}**  ",
        "",
        "Authority classes: `PROVEN` / `DERIVED` / `REVIEW_REQUIRED` / `UNKNOWN`.",
        "No finished-PLC L5X used as discovery input. No site-name production hardcodes.",
        "",
        "## Fields",
        "",
    ]
    for r in gate_rows:
        auth_md_lines.extend(
            [
                f"### {r.get('field')}",
                "",
                f"- **PRIMARY EVIDENCE:** {r.get('primary_evidence')}",
                f"- **SUPPORTING EVIDENCE:** {r.get('supporting_evidence')}",
                f"- **RELATIONSHIP PATH:** {r.get('relationship_path')}",
                f"- **AUTHORITY:** `{r.get('authority')}`",
                f"- **AUTOPOPULATE:** {'YES' if r.get('autopopulate') else 'NO'}",
                f"- **ENGINEER ACTION:** {r.get('engineer_action')}",
                f"- **WHY:** {r.get('why')}",
                "",
            ]
        )
    auth_md_lines.extend(
        [
            "## Autofill coverage (Gate F rows)",
            "",
            f"- PROVEN: **{coverage['PROVEN']['count']}** / {coverage['total_gate_f_fields']}",
            f"- DERIVED: **{coverage['DERIVED']['count']}** / {coverage['total_gate_f_fields']}",
            f"- ENGINEER_REQUIRED: **{coverage['ENGINEER_REQUIRED']['count']}** / {coverage['total_gate_f_fields']}",
            f"- UNKNOWN: **{coverage['UNKNOWN']['count']}** / {coverage['total_gate_f_fields']}",
            "",
        ]
    )
    auth_md_path = out_dir / "plc5_sorter_field_authority.md"
    auth_md_path.write_text("\n".join(auth_md_lines) + "\n", encoding="utf-8")

    deep_json = {
        "generated_at": _ts(),
        "machine": model.get("machine"),
        "sorters_discovered": model.get("sorter_count") or 0,
        "sorter_names": [_fv(s.get("name")) for s in (model.get("sorters") or [])],
        "applications": [_fv(a.get("name")) for a in (model.get("app_controls") or [])],
        "application_structure": app,
        "tracking_sections": len(model.get("tracking_path") or []),
        "encoders": [_fv(e.get("name")) for e in (model.get("encoders") or [])],
        "induct_conveyor": _fv(induct.get("conveyor")),
        "induct_conveyor_authority": (induct.get("authority") or {}).get("conveyor"),
        "induct_pe": _fv(induct.get("photoeye")),
        "induct_pe_authority": (induct.get("authority") or {}).get("photoeye"),
        "induct_encoder": _fv(induct.get("encoder")),
        "tracking_conveyors_resolved": cov.get("tracking_conveyors_resolved"),
        "tracking_pes_resolved": cov.get("tracking_pes_resolved"),
        "tracking_order_resolved": (model.get("field_authority") or {}).get(
            "tracking_order"
        ),
        "scan_bosses": [_fv(b.get("name")) for b in (model.get("scan_bosses") or [])],
        "scan_zones": [_fv(z.get("name")) for z in (model.get("scan_zones") or [])],
        "divert_topology_rows": cov.get("divert_topology_rows"),
        "divert_outputs_resolved": cov.get("divert_outputs_resolved"),
        "divert_pes_resolved": cov.get("divert_pes_resolved"),
        "remaining_review": [
            f.get("field")
            for f in gate_rows
            if str(f.get("authority")) in {AUTH_REVIEW, "REVIEW", "ENGINEER_REQUIRED"}
        ],
        "remaining_unknown": [
            f.get("field")
            for f in gate_rows
            if str(f.get("authority")) == AUTH_UNKNOWN
        ],
        "autofill_coverage": coverage,
        "field_authority": model.get("field_authority") or {},
        "plc_generation": model.get("plc_generation") or "NOT_STARTED",
        "apply_merge_note": (
            "dashboard fortna-plus.js Apply Sorter merges workbook like Safety: "
            "preserves conveyors/areas/safety_build/sawtooth_build; residual "
            "duplication remains vs safety-build.js / transport Apply helpers "
            "(documented for later centralization — Gate N)."
        ),
        "blocks_sorter_track_compiler": [
            "sorter_type (REVIEW)",
            "transport_area (UNKNOWN)",
            "global induct→divert track offset (REVIEW)",
            "commissioning / library path incomplete",
            "plc_generation PHASE1_SUPPORTED when sorters present",
        ],
    }
    deep_json_path = out_dir / "plc5_sorter_deep_autofill.json"
    _write_json(deep_json_path, deep_json)

    deep_md = [
        "# PLC5 Sorter Deep Autofill",
        "",
        f"**Generated:** `{deep_json['generated_at']}`  ",
        f"**Machine (discovery outcome):** `{model.get('machine') or ''}`  ",
        f"**PLC generation:** **{deep_json['plc_generation']}**  ",
        "",
        "## Counts",
        "",
        f"| Item | Value |",
        f"|------|------:|",
        f"| Sorters discovered | **{deep_json['sorters_discovered']}** |",
        f"| Applications | {len(deep_json['applications'])} |",
        f"| Tracking sections | {deep_json['tracking_sections']} |",
        f"| Encoders | {len(deep_json['encoders'])} |",
        f"| Induct conveyor | `{deep_json['induct_conveyor'] or '—'}` ({deep_json['induct_conveyor_authority']}) |",
        f"| Induct PE | `{deep_json['induct_pe'] or '—'}` ({deep_json['induct_pe_authority']}) |",
        f"| Tracking conveyors resolved | **{deep_json['tracking_conveyors_resolved']}** / {deep_json['tracking_sections']} |",
        f"| Tracking PEs resolved | **{deep_json['tracking_pes_resolved']}** / {deep_json['tracking_sections']} |",
        f"| Tracking order | `{deep_json['tracking_order_resolved']}` |",
        f"| Scan bosses | {len(deep_json['scan_bosses'])} |",
        f"| Scan zones | {len(deep_json['scan_zones'])} |",
        f"| Divert topology rows | **{deep_json['divert_topology_rows']}** |",
        f"| Divert outputs resolved | **{deep_json['divert_outputs_resolved']}** |",
        f"| Divert PEs resolved (distinct Verify I/O) | **{deep_json['divert_pes_resolved']}** |",
        "",
        "## Autofill coverage (Gate F)",
        "",
        f"- **{coverage['PROVEN']['count']} / {coverage['total_gate_f_fields']} PROVEN**",
        f"- **{coverage['DERIVED']['count']} / {coverage['total_gate_f_fields']} DERIVED**",
        f"- **{coverage['ENGINEER_REQUIRED']['count']} / {coverage['total_gate_f_fields']} ENGINEER_REQUIRED**",
        f"- **{coverage['UNKNOWN']['count']} / {coverage['total_gate_f_fields']} UNKNOWN**",
        "",
        "### PROVEN fields",
        "",
    ]
    for f in coverage["PROVEN"]["fields"]:
        deep_md.append(f"- {f}")
    deep_md.extend(["", "### DERIVED fields", ""])
    for f in coverage["DERIVED"]["fields"]:
        deep_md.append(f"- {f}")
    deep_md.extend(["", "### ENGINEER_REQUIRED fields", ""])
    for f in coverage["ENGINEER_REQUIRED"]["fields"]:
        deep_md.append(f"- {f}")
    deep_md.extend(["", "### UNKNOWN fields", ""])
    for f in coverage["UNKNOWN"]["fields"]:
        deep_md.append(f"- {f}")
    deep_md.extend(
        [
            "",
            "## Still blank / why",
            "",
            "- **Sorter type:** no RUN type column — engineer selects pattern.",
            "- **Transport Area:** no schema edge sorter→Areas.",
            "- **Track offset (global):** Outpoint Location is per-lane ticks only.",
            "- **Divert confirm PE:** FullClearTimer names are hints; Verify I/O often "
            "mirrors divert solenoid (not counted as PE).",
            "- **ENC→conveyor:** never by numeric suffix; only EnableBit→Mtrchain when "
            "both motor names exist as Conveyor IO.",
            "",
            "## Apply merge (Gate N)",
            "",
            deep_json["apply_merge_note"],
            "",
            "## Blocks Sorter_Track compiler",
            "",
        ]
    )
    for b in deep_json["blocks_sorter_track_compiler"]:
        deep_md.append(f"- {b}")
    deep_md.append("")
    deep_md_path = out_dir / "plc5_sorter_deep_autofill.md"
    deep_md_path.write_text("\n".join(deep_md) + "\n", encoding="utf-8")

    return {
        "field_authority_md": str(auth_md_path),
        "field_authority_json": str(auth_json_path),
        "deep_autofill_md": str(deep_md_path),
        "deep_autofill_json": str(deep_json_path),
    }


def discover(
    run_dir: Path,
    machine: str = "",
    *,
    out_dir: Path | None = None,
    subsystem_only: bool = False,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if (run_dir / "RUN").is_dir() and not (run_dir / "FORTNA").is_dir():
        run_dir = run_dir / "RUN"
    machine = _read_machine(run_dir, machine)
    inventory = inventory_run(run_dir, machine)
    model = build_subsystem_model(inventory, machine)
    canonical = build_canonical_sorter_model(run_dir, machine)
    # Keep subsystem + canonical aligned on divert / tracking / authority.
    model["divert_rows"] = canonical.get("divert_rows") or model.get("divert_rows") or []
    model["tracking_path"] = canonical.get("tracking_path") or model.get("tracking_path") or []
    model["field_authority"] = canonical.get("field_authority") or model.get("field_authority")
    model["plc_generation"] = (
        "PHASE1_SUPPORTED" if model.get("sorter_count") else "NOT_APPLICABLE"
    )
    matrix = build_generation_support_matrix(model)

    result = {
        "inventory": inventory,
        "subsystem_model": model,
        "canonical_sorter_model": canonical,
        "generation_support_matrix": matrix,
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "subsystem_model.json", model)
        _write_json(out_dir / "canonical_sorter_model.json", canonical)
        if not subsystem_only:
            _write_json(out_dir / "table_inventory.json", inventory)
            _write_json(out_dir / "generation_support_matrix.json", matrix)

    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, help="Path to RUN extract (contains FORTNA/)")
    ap.add_argument("--machine", default="", help="Controller MACHINENAME (e.g. ORNCCP4)")
    ap.add_argument("--out", default="", help="Output directory for JSON artifacts")
    ap.add_argument(
        "--subsystem-only",
        action="store_true",
        help="Write only subsystem_model.json",
    )
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else None
    result = discover(
        Path(args.run_dir),
        args.machine,
        out_dir=out,
        subsystem_only=args.subsystem_only,
    )
    inv = result["inventory"]
    model = result["subsystem_model"]
    matrix = result["generation_support_matrix"]
    print(
        f"machine={inv.get('machine')} tables={inv.get('table_count')} "
        f"active_tables={inv.get('tables_with_active_rows')} "
        f"sorters={model['characterization']['active_sorter_count']['value']} "
        f"encoders={model['characterization']['active_encoder_count']['value']} "
        f"NOT_SUPPORTED={matrix['counts']['NOT_SUPPORTED']} "
        f"GENERATABLE={matrix['counts']['GENERATABLE']}"
    )
    if out:
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
