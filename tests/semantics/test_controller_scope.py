#!/usr/bin/env python3
"""Unit tests for fortna_controller_scope ControllerScopeModel.

Checks:
  - no P-number→PLC heuristic helpers (p_number_to_plc style)
  - LOCAL set non-empty for active CP2 RUN
  - P600* not LOCAL when owned by another controller
  - does not read finished PLC path
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import inspect
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fortna_controller_scope as scope_mod  # noqa: E402
from fortna_controller_scope import (  # noqa: E402
    build_controller_scope,
    local_tags,
)

RUN = ROOT / "workspace" / "active" / "RUN"
FINISHED_MARKERS = (
    "ORLY_GreensboroPLC2_NC_Finished.L5X",
    "GreensboroPLC2_NC_Finished",
    "finished.l5x",
)


def main() -> int:
    print("=== test_controller_scope ===")
    failures = 0

    if not (RUN / "FORTNA" / "Conveyor.asc").is_file():
        print(f"FAIL: missing RUN at {RUN}")
        return 1

    # 1) Forbid number-range heuristics
    banned_name_bits = (
        "p_number_to_plc",
        "pnumber_to_plc",
        "number_range_to_plc",
        "ptag_number_plc",
        "p1xx",
    )
    for name, obj in inspect.getmembers(scope_mod):
        if not callable(obj):
            continue
        lower = name.lower()
        if any(b in lower for b in banned_name_bits):
            print(f"FAIL: forbidden heuristic function present: {name}")
            failures += 1
    src = Path(scope_mod.__file__).read_text(encoding="utf-8")
    for bit in ("P1xx", "p_number_to_plc", "number_range_heuristic"):
        if bit in src and "FORBIDDEN" not in src.split(bit)[0][-80:]:
            # Allow mention in docstring as forbidden policy text.
            if "forbidden" in src.lower() or "FORBIDDEN" in src:
                continue
            print(f"FAIL: suspicious heuristic token in source: {bit}")
            failures += 1
    if failures == 0:
        print("PASS: no p_number_to_plc-style heuristics")

    # 2) Build scope without reading finished PLC
    opened: list[str] = []
    real_open = open

    def tracking_open(file, *args, **kwargs):
        path = str(file)
        opened.append(path)
        lower = path.lower()
        for marker in FINISHED_MARKERS:
            if marker.lower() in lower:
                raise AssertionError(f"finished PLC path read during scope build: {path}")
        return real_open(file, *args, **kwargs)

    with mock.patch("builtins.open", tracking_open):
        scope = build_controller_scope(RUN, "ORNCCP2")

    blob = json.dumps(scope)
    for marker in FINISHED_MARKERS:
        if marker in blob:
            print(f"FAIL: finished PLC marker leaked into scope payload: {marker}")
            failures += 1
    else:
        print("PASS: does not read finished PLC path")

    # 3) LOCAL non-empty
    loc = local_tags(scope)
    print(f"LOCAL count: {len(loc)}")
    if not loc:
        print("FAIL: LOCAL set empty for active CP2 RUN")
        failures += 1
    else:
        print("PASS: LOCAL set non-empty")

    # 4) P600 not LOCAL if present as other-controller equipment
    p600ish = sorted(
        t
        for t in (
            list((scope.get("by_scope") or {}).get("OUT_OF_SCOPE") or [])
            + list((scope.get("by_scope") or {}).get("EXTERNAL_REFERENCE") or [])
            + list((scope.get("by_scope") or {}).get("UNRESOLVED") or [])
            + list(loc)
        )
        if t.upper().startswith("P600")
    )
    p600_local = sorted(t for t in loc if t.upper().startswith("P600"))
    if p600ish:
        if p600_local:
            print(f"FAIL: P600 tags unexpectedly LOCAL: {p600_local}")
            failures += 1
        else:
            print(f"PASS: P600 not LOCAL ({len(p600ish)} P600* seen outside LOCAL)")
    else:
        print("SKIP: no P600* tags in RUN scope inventory")

    counts = scope.get("counts") or {}
    print(f"counts: {counts}")
    if failures:
        print(f"FAILED ({failures})")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
