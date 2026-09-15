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

_DEVICE_RE = re.compile(
    r"^(?:T_)?(?:\d*ES\d[\w]*|ES\d[\w]*|ESR\d[\w]*|MCR\d[\w]*|ESLS\d[\w]*|\d+ES)$",
    re.I,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(s: Any) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^\w]", "_", str(s or "").strip())).strip("_")


def _classify_device(name: str) -> str:
    u = (name or "").upper()
    if "ESR" in u:
        return "ESR"
    if "MCR" in u:
        return "MCR"
    if "ESLS" in u or u.endswith("LS") and u.startswith("ES"):
        return "ESLS"
    if _DEVICE_RE.match(name or ""):
        return "ESTOP"
    return "OTHER"


def _digits(token: str) -> set[str]:
    return set(re.findall(r"\d{2,4}", token or ""))


def discover_safety_devices(run_dir: Path | str, machine: str) -> list[dict[str, Any]]:
    """Inventory of Safety devices from RUN (EStop model). Refs only — no invent."""
    em = build_estop_model(run_dir, machine)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in em.get("devices") or []:
        name = str(d.get("name") or "").strip()
        if not name or name.upper() in seen:
            continue
        seen.add(name.upper())
        kind = _classify_device(name)
        out.append(
            {
                "id": name,
                "name": name,
                "kind": kind,
                "normalized": d.get("normalized_name") or _safe(name),
                "io_word": d.get("io_word") or "",
                "io_bit": d.get("io_bit") or "",
                "reset_station": d.get("reset_station") or "",
                "origin": ORIGIN_AUTO,
                "evidence": list(d.get("evidence") or []),
                "physicalIoRef": {
                    "io_word": d.get("io_word") or "",
                    "io_bit": d.get("io_bit") or "",
                }
                if (d.get("io_word") or d.get("io_bit"))
                else None,
            }
        )
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
    if eng.get("name") and eng.get("name") != z.get("name"):
        z["name"] = str(eng["name"]).strip()
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
    eng_by_name = {
        str(z.get("name") or z.get("id") or "").strip(): z
        for z in eng_zones_list
        if z and (z.get("name") or z.get("id"))
    }

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
    # Ensure every engineer zone appears even if Transport dropped it
    for name, ez in eng_by_name.items():
        if not any(str(z.get("name") or "") == name for z in seed_zones):
            seed_zones.append(
                {
                    "name": name,
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
        auto = {
            "id": ir.name,
            "name": ir.name,
            "areaRef": area,
            "areaOrigin": ORIGIN_AUTO,
            "conveyorRefs": convs,
            "conveyorsOrigin": ORIGIN_AUTO if convs else ORIGIN_UNRESOLVED,
            "members": list(ir.members or []),
            "membersOrigin": ORIGIN_AUTO if ir.members else ORIGIN_UNRESOLVED,
            "eStops": [m for m in (ir.members or []) if _classify_device(m) == "ESTOP"],
            "esrDevices": [m for m in (ir.members or []) if _classify_device(m) == "ESR"],
            "mcrDevices": [m for m in (ir.members or []) if _classify_device(m) == "MCR"],
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
        }
        merged = _merge_engineer_zone(auto, eng_by_name.get(ir.name))
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

    assigned = {str(m).upper() for z in zones_out for m in (z.get("members") or [])}
    unassigned = [d for d in devices if d["name"].upper() not in assigned]

    model = {
        "kind": "SafetyModel",
        "version": 1,
        "machine": machine,
        "generated_at": _ts(),
        "devices": devices,
        "zones": zones_out,
        "unassignedDevices": [d["name"] for d in unassigned],
        "counts": {
            "zones": len(zones_out),
            "ready": sum(1 for z in zones_out if z.get("status") == "READY"),
            "review_required": sum(
                1 for z in zones_out if z.get("status") == "REVIEW_REQUIRED"
            ),
            "devices": len(devices),
            "estops": sum(1 for d in devices if d.get("kind") == "ESTOP"),
            "unassigned_estops": sum(
                1 for d in unassigned if d.get("kind") == "ESTOP"
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
        },
    }
    return model


def safety_build_workbook_payload(model: dict[str, Any]) -> dict[str, Any]:
    """Serialize SafetyModel → workbook.safety_build for Autogen/ES compiler."""
    zones = []
    for z in model.get("zones") or []:
        zones.append(
            {
                "id": z.get("id") or z.get("name"),
                "name": z.get("name"),
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
            }
        )
    return {
        "version": 1,
        "source": "safety_build",
        "appliedAt": _ts(),
        "zones": zones,
        "devices": [
            {"name": d.get("name"), "kind": d.get("kind")}
            for d in (model.get("devices") or [])
        ],
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
