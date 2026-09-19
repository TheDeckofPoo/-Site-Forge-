#!/usr/bin/env python3
"""Final L5X artifact closure gate — post assembly orphan / contamination scan.

Runs AFTER program pack inclusion, remapping, sorter/Safety generation, and
task scheduling. Site-specific tags/programs must trace to MachineClosure,
DERIVED relationships, or engineer assignment.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]

# Pack-template divert hosts that must not survive unless RUN proves them
PACK_TEMPLATE_DIVERT_HOSTS = ("P504", "P506", "P508", "P509", "P510", "P500", "P502", "P512")
DEFAULT_OPERATIONAL_RE = re.compile(
    r"Default[_\s]?Area[_\s]?ESZone\d*|Default[_\s]?Safety|Unassigned[_\s]?Safety",
    re.I,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_l5x_site_objects(l5x_text: str) -> dict[str, Any]:
    programs = sorted(set(re.findall(r'Program Name="([^"]+)"', l5x_text or "")))
    divert_tags = sorted(set(re.findall(r'Name="(P\d+_Divert\d*(?:_AOI|_Wave|_Output|_Cmd)?)"', l5x_text or "")))
    merge_tags = sorted(set(re.findall(r'Name="(P\d+_Merge)"', l5x_text or "")))
    es_zones = sorted(set(re.findall(r'Name="([^"]*ESZone\d+)"', l5x_text or "")))
    pack_orphans = [
        t
        for t in divert_tags
        if any(t.upper().startswith(f"{h}_DIVERT") for h in PACK_TEMPLATE_DIVERT_HOSTS)
    ]
    default_ops = [z for z in es_zones if DEFAULT_OPERATIONAL_RE.search(z)]
    # Also catch CFG lines referencing pack hosts
    cfg_pack = sorted(
        set(
            re.findall(
                r"\b((?:P504|P506|P508|P509|P510)_Divert\d*)\.CFG\b",
                l5x_text or "",
            )
        )
    )
    for c in cfg_pack:
        if c not in pack_orphans:
            pack_orphans.append(c)
    return {
        "programs": programs,
        "divert_tags": divert_tags,
        "merge_tags": merge_tags,
        "es_zone_tags": es_zones,
        "pack_template_divert_orphans": sorted(pack_orphans),
        "default_operational_zone_refs": default_ops,
        "has_sorter_track": "Sorter_Track" in programs,
        "shipping_sorter_programs": [p for p in programs if "ShippingSorter" in p or p.endswith("_Area_L3")],
        "safe_logic_routines": len(re.findall(r'Routine Name="Safe_Logic"', l5x_text or "")),
        "safe_pi_routines": len(re.findall(r'Routine Name="Safe_PI"', l5x_text or "")),
    }


def validate_final_artifact(
    *,
    l5x_text: str,
    machine: str = "",
    allowed_divert_hosts: list[str] | None = None,
    require_no_pack_orphans: bool = True,
    require_no_default_operational: bool = True,
) -> dict[str, Any]:
    scan = scan_l5x_site_objects(l5x_text)
    errors: list[str] = []
    reviews: list[str] = []
    allowed = {h.upper() for h in (allowed_divert_hosts or []) if h}

    orphans = list(scan.get("pack_template_divert_orphans") or [])
    if allowed:
        orphans = [
            o
            for o in orphans
            if not any(o.upper().startswith(f"{h}_DIVERT") for h in allowed)
        ]
    if require_no_pack_orphans and orphans:
        errors.append(
            f"PACK_TEMPLATE_DIVERT_ORPHANS: {orphans[:12]}"
            + (f" (+{len(orphans) - 12} more)" if len(orphans) > 12 else "")
        )
    defaults = list(scan.get("default_operational_zone_refs") or [])
    if require_no_default_operational and defaults:
        errors.append(f"DEFAULT_SAFETY_OPERATIONAL_REF: {defaults}")

    if scan.get("safe_logic_routines", 0) == 0 and scan.get("safe_pi_routines", 0) == 0:
        reviews.append("ES_NO_SAFE_ROUTINES — fail-safe shell or no engineer zone membership")

    status = "FAIL" if errors else ("REVIEW" if reviews else "PASS")
    return {
        "ok": status == "PASS",
        "status": status,
        "generated_at": _ts(),
        "machine": machine,
        "errors": errors,
        "reviews": reviews,
        "orphan_count": len(orphans),
        "scan": scan,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Final L5X artifact closure gate")
    ap.add_argument("--l5x", type=Path, required=True)
    ap.add_argument("--machine", default="")
    ap.add_argument("--allowed-divert-host", action="append", default=[])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    text = args.l5x.read_text(encoding="utf-8", errors="replace")
    result = validate_final_artifact(
        l5x_text=text,
        machine=args.machine,
        allowed_divert_hosts=args.allowed_divert_host,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": result["errors"], "orphan_count": result["orphan_count"]}, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
