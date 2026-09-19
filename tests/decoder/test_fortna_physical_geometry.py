#!/usr/bin/env python3
"""Unit tests for greensboro-infeed-v1 physical geometry."""
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


import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fortna_physical_geometry import (  # noqa: E402
    CALIBRATION,
    build_equipment_geometry,
    classify_mate,
    linear_body,
)


def approx(a, b, eps=1e-6):
    return abs(a - b) <= eps


def main() -> int:
    fails = []
    if CALIBRATION.get("xy_meaning") != "infeed_entry_end":
        fails.append("calibration xy_meaning")

    g = linear_body(0, 0, 1000, 90, 200)
    if not approx(g["entry"]["x"], 0) or not approx(g["entry"]["y"], 0):
        fails.append("linear entry")
    if not approx(g["exit"]["x"], 0, 1e-6) or not approx(g["exit"]["y"], 1000):
        fails.append("linear exit")
    if classify_mate(g["exit"], {"x": 0, "y": 1000}, 200) != "CONFIRMED":
        fails.append("mate confirmed")

    # Greensboro-style abutment: P312→P314 pattern
    a = build_equipment_geometry(
        {"X_cord": 64950, "Y_cord": 85700, "Angle": 90, "Length": 3000, "Width": 200, "Type": "ZEROPRESSURE"}
    )
    b = build_equipment_geometry(
        {"X_cord": 64950, "Y_cord": 88700, "Angle": 90, "Length": 2500, "Width": 200, "Type": "BELT"}
    )
    d = math.hypot(a["exit"]["x"] - b["entry"]["x"], a["exit"]["y"] - b["entry"]["y"])
    if d > 1e-6:
        fails.append(f"P312-style abutment d={d}")

    curve = build_equipment_geometry(
        {
            "X_cord": 0,
            "Y_cord": 0,
            "Angle": 90,
            "Length": -1,
            "Width": 200,
            "Type": "CURVE",
            "Inside_Radius": 266.667,
            "Infeed_Tangent": 50,
            "Discharge_Tangent": 50,
        },
        mate_entries=[(416.667, 416.667)],
    )
    if curve.get("kind") != "curve":
        fails.append("curve kind")
    if not curve.get("exit"):
        fails.append("curve exit")
    if abs(float(curve.get("sweep_deg") or 0)) != 90.0:
        fails.append("curve sweep 90")

    # Must not treat XY as center (±L/2)
    bad_center_exit_y = 500.0  # would be center model for L=1000 @90 from (0,0) if XY were center
    if approx(g["exit"]["y"], bad_center_exit_y):
        fails.append("still using center model")

    for f in fails:
        print(f"  [FAIL] {f}")
    if fails:
        print(f"FAIL — {len(fails)}")
        return 1
    print("PASS — physical geometry infeed-v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
