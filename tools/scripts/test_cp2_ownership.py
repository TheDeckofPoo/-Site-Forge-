#!/usr/bin/env python3
"""Smoke test: RUN-only CP2 ownership classifier.

Checks:
  - classifier runs against active RUN
  - required evidence keys present
  - CP2_CONFIRMED count > old Autogen PE/VFD-only 37
  - CONFIRMED is not forced equal to finished PLC 57
  - classification does not read finished PLC paths
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_cp2_ownership import (  # noqa: E402
    FINISHED_PLC_CONVEYOR_COUNT,
    OLD_AUTOGEN_SCOPED_COUNT,
    classify_ownership,
)

RUN = ROOT / "workspace" / "active" / "RUN"
FINISHED_MARKERS = (
    "ORLY_GreensboroPLC2_NC_Finished.L5X",
    "GreensboroPLC2_NC_Finished",
    "finished.l5x",
)

REQUIRED_EVIDENCE = {
    "machine_name_field",
    "pe_links",
    "motor_links",
    "vfd_links",
    "mtrchain_motors",
    "other_controller_conflicts",
    "match_mode",
    "reasons",
}


def main() -> int:
    print("=== test_cp2_ownership ===")
    failures = 0

    if not (RUN / "FORTNA" / "Conveyor.asc").is_file():
        print(f"FAIL: missing RUN at {RUN}")
        return 1

    opened: list[str] = []
    real_open = open

    def tracking_open(file, *args, **kwargs):
        path = str(file)
        opened.append(path)
        lower = path.lower()
        for marker in FINISHED_MARKERS:
            if marker.lower() in lower:
                raise AssertionError(f"finished PLC path read during classification: {path}")
        return real_open(file, *args, **kwargs)

    with mock.patch("builtins.open", tracking_open):
        payload = classify_ownership(RUN, "ORNCCP2")

    # Also guard Path.read_text callers that bypass builtins.open on some platforms
    blob = json.dumps(payload)
    for marker in FINISHED_MARKERS:
        if marker in blob:
            print(f"FAIL: finished PLC marker leaked into payload: {marker}")
            failures += 1

    counts = payload.get("counts") or {}
    confirmed = int(counts.get("CP2_CONFIRMED") or 0)
    print(f"counts: {counts}")
    print(f"CONFIRMED={confirmed} old37={OLD_AUTOGEN_SCOPED_COUNT} finished57={FINISHED_PLC_CONVEYOR_COUNT}")

    required_top = {
        "generated_at",
        "machine",
        "counts",
        "by_class",
        "classifications",
        "validation_observation",
        "policy",
    }
    missing_top = sorted(required_top - set(payload.keys()))
    if missing_top:
        print(f"FAIL: missing top-level keys {missing_top}")
        failures += 1
    else:
        print("PASS: top-level keys")

    policy = payload.get("policy") or {}
    if policy.get("finished_plc_not_used_for_classification") is not True:
        print("FAIL: policy.finished_plc_not_used_for_classification is not True")
        failures += 1
    if policy.get("match_mode") != "EXACT":
        print("FAIL: policy.match_mode is not EXACT")
        failures += 1
    if policy.get("include_motors") is not True:
        print("FAIL: policy.include_motors is not True")
        failures += 1

    rows = payload.get("classifications") or []
    if not rows:
        print("FAIL: classifications empty")
        failures += 1
    else:
        bad = 0
        for row in rows[:50]:
            ev = row.get("evidence") or {}
            miss = sorted(REQUIRED_EVIDENCE - set(ev.keys()))
            if miss:
                print(f"FAIL: {row.get('conveyor_tag')} missing evidence keys {miss}")
                bad += 1
                break
            if ev.get("match_mode") != "EXACT" or row.get("match_mode") != "EXACT":
                print(f"FAIL: {row.get('conveyor_tag')} match_mode not EXACT")
                bad += 1
                break
        if bad == 0:
            print(f"PASS: evidence keys on {min(50, len(rows))} sampled rows")

    if confirmed <= OLD_AUTOGEN_SCOPED_COUNT:
        print(f"FAIL: CONFIRMED {confirmed} should be > old Autogen-scoped {OLD_AUTOGEN_SCOPED_COUNT}")
        failures += 1
    else:
        print(f"PASS: CONFIRMED {confirmed} > {OLD_AUTOGEN_SCOPED_COUNT}")

    if confirmed == FINISHED_PLC_CONVEYOR_COUNT:
        # Soft check: equality is allowed only if RUN truly yields 57 — but must not be forced.
        # Fail if a hard-coded target is present in the module source.
        src = (SCRIPTS / "fortna_cp2_ownership.py").read_text(encoding="utf-8")
        if "target" in src.lower() and "57" in src and "force" in src.lower():
            print("FAIL: appears to force target 57")
            failures += 1
        else:
            print(
                "NOTE: CONFIRMED equals finished 57 by RUN coincidence — "
                "not treated as a forced target"
            )
    else:
        print(f"PASS: CONFIRMED {confirmed} != finished {FINISHED_PLC_CONVEYOR_COUNT} (not forced)")

    # Ensure lettered finished-style conveyors were not invented as mechanical rows
    invented = [
        t
        for t in (payload.get("by_class") or {}).get("CP2_CONFIRMED") or []
        if t in {"P130A", "P130B", "P130C", "P130D", "P130E", "P145A", "P145B", "P145C", "P145D", "P145E"}
    ]
    if invented:
        print(f"FAIL: invented lettered conveyors from motors/finished: {invented}")
        failures += 1
    else:
        print("PASS: no invented lettered P130A/P145A conveyors")

    finished_reads = [p for p in opened if any(m.lower() in p.lower() for m in FINISHED_MARKERS)]
    if finished_reads:
        print(f"FAIL: finished PLC paths opened: {finished_reads}")
        failures += 1
    else:
        print("PASS: no finished PLC path read for classification")

    if failures:
        print(f"RESULT: FAIL ({failures})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
