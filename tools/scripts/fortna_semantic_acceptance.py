#!/usr/bin/env python3
"""CP4 semantic acceptance runner — reports each adapter independently."""
from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from typing import Any

from fortna_semantics.bundle import run_cp4_bundle
from fortna_semantics.evidence import write_json

ROOT = Path(__file__).resolve().parents[2]


def compare_cp4_sites(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    findings = []
    sites = [b["site"] for b in bundles]
    for adapter in ("Transportation", "Mtrchain", "Merge", "Jam", "Safety", "IO"):
        statuses = {b["site"]: (b.get("adapters") or {}).get(adapter, {}).get("status") for b in bundles}
        counts = {
            b["site"]: (b.get("adapterResults") or {}).get(adapter, {}).get("counts")
            for b in bundles
        }
        if len(set(statuses.values())) == 1:
            cls = "GENERIC_SEMANTIC_CONFIRMED"
        elif "FAIL" in statuses.values():
            cls = "POSSIBLE_SEMANTIC_DEFECT"
        elif "REVIEW" in statuses.values():
            cls = "REVIEW_REQUIRED"
        else:
            cls = "SITE_DATA_DIFFERENCE"
        findings.append(
            {
                "adapter": adapter,
                "classification": cls,
                "statuses": statuses,
                "counts": counts,
            }
        )
    return {
        "kind": "Cp4SemanticCrossSiteReport",
        "version": 1,
        "sites": sites,
        "bundleStatuses": {b["site"]: b.get("status") for b in bundles},
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 semantic acceptance")
    ap.add_argument("--out-dir", default=str(ROOT / "artifacts"))
    ap.add_argument("--skip-unit-tests", action="store_true")
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)

    unit = {"pass": True, "detail": "skipped"}
    if not args.skip_unit_tests:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for mod in (
            "test_fortna_mnu_schema",
            "test_fortna_mnu_runtime",
            "test_fortna_run_loader",
            "test_fortna_reference_resolver",
            "test_cp4_transportation",
            "test_cp4_mtrchain",
            "test_cp4_merge",
            "test_cp4_jam",
            "test_cp4_safety",
            "test_cp4_io",
            "test_cp4_bundle",
        ):
            try:
                suite.addTests(loader.loadTestsFromName(mod))
            except Exception as e:
                unit = {"pass": False, "detail": str(e)}
                break
        if unit.get("pass", True):
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            unit = {
                "pass": result.wasSuccessful(),
                "testsRun": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
            }

    sites = [
        ("plc2", ROOT / "artifacts/fortna-reference-graph-plc2.json", "ORNCCP2"),
        ("plc4", ROOT / "artifacts/fortna-reference-graph-plc4.json", "ORNCCP4"),
        ("plc5", ROOT / "artifacts/fortna-reference-graph-plc5.json", "ORNCCP5"),
    ]
    bundles = []
    overall = True
    print("\n=== CP4 ADAPTER STATUS ===")
    for site, graph, ac in sites:
        if not graph.is_file():
            print(f"{site}: FAIL — missing CP3 graph {graph}")
            overall = False
            continue
        b = run_cp4_bundle(site=site, graph_path=graph, ac_name=ac, out_dir=out_dir)
        bundles.append(b)
        print(f"\n{site} bundle={b['status']}")
        for name, st in b["adapters"].items():
            print(f"  {name:15} {st['status']:6}  {st.get('counts')}")
        # PLC2 hard expectations
        if site == "plc2":
            m = b["adapterResults"]["Mtrchain"]["proofs"]["M314"]
            mg = b["adapterResults"]["Merge"]["proofs"]["MERGE_316_SPUR"]
            if m.get("status") != "PROVEN" or mg.get("status") != "PROVEN":
                print("  PLC2 proof soft-fail", m.get("status"), mg.get("status"))
                overall = False
        if b["status"] == "FAIL":
            overall = False

    cross = compare_cp4_sites(bundles)
    cross["unitTests"] = unit
    write_json(out_dir / "cp4-semantic-cross-site-report.json", cross)
    overall = overall and bool(unit.get("pass"))
    print("\nCross-site ->", out_dir / "cp4-semantic-cross-site-report.json")
    print("OVERALL PASS" if overall else "OVERALL FAIL")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
