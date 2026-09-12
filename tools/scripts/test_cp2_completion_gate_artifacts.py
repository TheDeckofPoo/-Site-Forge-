#!/usr/bin/env python3
"""Smoke test: CP2 completion gate deliverable JSON files exist with required keys."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "exports" / "cp2-gate"

REQUIRED = {
    "io_inventory.json": {
        "generated_at",
        "machine",
        "counts",
        "lists",
        "io_compare_vs_finished",
        "verdict",
    },
    "equipment_inventory.json": {
        "generated_at",
        "machine",
        "counts",
        "run_conveyors_expected",
        "ownership_for_run_conveyors",
        "ownership_classification",
        "ownership_validation_observation",
        "verdict",
    },
    "ownership_classification.json": {
        "generated_at",
        "machine",
        "counts",
        "by_class",
        "classifications",
        "validation_observation",
        "policy",
    },
    "area_safety_inventory.json": {
        "generated_at",
        "areas_expected_from_workbook",
        "es_zones_expected_from_workbook",
        "conveyors_per_area",
        "compare_vs_finished",
        "verdict",
    },
    "estop_inventory.json": {
        "generated_at",
        "machine",
        "counts",
        "devices",
        "compare_vs_generated",
        "verdict",
    },
    "layout_metrics.json": {
        "generated_at",
        "machine",
        "counts",
        "visual_layout_acceptance",
        "verdict",
    },
    "library_provenance.json": {
        "generated_at",
        "required_libraries",
        "no_logic_copied_from_finished_cp2",
        "verdict",
    },
    "comparison_summary.json": {
        "generated_at",
        "machine",
        "policy",
        "category_scores",
        "layout_visualization_gate",
    },
}


def main() -> int:
    print("=== test_cp2_completion_gate_artifacts ===")
    if not GATE.is_dir():
        print(f"FAIL: missing gate dir {GATE}")
        return 1
    failures = 0
    for name, keys in REQUIRED.items():
        path = GATE / name
        if not path.is_file():
            print(f"FAIL: missing {path}")
            failures += 1
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL: {name} invalid JSON: {exc}")
            failures += 1
            continue
        missing = sorted(keys - set(data.keys()))
        if missing:
            print(f"FAIL: {name} missing keys {missing}")
            failures += 1
            continue
        # comparison_summary must not invent an overall score
        if name == "comparison_summary.json" and "overall_accuracy" in data:
            print("FAIL: comparison_summary.json must not contain overall_accuracy")
            failures += 1
            continue
        if name == "comparison_summary.json":
            cats = data.get("category_scores") or []
            if not isinstance(cats, list) or not cats:
                print("FAIL: comparison_summary.json category_scores empty")
                failures += 1
                continue
        print(f"PASS: {name}")
    doc = ROOT / "docs" / "CP2_COMPLETION_GATE.md"
    if not doc.is_file():
        print(f"FAIL: missing {doc}")
        failures += 1
    else:
        print(f"PASS: docs/CP2_COMPLETION_GATE.md")
    orch = ROOT / "tools" / "scripts" / "fortna_cp2_completion_gate.py"
    if not orch.is_file():
        print(f"FAIL: missing {orch}")
        failures += 1
    else:
        print(f"PASS: fortna_cp2_completion_gate.py")
    if failures:
        print(f"RESULT: FAIL ({failures})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
