#!/usr/bin/env python3
"""Validate a SiteModel JSON for common RUN-derived integrity issues.

Checks (non-exhaustive):
  - PE missing I/O assignment
  - Motor inactive but INCLUDED
  - VFD multi-drive ambiguity
  - Sawtooth lane unknown conveyor
  - Finished-PLC path leakage in model text
  - Greensboro hardcoding leakage unless present in run_dir string facts

Usage:
  python fortna_validate_site_model.py --site-model exports/run-discovery/site_model.json
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

from fortna_site_model import (  # noqa: E402
    EXCLUDED,
    INACTIVE_CONFIRMED,
    INCLUDED,
    HISTORICAL_OR_STALE,
    _clean,
    normalize_name,
    write_json,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


FORBIDDEN_PLC_FRAGMENTS = [
    "read_l5x" + "(",
    "ORLY_" + "Greensboro_NC_PLC4",
    "PLC4Finished" + ".L5X",
    "finished_plc4",
    "plc4_finished",
]


def validate_site_model(site: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def add(kind: str, severity: str, message: str, **extra: Any) -> None:
        issues.append({"kind": kind, "severity": severity, "message": message, **extra})

    # --- PE missing I/O ---
    for pe in site.get("photoeyes") or []:
        if pe.get("inclusion") != INCLUDED:
            continue
        io_word = _clean(pe.get("io_address_word") or pe.get("IO_Address_Word") or "")
        has_io_ev = any(
            (e.get("kind") in {"controller_io", "io_assignment", "configio_link"})
            for e in (pe.get("evidence") or [])
        )
        if not io_word and not has_io_ev:
            add(
                "pe_missing_io",
                "warning",
                f"INCLUDED photoeye lacks I/O assignment: {pe.get('normalized_name')}",
                canonical_id=pe.get("canonical_id"),
            )

    # --- Motor inactive but INCLUDED ---
    for motor in site.get("motors") or []:
        if motor.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
            if motor.get("inclusion") == INCLUDED:
                add(
                    "motor_inactive_included",
                    "error",
                    f"Inactive motor marked INCLUDED: {motor.get('normalized_name')}",
                    canonical_id=motor.get("canonical_id"),
                )

    # Hard rule across buckets
    for bucket in ("equipment", "motors", "vfds", "photoeyes", "sorters", "sawtooth_merges"):
        for obj in site.get(bucket) or []:
            if obj.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                if obj.get("inclusion") == INCLUDED:
                    add(
                        "inactive_included",
                        "error",
                        f"{bucket} inactive object INCLUDED: {obj.get('normalized_name')}",
                        canonical_id=obj.get("canonical_id"),
                    )

    # --- VFD multi-drive ---
    # If multiple VFDs claim the same conveyor, flag ambiguity.
    conv_to_vfds: dict[str, list[str]] = defaultdict(list)
    for vfd in site.get("vfds") or []:
        name = vfd.get("normalized_name") or vfd.get("raw_name") or ""
        for conv in vfd.get("conveyors") or []:
            conv_to_vfds[normalize_name(str(conv))].append(str(name))
        linked = vfd.get("linked_conveyor")
        if linked:
            conv_to_vfds[normalize_name(str(linked))].append(str(name))
    for conv, vfds in sorted(conv_to_vfds.items()):
        uniq = sorted({normalize_name(v) for v in vfds if v})
        if conv and len(uniq) > 1:
            add(
                "vfd_multi_drive",
                "warning",
                f"Conveyor {conv} linked to multiple VFDs: {uniq}",
                conveyor=conv,
                vfds=uniq,
            )

    # --- Lane unknown conveyor ---
    for merge in site.get("sawtooth_merges") or []:
        for lane in merge.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            lname = lane.get("name") or ""
            conv = _clean(lane.get("conveyor"))
            if not conv:
                add(
                    "lane_unknown_conveyor",
                    "warning",
                    f"Sawtooth lane missing conveyor: {lname}",
                    merge=merge.get("normalized_name"),
                    lane=lname,
                )

    # --- Finished PLC / Greensboro leakage in serialized model ---
    blob = json.dumps(site, ensure_ascii=False)
    for frag in FORBIDDEN_PLC_FRAGMENTS:
        if frag.lower() in blob.lower():
            add(
                "finished_plc_leakage",
                "error",
                f"Forbidden finished-PLC fragment in site model: {frag}",
            )

    run_dir = str(site.get("run_dir") or "")
    # Greensboro names in model identities are only OK if the RUN path itself is Greensboro.
    run_is_gso = bool(re.search(r"Greensboro|ORNCCP", run_dir, re.I))
    if not run_is_gso:
        for bucket in ("equipment", "controllers", "sorters", "areas"):
            for obj in site.get(bucket) or []:
                name = str(obj.get("normalized_name") or obj.get("raw_name") or "")
                if re.search(r"Greensboro", name, re.I):
                    add(
                        "greensboro_hardcoding",
                        "error",
                        f"Greensboro name in model without Greensboro RUN: {name}",
                        canonical_id=obj.get("canonical_id"),
                    )

    counts = Counter(i["severity"] for i in issues)
    return {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "run_dir": site.get("run_dir"),
        "ok": counts.get("error", 0) == 0,
        "issue_counts": dict(counts),
        "issues": issues,
        "checks_run": [
            "pe_missing_io",
            "motor_inactive_included",
            "inactive_included",
            "vfd_multi_drive",
            "lane_unknown_conveyor",
            "finished_plc_leakage",
            "greensboro_hardcoding",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate SiteModel JSON")
    ap.add_argument("--site-model", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    site = json.loads(args.site_model.read_text(encoding="utf-8"))
    report = validate_site_model(site)
    if args.out:
        write_json(args.out, report)
    print(json.dumps({"ok": report["ok"], "issue_counts": report["issue_counts"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
