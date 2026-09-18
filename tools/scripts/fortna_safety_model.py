#!/usr/bin/env python3
"""Canonical SafetyModel — Site Forge Safety Build subsystem.

Philosophy:
  AUTO DISCOVER (RUN proven) → ENGINEER REVIEW/CORRECT → APPLY → GENERATE PLC

SafetyModel references Areas / Conveyors / HardwareIO endpoints — it does NOT
own a second Transportation copy.

Engineer overrides are authoritative and must survive rediscovery.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    safety_readiness,
)
from fortna_estop_model import build_estop_model  # noqa: E402

ORIGIN_AUTO = "AUTO_RUN_PROVEN"
ORIGIN_ENGINEER = "ENGINEER_ASSIGNED"
ORIGIN_SUGGESTED = "SUGGESTED_DIGIT_MATCH"
ORIGIN_UNRESOLVED = "UNRESOLVED"

# Engineer Hardware I/O prefixes (T_2ES, CP2_ESR1, T_2MCR1, CP2_CS) + RUN names
# (2ES, 2ESR1_AUX, 2MCR1, ESLS125).
_DEVICE_RE = re.compile(
    r"^(?:"
    r"T_\d+ES\d*\w*"  # T_2ES, T_2ES1
    r"|T_\d+MCR\d*\w*"  # T_2MCR1
    r"|T_\d+ESR\d*\w*"  # T_2ESR1
    r"|CP\d+_ESR\d*\w*"  # CP2_ESR1
    r"|CP\d+_MCR\d*\w*"  # CP2_MCR1
    r"|CP\d+_CS\d*"  # CP2_CS control station / reset
    r"|CP\d+_ES\d*\w*"  # CP2_ES…
    r"|\d+ESR\d*\w*"  # 2ESR1_AUX
    r"|\d+MCR\d*\w*"  # 2MCR1, 2MCR1_AUX
    r"|ESR\d*\w*"
    r"|MCR\d*\w*"
    r"|ESLS\d*\w*"
    r"|ES\d[\w]*"  # ES400, ES406, ESLS handled above
    r"|\d+ES\d*\w*"  # 2ES, 4ES
    r"|T_\d+ES$"
    r")$",
    re.I,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(s: Any) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^\w]", "_", str(s or "").strip())).strip("_")


def _classify_device(name: str) -> str:
    """Classify Safety device kind from RUN or engineer Hardware I/O name."""
    u = (name or "").strip().upper().replace("-", "_")
    if not u:
        return ""
    if "ESLS" in u:
        return "ESLS"
    if re.search(r"ESR\d*|ESR_", u) or "_ESR" in u or u.startswith("ESR"):
        return "ESR"
    if re.search(r"MCR\d*", u) or "_MCR" in u or u.startswith("MCR"):
        return "MCR"
    # Control station used for Area reset/silence (CP2_CS)
    if re.match(r"^CP\d+_CS\d*$", u) or u.endswith("_CS"):
        return "CS"
    if _DEVICE_RE.match(u) or re.search(r"(^|_)ES\d", u) or re.match(r"^(?:T_)?\d+ES$", u):
        return "ESTOP"
    return ""


def _digits(token: str) -> set[str]:
    return set(re.findall(r"\d{2,4}", token or ""))


def _provenance_from_evidence(
    evidence: list[dict[str, Any]],
    *,
    engineer_name: str = "",
    physical_address: str = "",
) -> dict[str, str]:
    """Derive source / sourceTable / confidence from first evidence entry."""
    first = (evidence[0] if evidence else {}) or {}
    kind = str(first.get("kind") or "")
    table = str(first.get("table") or first.get("file") or "")
    if kind == "hardware_io_engineer_name" or engineer_name:
        return {
            "source": "HARDWARE_IO",
            "sourceTable": table or "hardware_io",
            "confidence": "PROVEN",
        }
    if kind == "conveyor_asc_safety_name" or table:
        prov = str(first.get("provenance") or "RUN_EXPLICIT").upper()
        return {
            "source": "RUN",
            "sourceTable": table or "Conveyor.asc",
            "confidence": "SUGGESTED" if "SUGGEST" in prov else "PROVEN",
        }
    if kind:
        return {
            "source": kind if kind.isupper() else "RUN",
            "sourceTable": table,
            "confidence": "PROVEN",
        }
    if physical_address:
        return {"source": "HARDWARE_IO", "sourceTable": "hardware_io", "confidence": "PROVEN"}
    return {"source": "RUN", "sourceTable": "", "confidence": "UNRESOLVED"}


def _physical_endpoint_summary(
    *,
    physical_io_ref: dict[str, Any] | None,
    physical_address: str = "",
    io_word: str = "",
    io_bit: str = "",
) -> str:
    if physical_address:
        return str(physical_address)
    if physical_io_ref:
        w = str(physical_io_ref.get("io_word") or "")
        b = str(physical_io_ref.get("io_bit") or "")
        if w and b:
            return f"{w}.{b}"
        if w or b:
            return w or b
        addr = physical_io_ref.get("physical_address") or physical_io_ref.get("address")
        if addr:
            return str(addr)
    if io_word and io_bit:
        return f"{io_word}.{io_bit}"
    return io_word or io_bit or ""


def _add_device(
    out: list[dict[str, Any]],
    seen: set[str],
    *,
    name: str,
    evidence: list[dict[str, Any]],
    io_word: str = "",
    io_bit: str = "",
    reset_station: str = "",
    normalized: str = "",
    engineer_name: str = "",
    physical_address: str = "",
) -> None:
    name = str(name or "").strip()
    if not name or name.upper() in {"N/A", "INVALID", "NONE"}:
        return
    kind = _classify_device(name)
    if not kind:
        return
    key = name.upper()
    if key in seen:
        return
    seen.add(key)
    phys_ref = {"io_word": io_word, "io_bit": io_bit} if (io_word or io_bit) else None
    if physical_address:
        phys_ref = {**(phys_ref or {}), "physical_address": physical_address}
    prov = _provenance_from_evidence(
        evidence,
        engineer_name=engineer_name,
        physical_address=physical_address,
    )
    out.append(
        {
            "id": name,
            "name": name,
            "kind": kind,
            "normalized": normalized or _safe(name),
            "io_word": io_word or "",
            "io_bit": io_bit or "",
            "reset_station": reset_station or "",
            "origin": ORIGIN_AUTO,
            "evidence": evidence,
            "physicalIoRef": phys_ref,
            # Blank-preserving fields — stamped after zone membership merge
            "safetyZoneRef": None,
            "status": "UNASSIGNED",
            "source": prov["source"],
            "sourceTable": prov["sourceTable"],
            "originalName": name,
            "engineerName": engineer_name or "",
            "physicalEndpoint": _physical_endpoint_summary(
                physical_io_ref=phys_ref,
                physical_address=physical_address,
                io_word=io_word,
                io_bit=io_bit,
            ),
            "classification": kind,
            "confidence": prov["confidence"],
        }
    )


def discover_safety_devices(run_dir: Path | str, machine: str) -> list[dict[str, Any]]:
    """Inventory of Safety devices from RUN.

    Sources:
      - EStop.asc (via estop model)
      - Conveyor.asc IO_Name matching ES / ESR / MCR / ESLS / CP#_CS prefixes
        (includes 2ES, 2ESR1_AUX, 2MCR1 — engineer may rename to T_2ES / CP2_ESR1)
    """
    from fortna_site_model import merge_table_rows  # local import

    run_dir = Path(run_dir)
    em = build_estop_model(run_dir, machine)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in em.get("devices") or []:
        _add_device(
            out,
            seen,
            name=str(d.get("name") or ""),
            evidence=list(d.get("evidence") or []),
            io_word=str(d.get("io_word") or ""),
            io_bit=str(d.get("io_bit") or ""),
            reset_station=str(d.get("reset_station") or ""),
            normalized=str(d.get("normalized_name") or ""),
        )

    fortna = run_dir / "FORTNA"
    if fortna.is_dir():
        try:
            merged = merge_table_rows(fortna, "Conveyor.asc", machine)
            for item in merged.get("rows") or []:
                row = item.get("row") or {}
                name = str(
                    row.get("IO_Name") or row.get("Name") or row.get("Desc") or ""
                ).strip()
                if not name or not _classify_device(name):
                    continue
                _add_device(
                    out,
                    seen,
                    name=name,
                    evidence=[
                        {
                            "kind": "conveyor_asc_safety_name",
                            "table": "Conveyor.asc",
                            "io_name": name,
                            "provenance": item.get("provenance") or "RUN_EXPLICIT",
                        }
                    ],
                    io_word=str(row.get("IO_Address_Word") or ""),
                    io_bit=str(row.get("IO_Address_Bit") or ""),
                )
        except Exception:
            pass

        # Also pick engineer-style aliases if present as separate IO_Name rows
        # (some sites store CP2_ESR1 / T_2ES directly in Conveyor.asc)
        # Already covered by _classify_device + Conveyor scan above.

    # Hardware I/O engineer Names (T_2ES, CP2_ESR1, T_2MCR1, CP2_CS, …)
    try:
        from fortna_hardware_io_overrides import load_overrides

        ov = load_overrides()
        for _addr, ch in (ov.get("channels") or {}).items():
            if not isinstance(ch, dict):
                continue
            ename = str(
                ch.get("engineerName")
                or ch.get("engineer_name")
                or ch.get("name")
                or ""
            ).strip()
            if not ename or not _classify_device(ename):
                continue
            _add_device(
                out,
                seen,
                name=ename,
                evidence=[
                    {
                        "kind": "hardware_io_engineer_name",
                        "physical_address": str(_addr),
                        "engineer_name": ename,
                    }
                ],
                engineer_name=ename,
                physical_address=str(_addr),
            )
    except Exception:
        pass

    return out


def _merge_engineer_zone(
    auto_zone: dict[str, Any],
    eng: dict[str, Any] | None,
) -> dict[str, Any]:
    """Overlay engineer-owned fields onto auto zone. Engineer wins."""
    z = dict(auto_zone)
    if not eng:
        return z
    # Engineer-owned membership
    if "members" in eng and eng.get("members") is not None:
        z["members"] = [str(m).strip() for m in (eng.get("members") or []) if str(m).strip()]
        z["membersOrigin"] = ORIGIN_ENGINEER
        z["eStops"] = [m for m in z["members"] if _classify_device(m) == "ESTOP"]
        z["esrDevices"] = [m for m in z["members"] if _classify_device(m) == "ESR"]
        z["mcrDevices"] = [m for m in z["members"] if _classify_device(m) == "MCR"]
    if eng.get("area") or eng.get("areaRef"):
        z["areaRef"] = str(eng.get("area") or eng.get("areaRef") or "").strip()
        z["areaOrigin"] = ORIGIN_ENGINEER
    if eng.get("conveyors") or eng.get("conveyorRefs"):
        refs = eng.get("conveyorRefs") or eng.get("conveyors") or []
        z["conveyorRefs"] = [str(c).strip() for c in refs if str(c).strip()]
        z["conveyorsOrigin"] = ORIGIN_ENGINEER
    if eng.get("resetSource") or eng.get("reset_source"):
        z["resetSource"] = str(eng.get("resetSource") or eng.get("reset_source") or "").strip()
        z["resetOrigin"] = ORIGIN_ENGINEER
    if eng.get("silenceSource") or eng.get("silence_source"):
        z["silenceSource"] = str(
            eng.get("silenceSource") or eng.get("silence_source") or ""
        ).strip()
        z["silenceOrigin"] = ORIGIN_ENGINEER
    # Gate I — engineering_name editable; source_id immutable
    src = str(eng.get("source_id") or eng.get("sourceId") or z.get("source_id") or z.get("name") or "").strip()
    if src:
        z["source_id"] = src
        z["id"] = src
    eng_name = str(
        eng.get("engineering_name") or eng.get("engineeringName") or ""
    ).strip()
    if eng_name:
        z["engineering_name"] = eng_name
        z["name"] = eng_name
        z["nameOrigin"] = ORIGIN_ENGINEER
    elif eng.get("name") and eng.get("name") != z.get("name"):
        # Legacy rename path — treat name as engineering_name, keep source_id
        z["engineering_name"] = str(eng["name"]).strip()
        z["name"] = z["engineering_name"]
        z["nameOrigin"] = ORIGIN_ENGINEER
    z["engineerEdited"] = True
    return z


def suggest_devices_for_zone(
    zone: dict[str, Any],
    devices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Digit-match suggestions — NOT auto-proven. Engineer must accept."""
    conv_digits: set[str] = set()
    for c in zone.get("conveyorRefs") or []:
        conv_digits |= _digits(str(c))
    area_digits = _digits(str(zone.get("areaRef") or ""))
    want = conv_digits | area_digits
    if not want:
        return []
    suggestions = []
    assigned = {str(m).upper() for m in (zone.get("members") or [])}
    for d in devices:
        name = d.get("name") or ""
        if name.upper() in assigned:
            continue
        if _digits(name) & want:
            suggestions.append(
                {
                    "name": name,
                    "kind": d.get("kind"),
                    "origin": ORIGIN_SUGGESTED,
                    "evidence": [
                        {
                            "kind": "digit_match_suggestion",
                            "device": name,
                            "matched_digits": sorted(_digits(name) & want),
                            "note": "Suggestion only — not RUN-proven zone membership",
                        }
                    ],
                }
            )
    return suggestions


def build_safety_model(
    *,
    run_dir: Path | str | None,
    machine: str,
    transport_zones: list[dict[str, Any]] | None = None,
    areas: list[str] | None = None,
    area_conveyors: dict[str, list[str]] | None = None,
    engineer_safety_build: dict[str, Any] | None = None,
    library_has_aois: bool = True,
) -> dict[str, Any]:
    """Build canonical SafetyModel.

    transport_zones: from Transport Apply [{name, area, conveyors, members?}]
    engineer_safety_build: persisted workbook.safety_build (engineer authoritative)
    """
    eng_build = dict(engineer_safety_build or {})
    eng_zones_list = list(eng_build.get("zones") or [])
    eng_by_name: dict[str, dict[str, Any]] = {}
    for z in eng_zones_list:
        if not z:
            continue
        for key in (
            z.get("source_id"),
            z.get("sourceId"),
            z.get("id"),
            z.get("engineering_name"),
            z.get("name"),
        ):
            k = str(key or "").strip()
            if k and k not in eng_by_name:
                eng_by_name[k] = z

    devices: list[dict[str, Any]] = []
    if run_dir:
        try:
            devices = discover_safety_devices(run_dir, machine)
        except Exception as ex:
            devices = []
            disc_err = str(ex)
        else:
            disc_err = None
    else:
        disc_err = "no_run_dir"

    # Seed zone shells from Transport + named safety zones + engineer build
    seed_zones = list(transport_zones or [])
    named = list(eng_build.get("safety_zones") or [])  # optional explicit names

    def _seed_ids(z: dict[str, Any]) -> set[str]:
        return {
            str(x or "").strip()
            for x in (
                z.get("source_id"),
                z.get("sourceId"),
                z.get("id"),
                z.get("name"),
                z.get("engineering_name"),
            )
            if str(x or "").strip()
        }

    # Ensure every engineer zone appears even if Transport dropped it.
    # Gate I — match by source_id so a rename does not duplicate the shell.
    seen_eng: set[str] = set()
    for ez in eng_zones_list:
        if not ez:
            continue
        sid = str(
            ez.get("source_id") or ez.get("sourceId") or ez.get("id") or ez.get("name") or ""
        ).strip()
        if not sid or sid in seen_eng:
            continue
        seen_eng.add(sid)
        already = any(sid in _seed_ids(z) for z in seed_zones)
        if already:
            continue
        seed_zones.append(
            {
                "name": sid,  # IR identity = source_id
                "source_id": sid,
                "engineering_name": str(
                    ez.get("engineering_name") or ez.get("name") or sid
                ).strip(),
                "area": ez.get("area") or ez.get("areaRef") or "",
                "conveyors": ez.get("conveyors") or ez.get("conveyorRefs") or [],
                "members": ez.get("members") or [],
            }
        )

    # Named Safety Zone list (workbook.safety_zones) — Area≠Zone stubs
    safety_zone_names = [
        str(z.get("name") or "").strip()
        for z in seed_zones
        if z.get("name")
    ] + [str(n).strip() for n in named if str(n).strip()]
    # Also accept top-level safety_zones on eng_build / caller areas pairing
    for n in eng_build.get("zone_names") or []:
        if str(n).strip():
            safety_zone_names.append(str(n).strip())

    irs = build_safety_zone_irs(
        safety_zones=safety_zone_names,
        areas=list(areas or []),
        estop_model=None,
        engineer_zones=seed_zones,
        default_area=(areas or ["Main_Area"])[0] if (areas or []) else "Main_Area",
        area_conveyors=area_conveyors or {},
    )

    zones_out: list[dict[str, Any]] = []
    for ir in irs:
        area = ir.area or ""
        convs = list(ir.conveyors or [])
        if not convs and area and area_conveyors:
            convs = list((area_conveyors or {}).get(area) or [])
        # Gate J — only keep RUN members when already on IR (proven); never invent
        ir_members = list(ir.members or [])
        auto = {
            "id": ir.name,
            "source_id": ir.name,
            "name": ir.name,
            "engineering_name": ir.name,
            "areaRef": area,
            "areaOrigin": ORIGIN_AUTO,
            "conveyorRefs": convs,
            "conveyorsOrigin": ORIGIN_AUTO if convs else ORIGIN_UNRESOLVED,
            "members": ir_members,
            "membersOrigin": ORIGIN_AUTO if ir_members else ORIGIN_UNRESOLVED,
            "eStops": [m for m in ir_members if _classify_device(m) == "ESTOP"],
            "esrDevices": [m for m in ir_members if _classify_device(m) == "ESR"],
            "mcrDevices": [m for m in ir_members if _classify_device(m) == "MCR"],
            "resetSource": ir.reset_source or (f"{area}.Reset" if area else ""),
            "resetOrigin": ORIGIN_AUTO if area else ORIGIN_UNRESOLVED,
            "silenceSource": ir.silence_source or (f"{area}.Silence" if area else ""),
            "silenceOrigin": ORIGIN_AUTO if area else ORIGIN_UNRESOLVED,
            "physicalIORefs": [],
            "evidence": [
                {
                    "kind": "transport_zone_seed",
                    "zone": ir.name,
                    "area": area,
                    "conveyors": len(convs),
                }
            ],
            "unresolved": [],
            "suggestions": [],
            "engineerEdited": False,
            "status": "UNRESOLVED",
            "runDiscovered": True,
        }
        # Match engineer overlay by source_id first, then display name
        eng_hit = eng_by_name.get(ir.name)
        if not eng_hit:
            for ez in eng_zones_list:
                ez_sid = str(ez.get("source_id") or ez.get("sourceId") or "").strip()
                if ez_sid and ez_sid == ir.name:
                    eng_hit = ez
                    break
                if str(ez.get("engineering_name") or ez.get("name") or "").strip() == ir.name:
                    eng_hit = ez
                    break
        merged = _merge_engineer_zone(auto, eng_hit)
        merged["suggestions"] = suggest_devices_for_zone(merged, devices)
        # Attach physical IO refs for assigned members
        by_dev = {d["name"].upper(): d for d in devices}
        phys = []
        for m in merged.get("members") or []:
            d = by_dev.get(str(m).upper())
            if d and d.get("physicalIoRef"):
                phys.append({"device": m, **d["physicalIoRef"]})
        merged["physicalIORefs"] = phys
        zones_out.append(merged)

    # Readiness via es_compiler field matrix (reuse)
    class _IR:
        def __init__(self, z: dict[str, Any]):
            self.name = z["name"]
            self.area = z.get("areaRef") or ""
            self.members = list(z.get("members") or [])
            self.conveyors = list(z.get("conveyorRefs") or [])
            self.reset_source = z.get("resetSource") or ""
            self.silence_source = z.get("silenceSource") or ""
            self.device_membership_status = (
                "RESOLVED" if self.members else ("UNRESOLVED" if self.conveyors else "NONE")
            )
            self.aggregator_groups = []

        def ensure_aggregators(self) -> None:
            return None

    ready = safety_readiness(
        [_IR(z) for z in zones_out],
        library_has_aois=library_has_aois,
    )
    # Stamp per-zone status from readiness diag
    diag_by = {d.get("name"): d for d in (ready.get("zones") or [])}
    for z in zones_out:
        d = diag_by.get(z["name"]) or {}
        z["fields"] = d.get("fields") or {}
        z["missing"] = d.get("missing") or []
        z["hard_missing"] = d.get("hard_missing") or []
        z["status"] = d.get("zone_status") or (
            "READY" if not z.get("hard_missing") and z.get("members") else "REVIEW_REQUIRED"
        )
        if z["status"] == "UNRESOLVED":
            z["status"] = "REVIEW_REQUIRED"
        z["unresolved"] = list(z.get("hard_missing") or [])

    # Stamp each device with zone membership / assignment status.
    # Never delete unassigned devices — blanks stay visible for engineer review.
    assignment: dict[str, tuple[str, str]] = {}
    for z in zones_out:
        origin = str(z.get("membersOrigin") or "")
        for m in z.get("members") or []:
            key = str(m).upper()
            if key and key not in assignment:
                assignment[key] = (str(z.get("name") or ""), origin)
    for d in devices:
        key = str(d.get("name") or "").upper()
        if key in assignment:
            zone_name, origin = assignment[key]
            d["safetyZoneRef"] = zone_name or None
            if origin == ORIGIN_ENGINEER:
                d["status"] = "ENGINEER_ASSIGNED"
            else:
                d["status"] = "AUTO_RESOLVED"
        else:
            d["safetyZoneRef"] = None
            d["status"] = "UNASSIGNED"
        # Ensure blank-preserving fields survive older device dicts
        d.setdefault("originalName", d.get("name") or "")
        d.setdefault("engineerName", d.get("engineerName") or "")
        d.setdefault("classification", d.get("kind") or "")
        d.setdefault("confidence", d.get("confidence") or "UNRESOLVED")
        d.setdefault("source", d.get("source") or "RUN")
        d.setdefault("sourceTable", d.get("sourceTable") or "")
        d.setdefault(
            "physicalEndpoint",
            _physical_endpoint_summary(
                physical_io_ref=d.get("physicalIoRef"),
                io_word=str(d.get("io_word") or ""),
                io_bit=str(d.get("io_bit") or ""),
            ),
        )

    assigned = set(assignment.keys())
    unassigned = [d for d in devices if d["name"].upper() not in assigned]
    auto_n = sum(1 for d in devices if d.get("status") == "AUTO_RESOLVED")
    eng_n = sum(1 for d in devices if d.get("status") == "ENGINEER_ASSIGNED")
    un_n = sum(1 for d in devices if d.get("status") == "UNASSIGNED")
    devices_found = len(devices)
    zones_ready = sum(1 for z in zones_out if z.get("status") == "READY")
    zones_review = sum(1 for z in zones_out if z.get("status") == "REVIEW_REQUIRED")

    def _names_of(kind: str) -> list[str]:
        return [d["name"] for d in devices if d.get("kind") == kind]

    inventory_by_kind = {
        "ESTOP": _names_of("ESTOP"),
        "ESR": _names_of("ESR"),
        "MCR": _names_of("MCR"),
        "CS": _names_of("CS"),
        "ESLS": _names_of("ESLS"),
        "OTHER": [
            d["name"]
            for d in devices
            if d.get("kind") not in {"ESTOP", "ESR", "MCR", "CS", "ESLS"}
        ],
    }

    model = {
        "kind": "SafetyModel",
        "version": 1,
        "machine": machine,
        "generated_at": _ts(),
        "devices": devices,
        "zones": zones_out,
        "unassignedDevices": [d["name"] for d in unassigned],
        "inventoryByKind": inventory_by_kind,
        "counts": {
            "zones": len(zones_out),
            "ready": zones_ready,
            "review_required": zones_review,
            "zones_ready": zones_ready,
            "zones_review": zones_review,
            "devices": devices_found,
            "devices_found": devices_found,
            "estops": len(inventory_by_kind["ESTOP"]),
            "esr": len(inventory_by_kind["ESR"]),
            "mcr": len(inventory_by_kind["MCR"]),
            "cs": len(inventory_by_kind["CS"]),
            "esls": len(inventory_by_kind["ESLS"]),
            "other_safety": len(inventory_by_kind["OTHER"]),
            "automatically_resolved": auto_n,
            "engineer_assigned": eng_n,
            "unassigned": un_n,
            "unassigned_estops": sum(
                1 for d in unassigned if d.get("kind") == "ESTOP"
            ),
            "completion_pct": round(
                100 * (auto_n + eng_n) / max(1, devices_found)
            ),
            "unresolved_io": sum(
                1
                for z in zones_out
                for f in (z.get("hard_missing") or [])
                if f == "SafetyDevices"
            ),
        },
        "readiness": ready,
        "discovery_error": disc_err,
        "policy": {
            "area_ne_safety_zone": True,
            "engineer_overrides_survive_rediscovery": True,
            "no_silent_es_omit": True,
            "suggestions_are_not_auto_assign": True,
            "partial_es_emit_allowed": True,
        },
    }
    return model


def safety_build_workbook_payload(model: dict[str, Any]) -> dict[str, Any]:
    """Serialize SafetyModel → workbook.safety_build for Autogen/ES compiler."""
    zones = []
    for z in model.get("zones") or []:
        sid = str(z.get("source_id") or z.get("id") or z.get("name") or "").strip()
        eng = str(z.get("engineering_name") or z.get("name") or sid).strip()
        zones.append(
            {
                "id": sid,
                "source_id": sid,
                "name": eng,
                "engineering_name": eng,
                "area": z.get("areaRef") or "",
                "areaRef": z.get("areaRef") or "",
                "conveyors": list(z.get("conveyorRefs") or []),
                "conveyorRefs": list(z.get("conveyorRefs") or []),
                "members": list(z.get("members") or []),
                "eStops": list(z.get("eStops") or []),
                "esrDevices": list(z.get("esrDevices") or []),
                "mcrDevices": list(z.get("mcrDevices") or []),
                "resetSource": z.get("resetSource") or "",
                "silenceSource": z.get("silenceSource") or "",
                "reset_source": z.get("resetSource") or "",
                "silence_source": z.get("silenceSource") or "",
                "membersOrigin": z.get("membersOrigin"),
                "areaOrigin": z.get("areaOrigin"),
                "conveyorsOrigin": z.get("conveyorsOrigin"),
                "status": z.get("status"),
                "fields": z.get("fields") or {},
                "engineerEdited": bool(z.get("engineerEdited")),
                "runDiscovered": bool(z.get("runDiscovered")),
            }
        )
    # Preserve full device records (zone ref / status / evidence / provenance)
    devices_out = []
    for d in model.get("devices") or []:
        if not isinstance(d, dict):
            continue
        devices_out.append(dict(d))
    return {
        "version": 1,
        "source": "safety_build",
        "appliedAt": _ts(),
        "zones": zones,
        "devices": devices_out,
        "unassignedDevices": list(model.get("unassignedDevices") or []),
        "inventoryByKind": dict(model.get("inventoryByKind") or {}),
        "counts": model.get("counts") or {},
        "readiness": model.get("readiness") or {},
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build canonical SafetyModel from RUN")
    ap.add_argument("--run-dir", default="workspace/_plc2_run_peek/RUN")
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", default="exports/plc2-safety/safety_model.json")
    ap.add_argument("--workbook", default="workspace/autogen_workbook.json")
    args = ap.parse_args(argv)
    wb = {}
    wp = Path(args.workbook)
    if wp.is_file():
        wb = json.loads(wp.read_text(encoding="utf-8"))
    area_convs: dict[str, list[str]] = {}
    zone_from_conv: dict[str, dict[str, Any]] = {}
    for c in wb.get("conveyors") or []:
        if not isinstance(c, dict):
            continue
        an = str(c.get("main_area") or c.get("area") or "").strip()
        cn = str(
            c.get("conveyor") or c.get("clean_name") or c.get("name") or ""
        ).strip()
        zn = str(c.get("safety_zone") or c.get("safetyZone") or "").strip()
        if an and cn:
            area_convs.setdefault(an, []).append(cn)
        if zn and cn:
            if zn not in zone_from_conv:
                zone_from_conv[zn] = {"name": zn, "area": an, "conveyors": [], "members": []}
            if an and not zone_from_conv[zn].get("area"):
                zone_from_conv[zn]["area"] = an
            if cn not in zone_from_conv[zn]["conveyors"]:
                zone_from_conv[zn]["conveyors"].append(cn)
    tz = list((wb.get("safety_build") or {}).get("zones") or [])
    # Prefer conveyor.safety_zone seeds when safety_build empty
    if not tz and zone_from_conv:
        tz = list(zone_from_conv.values())
    eng_sb = dict(wb.get("safety_build") or {})
    # Promote workbook.safety_zones into the engineer build for stub creation
    if wb.get("safety_zones") and "zone_names" not in eng_sb:
        eng_sb["zone_names"] = list(wb.get("safety_zones") or [])
    model = build_safety_model(
        run_dir=args.run_dir,
        machine=args.machine,
        transport_zones=tz,
        areas=list(wb.get("areas") or []),
        area_conveyors=area_convs,
        engineer_safety_build=eng_sb,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(
        f"SafetyModel zones={model['counts']['zones']} "
        f"ready={model['counts']['ready']} review={model['counts']['review_required']} "
        f"devices={model['counts']['devices']} → {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
