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
                "role": "Gold Sorter_Track program pack (Greensboro PLC5 pattern)",
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


def build_divert_rows(zone_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """SrtZoneLane → divert topology rows; output IO stays REVIEW when INVALID."""
    out: list[dict[str, Any]] = []
    for z in zone_rows:
        name = _clean(z.get("Name"))
        lane = _clean(z.get("Lane"))
        if not _meaningful(name) and not _meaningful(lane):
            continue
        enable_sig = _clean(z.get("LaneEnableSignal"))
        host = _clean(z.get("HostZone"))
        app = _clean(z.get("AppSorter"))
        enabled = _clean(z.get("Enabled"))
        topology_ok = _meaningful(lane) or _meaningful(host)
        divert_io_auth = _authority(enable_sig, blank_is=AUTH_REVIEW)
        if divert_io_auth == AUTH_PROVEN and enable_sig.upper() == "INVALID":
            divert_io_auth = AUTH_REVIEW
        if not _meaningful(enable_sig) or enable_sig.upper() == "INVALID":
            divert_io_auth = AUTH_REVIEW
            divert_io_value = enable_sig or "INVALID"
        else:
            divert_io_value = enable_sig
        out.append(
            {
                "name": _field(name, "FORTNA/SrtZoneLane.asc"),
                "enabled": _field(enabled, "FORTNA/SrtZoneLane.asc"),
                "app_sorter": _field(app, "FORTNA/SrtZoneLane.asc"),
                "lane": _field(lane, "FORTNA/SrtZoneLane.asc"),
                "host_zone": _field(host, "FORTNA/SrtZoneLane.asc"),
                "full_clear_timer": _field(
                    _clean(z.get("FullClearTimer")), "FORTNA/SrtZoneLane.asc"
                ),
                "lane_enable_signal": _field(enable_sig, "FORTNA/SrtZoneLane.asc"),
                "divert_output_io": _field(
                    divert_io_value,
                    "FORTNA/SrtZoneLane.asc LaneEnableSignal",
                    PROV_ENGINEER if divert_io_auth == AUTH_REVIEW else PROV_RUN,
                ),
                "authority": {
                    "topology": AUTH_PROVEN if topology_ok else AUTH_REVIEW,
                    "lane": _authority(lane),
                    "host_zone": _authority(host),
                    "app_sorter": _authority(app),
                    "divert_output_io": divert_io_auth,
                },
            }
        )
    return out


def build_tracking_path_rows(
    sorters: list[dict[str, Any]],
    encoders_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """One tracking stub per sorter when encoder link is PROVEN; conveyor stays UNKNOWN."""
    rows: list[dict[str, Any]] = []
    for s in sorters:
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
        rows.append(
            {
                "sorter": _field(name, "FORTNA/Sorters.asc"),
                "encoder_tag": _field(enc, "FORTNA/Sorters.asc Encoder ioName"),
                "encoder_ticks_per_foot": _field(
                    (enc_doc or {}).get("ticks_per_foot", {}).get("value")
                    if isinstance((enc_doc or {}).get("ticks_per_foot"), dict)
                    else (enc_doc or {}).get("ticks_per_foot") or "",
                    "FORTNA/Encoders.asc",
                    PROV_RUN if enc_doc else PROV_UNKNOWN,
                ),
                "conveyor": _field("", "not in RUN sorter/encoder join", PROV_UNKNOWN),
                "photoeye": _field("", "not in RUN sorter/encoder join", PROV_UNKNOWN),
                "authority": {
                    "encoder_tag": enc_auth,
                    "conveyor": AUTH_UNKNOWN,
                    "photoeye": AUTH_UNKNOWN,
                },
            }
        )
    return rows


def build_canonical_sorter_model(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Full SorterModel foundation from RUN (all active rows, field authority).

    Does NOT emit PLC / L5X. Divert output IO is REVIEW_REQUIRED when INVALID.
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN").is_dir() and not (run_dir / "FORTNA").is_dir():
        run_dir = run_dir / "RUN"
    machine = _read_machine(run_dir, machine)

    sorter_rows = iter_active_table_rows(run_dir, "Sorters.asc", machine)
    encoder_rows = iter_active_table_rows(run_dir, "Encoders.asc", machine)
    zone_rows = iter_active_table_rows(run_dir, "SrtZoneLane.asc", machine)
    app_rows = iter_active_table_rows(run_dir, "SrtAppControl.asc", machine)
    boss_rows = iter_active_table_rows(run_dir, "SrtScanBoss.asc", machine)

    sorters: list[dict[str, Any]] = []
    for s in sorter_rows:
        name = _clean(s.get("Sorter Name") or s.get("Name"))
        if not _meaningful(name):
            continue
        enc = _clean(s.get("Encoder ioName") or s.get("Encoder Name"))
        mach = _clean(s.get("Machine") or machine)
        sorters.append(
            {
                "name": _field(name, "FORTNA/Sorters.asc"),
                "encoder_io": _field(enc, "FORTNA/Sorters.asc"),
                "machine": _field(mach, "FORTNA/Sorters.asc"),
                "authority": {
                    "name": AUTH_PROVEN,
                    "encoder_io": _authority(enc),
                    "machine": _authority(mach) if mach else AUTH_DERIVED,
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

    divert_rows = build_divert_rows(zone_rows)
    tracking_path = build_tracking_path_rows(sorters, encoders_by_name)

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

    zone_lanes = [
        {
            "name": d["name"],
            "enabled": d["enabled"],
            "app_sorter": d["app_sorter"],
            "lane": d["lane"],
            "host_zone": d["host_zone"],
            "full_clear_timer": d["full_clear_timer"],
            "authority": d["authority"],
        }
        for d in divert_rows
    ]

    field_authority = {
        "sorter_existence": AUTH_PROVEN if sorters else AUTH_UNKNOWN,
        "sorter_identity": AUTH_PROVEN if sorters else AUTH_UNKNOWN,
        "sorter_encoder_link": (
            AUTH_PROVEN
            if sorters and all(
                (s.get("authority") or {}).get("encoder_io") == AUTH_PROVEN
                for s in sorters
            )
            else (AUTH_DERIVED if sorters else AUTH_UNKNOWN)
        ),
        "encoder_parameters": AUTH_PROVEN if encoders else AUTH_UNKNOWN,
        "app_control": AUTH_PROVEN if apps else AUTH_UNKNOWN,
        "scan_boss": AUTH_PROVEN if scan_bosses else AUTH_UNKNOWN,
        "divert_lane_topology": AUTH_PROVEN if divert_rows else AUTH_UNKNOWN,
        "divert_output_io": AUTH_REVIEW,
        "tracking_conveyor_chain": AUTH_UNKNOWN,
        "sorter_type": AUTH_REVIEW,
        "plc_generation": "NOT_STARTED",
    }

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
        "zone_lanes": zone_lanes,
        "divert_rows": divert_rows,
        "tracking_path": tracking_path,
        "field_authority": field_authority,
        "generation_state": "NOT_SUPPORTED",
        "plc_generation": "NOT_STARTED",
        "note": (
            "Canonical model + UI populate only. Sorter_Track L5X generation "
            "remains NOT_STARTED / REVIEW until a generic library path exists."
        ),
    }


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
                "packs exist but are Greensboro-fixed; no complete generic library path."
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
            "NOT_SUPPORTED",
            "tools/libraries/programs/Sorter_Track_Program.L5X + fortna_sorter_build.py",
            (
                "Gold Greensboro pack with token-rename/divert-limit only — "
                "not a complete generic library path"
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
            "library path already exists. Greensboro gold packs do not qualify."
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
    model["plc_generation"] = "NOT_STARTED"
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
