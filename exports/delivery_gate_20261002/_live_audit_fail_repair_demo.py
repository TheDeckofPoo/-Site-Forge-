#!/usr/bin/env python3
"""Live AI/Relay on deliberate AUDIT_FAIL — does NOT promote."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_l5x_acceptance_auditor import (  # noqa: E402
    build_expected_artifact_manifest,
    run_acceptance_and_repair,
)


class Fake:
    machine = "MSCRENOPICK"
    project_name = "MSCRENOPICK"
    areas = ["MSCRENOPICK_Area"]
    include_io_map = True
    conveyors = [1] * 47
    safety_zone_members = [
        {
            "name": "MSCRENOPICK_ESZone1",
            "status": "READY",
            "operational": True,
            "membersOrigin": "ENGINEER_ASSIGNED",
            "members": ["ESPB2", "ESPB24", "ESPB32", "ESLS2"],
            "area": "MSCRENOPICK_Area",
        }
    ]


def main() -> int:
    good = sorted(
        (REPO / "exports" / "current").glob("MSCRENOPICK_*.L5X"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[0]
    raw = good.read_text(encoding="utf-8", errors="replace")
    dam = re.sub(
        r'<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"[^>]*>.*?</Routine>',
        "",
        raw,
        count=1,
        flags=re.S,
    )
    out = REPO / "exports" / "delivery_gate_20261002" / "_live_audit_fail_repair"
    out.mkdir(exist_ok=True)
    p = out / "damaged.L5X"
    p.write_text(dam, encoding="utf-8")
    man = build_expected_artifact_manifest(Fake(), report={"conveyor_count": 47})
    r = run_acceptance_and_repair(
        l5x_path=p,
        manifest=man,
        out_dir=out,
        regenerate_fn=None,
        live=True,
        max_outer_cycles=1,
    )
    summary = {
        "status": r.get("status"),
        "ok": r.get("ok"),
        "promoted": r.get("promoted"),
        "ai_api_calls": r.get("ai_api_calls"),
        "relay_calls": r.get("relay_calls"),
        "estimated_cost_usd": r.get("estimated_cost_usd"),
        "initial_sigs": (r.get("initial_audit") or {}).get("signatures"),
        "generator_defect": r.get("generator_defect"),
    }
    (out / "live_repair_result.json").write_text(
        json.dumps(r, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    # Success criteria: AUDIT_FAIL (not promoted) + at least one AI or Relay call
    if r.get("promoted"):
        return 2
    if int(r.get("ai_api_calls") or 0) + int(r.get("relay_calls") or 0) < 1:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
