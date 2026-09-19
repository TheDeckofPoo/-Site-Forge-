#!/usr/bin/env python3
"""Smoke test: CP2 demo-closure deliverable JSON files exist with required keys."""
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


import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "exports" / "cp2-demo-closure"

REQUIRED = {
    "run_realization.json": {
        "generated_at",
        "machine",
        "counts",
        "items",
    },
    "pe_realization.json": {
        "generated_at",
        "machine",
        "counts",
        "instances",
        "validation_observation_only",
    },
    "area_es_status.json": {
        "generated_at",
        "machine",
        "run_area_es_recoverability",
        "counts",
        "area_required",
        "es_zone_required",
    },
    "overlap_classification.json": {
        "generated_at",
        "machine",
        "classes",
        "counts_by_class",
        "overlap_pairs",
    },
    "remaining_work.json": {
        "generated_at",
        "summary",
        "engineering_terms",
    },
}

RUN_COUNT_KEYS = {
    "run_equipment_discovered",
    "site_forge_supported",
    "automatically_realized",
    "engineer_confirmation_required",
    "unsupported",
    "ignored",
}

REMAINING_KEYS = {
    "conveyors_need_topology",
    "conveyors_need_area",
    "conveyors_need_es_zone",
    "pe_roles_need_confirmation",
    "unsupported_equipment_items",
}

OVERLAP_CLASSES = {
    "SAME_PHYSICAL_EQUIPMENT",
    "PARALLEL_EQUIPMENT",
    "PARENT_CHILD",
    "VALID_OVERLAP",
    "SUSPECT_GEOMETRY",
    "UNKNOWN",
}


def main() -> int:
    print("=== test_cp2_demo_closure_artifacts ===")
    if not OUT.is_dir():
        print(f"FAIL: missing out dir {OUT}")
        return 1
    failures = 0

    for name, keys in REQUIRED.items():
        path = OUT / name
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
        print(f"PASS: {name}")

        if name == "run_realization.json":
            ck = set((data.get("counts") or {}).keys())
            miss = sorted(RUN_COUNT_KEYS - ck)
            if miss:
                print(f"FAIL: run_realization counts missing {miss}")
                failures += 1
            statuses = {it.get("status") for it in (data.get("items") or [])}
            allowed = {
                "automatically_realized",
                "engineer_confirmation_required",
                "unsupported",
                "ignored",
            }
            bad = sorted(statuses - allowed - {None})
            if bad:
                print(f"FAIL: unexpected realization statuses {bad}")
                failures += 1

        if name == "pe_realization.json":
            vo = data.get("validation_observation_only") or {}
            if "finished_plc_Full_PE" not in vo or "finished_plc_PE_Logic" not in vo:
                print("FAIL: pe_realization missing finished PLC observation keys")
                failures += 1
            provs = {i.get("provenance") for i in (data.get("instances") or [])}
            allowed_p = {
                "RUN_EXPLICIT",
                "RUN_DERIVED",
                "ENGINEER_CONFIGURED",
                "DEFAULT",
                "UNKNOWN",
                None,
            }
            bad_p = sorted(provs - allowed_p)
            if bad_p:
                print(f"FAIL: unexpected PE provenance values {bad_p}")
                failures += 1

        if name == "overlap_classification.json":
            classes = set(data.get("classes") or [])
            if not OVERLAP_CLASSES <= classes:
                print(f"FAIL: overlap classes missing {sorted(OVERLAP_CLASSES - classes)}")
                failures += 1

        if name == "remaining_work.json":
            miss = sorted(REMAINING_KEYS - set((data.get("summary") or {}).keys()))
            if miss:
                print(f"FAIL: remaining_work summary missing {miss}")
                failures += 1
            terms = data.get("engineering_terms") or []
            if len(terms) < 5:
                print("FAIL: remaining_work engineering_terms expected 5 lines")
                failures += 1

    demo_md = OUT / "demo_gate.md"
    if not demo_md.is_file():
        print(f"FAIL: missing {demo_md}")
        failures += 1
    else:
        print("PASS: demo_gate.md")

    doc = ROOT / "docs" / "CP2_DEMO_CLOSURE.md"
    if not doc.is_file():
        print(f"FAIL: missing {doc}")
        failures += 1
    else:
        print("PASS: docs/CP2_DEMO_CLOSURE.md")

    orch = ROOT / "tools" / "scripts" / "fortna_cp2_demo_closure.py"
    if not orch.is_file():
        print(f"FAIL: missing {orch}")
        failures += 1
    else:
        print("PASS: fortna_cp2_demo_closure.py")

    if failures:
        print(f"RESULT: FAIL ({failures})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
