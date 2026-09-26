#!/usr/bin/env python3
"""Compact five-site Safety corrective-pass diagnostics (Warden re-gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
OUT = ROOT / "tools" / "diagnostics" / "safety_corrective_pass"
OUT.mkdir(parents=True, exist_ok=True)

from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_collision_review,
    apply_hardware_backed_readiness,
)
from fortna_safety_model import build_safety_model  # noqa: E402
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402

SITES = [
    ("ORL_AC3", ROOT / "workspace" / "_orl_ac3_run" / "RUN", "ORL_AC3"),
    ("TOPB-ET", ROOT / "workspace" / "_topb_et_run" / "RUN", "TOPB-ET"),
    ("TFCP1", ROOT / "workspace" / "_tfcp1_run" / "RUN", "TFCP1"),
    ("TPNA1", ROOT / "workspace" / "_tpna1_run" / "RUN", "TPNA1"),
    ("ULTAPICK", ROOT / "workspace" / "_ultapick_run" / "RUN", "ULTAPICK"),
]


def _find_run(machine: str) -> Path | None:
    candidates = [
        ROOT / "workspace" / f"_{machine.lower().replace('-', '_')}_run" / "RUN",
        ROOT / "workspace" / "active" / "RUN",
    ]
    # Broad search under workspace
    ws = ROOT / "workspace"
    if ws.is_dir():
        for p in ws.rglob("project.cfg"):
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if f"Machinename={machine}" in txt or f"Machinename = {machine}" in txt:
                return p.parent
            if machine.upper() in txt.upper() and "Machinename" in txt:
                # Prefer exact
                for line in txt.splitlines():
                    if "machinename" in line.lower() and machine.upper() in line.upper():
                        return p.parent
    for c in candidates:
        if (c / "project.cfg").is_file():
            return c
    return None


def _summarize(model: dict) -> dict:
    devices = list(model.get("safetyDevices") or model.get("devices") or [])
    eu = model.get("evidence_union") or {}
    ready = [
        d for d in devices
        if d.get("hardwareBacked") is True
        and d.get("assignable") is not False
        and not d.get("endpointConflict")
        and str(d.get("endpoint_proof_depth") or "").upper() == "FULL"
    ]
    review = [
        d for d in devices
        if d.get("endpointConflict")
        or d.get("assignable") is False
        or d.get("hardwareBacked") is False
        or "REVIEW" in str(d.get("status") or d.get("readiness") or "").upper()
    ]
    depths = {}
    for d in devices:
        depth = str(d.get("endpoint_proof_depth") or "UNKNOWN").upper()
        depths[depth] = depths.get(depth, 0) + 1
    collisions = eu.get("endpoint_collisions") or model.get("endpoint_collisions") or []
    zones = [z for z in (model.get("zones") or []) if z and not str(z.get("name") or "").lower().startswith("default")]
    default_n = 0
    for z in model.get("zones") or []:
        if "default" in str(z.get("name") or "").lower() or z.get("defaultSafety"):
            default_n = len(z.get("members") or [])
    unsupported = eu.get("unsupported_interface") or model.get("unsupported_interface") or []
    return {
        "machine": model.get("machine"),
        "canonical_devices": len(devices),
        "READY": len(ready),
        "REVIEW": len(review),
        "endpoint_proof_depth": depths,
        "endpoint_collisions": collisions,
        "collision_count": len(collisions),
        "writer_ownership_note": "ORI-048: emit uses written_tags writer graph (not phys-as-writer)",
        "owner_controller_state": {
            "model_machine": model.get("machine"),
            "never_stamp_blank_as_active": True,
            "unsupported_conserved": len(unsupported),
        },
        "zones": [
            {
                "name": z.get("name") or z.get("engineering_name"),
                "areaRef": z.get("areaRef") or z.get("area") or "",
                "members": len(z.get("members") or []),
                "status": z.get("status"),
            }
            for z in zones
        ],
        "Default_membership": default_n,
        "safety_evidence_complete": model.get("safety_evidence_complete"),
        "blocked_reasons": sorted(
            {
                str(d.get("review_reason") or d.get("reason") or "")
                for d in devices
                if d.get("review_reason") or d.get("reason")
            }
            - {""}
        ),
        "ready_names_sample": [d.get("name") for d in ready[:12]],
        "review_names_sample": [d.get("name") for d in review[:20]],
    }


def _orl_area_delete_probe() -> dict:
    wb = {
        "conveyors": [],
        "areas": [{"name": "Warden_Area", "engineerCreated": True}],
        "options": {"areas": ["Warden_Area"]},
        "safety_build": {
            "appliedAt": "2026-09-26T12:00:00Z",
            "zones": [
                {
                    "source_id": "szone_orl",
                    "name": "Warden_ESZ",
                    "areaRef": "Warden_Area",
                    "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "provenance": "ENGINEER_CREATED",
                }
            ],
        },
    }
    after_del = apply_graph_to_workbook(
        {
            "areas": [],
            "deletedAreas": ["Warden_Area"],
            "safetyBuild": {
                "zones": [
                    {
                        "source_id": "szone_orl",
                        "name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges": [],
        },
        wb,
    )["workbook"]
    z = ((after_del.get("safety_build") or {}).get("zones") or [None])[0] or {}
    # Recreate same Area — areaRef must stay cleared (no silent relink at workbook layer)
    after_re = apply_graph_to_workbook(
        {
            "areas": [{"name": "Warden_Area", "isDefault": False, "nodes": [], "wires": []}],
            "deletedAreas": [],
            "safetyBuild": {
                "zones": [
                    {
                        "source_id": "szone_orl",
                        "name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges": [],
        },
        after_del,
    )["workbook"]
    zones = (after_re.get("safety_build") or {}).get("zones") or []
    same_name = [x for x in zones if str(x.get("name") or "") == "Warden_ESZ"]
    return {
        "after_delete_areaRef": z.get("areaRef") or "",
        "after_delete_members": len(z.get("members") or []),
        "after_recreate_areaRef": (same_name[0].get("areaRef") if same_name else None) or "",
        "duplicate_zone_count": max(0, len(same_name) - 1),
        "zone_still_present": bool(same_name),
    }


def main() -> int:
    results = {"ORL_area_delete_probe": _orl_area_delete_probe()}
    for label, hint, machine in SITES:
        run = hint if (hint / "project.cfg").is_file() else _find_run(machine)
        entry: dict = {"machine": machine, "run_dir": str(run) if run else None}
        if not run:
            entry["error"] = "RUN_NOT_FOUND"
            results[label] = entry
            (OUT / f"{label}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
            continue
        try:
            model = build_safety_model(run_dir=run, machine=machine)
            summary = _summarize(model)
            # Re-apply endpoint integrity for explicit collision/readiness dump
            devices = list(model.get("safetyDevices") or [])
            coll = apply_endpoint_collision_review(devices)
            summary["collision_count"] = coll.get("conflicted_count") or 0
            summary["endpoint_collisions"] = coll.get("collisions") or []
            entry["summary"] = summary
            entry["ok"] = True
        except Exception as exc:
            entry["error"] = str(exc)
            entry["ok"] = False
        results[label] = entry
        (OUT / f"{label}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
        print(label, "OK" if entry.get("ok") else entry.get("error"))

    (OUT / "INDEX.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
