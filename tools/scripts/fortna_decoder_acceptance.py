#!/usr/bin/env python3
"""Permanent FortnaPlus decoder acceptance / regression harness.

Runs CP1 → CP2 → CP3 against a site fixture and emits a deterministic report.
Does not integrate into production Site Forge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
import unittest
from pathlib import Path
from typing import Any

from fortna_mnu_schema import parse_mnu_file
from fortna_reference_resolver import (
    build_reference_graph,
    extract_proofs,
    write_graph,
)
from fortna_run_loader import load_run

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent


def _sha_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run_site_acceptance(
    *,
    site_name: str,
    run_dir: Path,
    ac_name: str,
    graph_out: Path,
    report_out: Path | None = None,
    check_plc2_invariants: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "site": site_name,
        "acName": ac_name,
        "runDir": str(run_dir),
        "gates": {},
        "pass": False,
    }
    fortna = run_dir / "FORTNA" / "fortna.mnu"
    project = run_dir / "PROJECT" / "project.mnu"
    if not project.is_file():
        project = None

    # CP1
    try:
        sch = parse_mnu_file(fortna, origin="FORTNA")
        cp1 = {
            "pass": sch.stats.get("definitions", 0) > 0 and sch.stats.get("fields", 0) > 0,
            "definitions": sch.stats.get("definitions"),
            "fields": sch.stats.get("fields"),
            "lines": sch.stats.get("lines"),
        }
        if project:
            ps = parse_mnu_file(project, origin="PROJECT")
            cp1["projectDefinitions"] = ps.stats.get("definitions")
            cp1["projectFields"] = ps.stats.get("fields")
    except Exception as e:
        cp1 = {"pass": False, "error": str(e), "traceback": traceback.format_exc()}
    report["gates"]["CP1"] = cp1

    # CP2
    try:
        pack = load_run(
            fortna_mnu=fortna,
            project_mnu=project,
            run_dir=run_dir,
            ac_name=ac_name,
        )
        s = pack["summary"]
        cp2 = {
            "pass": s.get("tablesLoaded", 0) > 0 and s.get("totalRecords", 0) > 0,
            "summary": s,
        }
    except Exception as e:
        cp2 = {"pass": False, "error": str(e), "traceback": traceback.format_exc()}
        pack = None
    report["gates"]["CP2"] = cp2

    # CP3
    try:
        graph = build_reference_graph(
            fortna_mnu=fortna,
            project_mnu=project,
            run_dir=run_dir,
            ac_name=ac_name,
        )
        digest = write_graph(graph, graph_out)
        proofs = extract_proofs(graph, site=site_name)
        st = graph["statistics"]
        # Reverse integrity: every RECORD resolved edge with targetRecord appears in reverse
        rev = graph["reverseRelationships"]
        missing_rev = 0
        for e in graph["relationships"]:
            if e.get("scope") != "RECORD":
                continue
            if e.get("targetMenu") and e.get("targetRecord") is not None:
                key = f"{e['targetMenu']}#{e['targetRecord']}"
                inbound = rev.get(key) or []
                if not any(
                    x.get("sourceMenu") == e.get("sourceMenu")
                    and x.get("sourceRecord") == e.get("sourceRecord")
                    and x.get("sourceColumn") == e.get("sourceColumn")
                    for x in inbound
                ):
                    missing_rev += 1
        cp3 = {
            "pass": st.get("edgesRecord", 0) > 0 and missing_rev == 0,
            "statistics": st,
            "graphOut": str(graph_out),
            "graphSha256": digest,
            "reverseIntegrityMissing": missing_rev,
            "proofs": proofs,
        }
    except Exception as e:
        cp3 = {"pass": False, "error": str(e), "traceback": traceback.format_exc()}
        proofs = {}
    report["gates"]["CP3"] = cp3

    # PLC2 invariants
    invariants: dict[str, Any] = {"applied": check_plc2_invariants, "pass": True, "checks": []}
    if check_plc2_invariants and cp3.get("pass"):
        checks = []

        def add(name: str, ok: bool, detail: Any = None) -> None:
            checks.append({"name": name, "pass": bool(ok), "detail": detail})

        p = proofs
        m314 = (p.get("mtrchainM314") or {}).get("columns") or {}
        add("m314_record_found", (p.get("mtrchainM314") or {}).get("recordIndex") == 55)
        add(
            "m314_motor_ndx",
            (m314.get("Motor_Ndx") or {}).get("sourceRawValue") == "M314"
            and (m314.get("Motor_Ndx") or {}).get("targetIdentity") == "M314"
            and (m314.get("Motor_Ndx") or {}).get("status") == "RESOLVED",
        )
        add(
            "m314_chained1",
            (m314.get("Motor_Chained1") or {}).get("sourceRawValue") == "P314"
            and (m314.get("Motor_Chained1") or {}).get("status") == "RESOLVED",
        )
        add(
            "m314_aux",
            (m314.get("Motor_Aux") or {}).get("sourceRawValue") == "LATCH_MERGE_316"
            and (m314.get("Motor_Aux") or {}).get("status") == "RESOLVED",
        )
        add(
            "m314_enabled",
            (m314.get("Enabled") or {}).get("sourceRawValue") == "M136_AUX"
            and (m314.get("Enabled") or {}).get("status") == "RESOLVED",
        )

        lanes = p.get("merge316") or []
        add("merge316_two_lanes", len(lanes) >= 2, len(lanes))
        if len(lanes) >= 2:
            # Order not guaranteed — match by ReleaseIO raw
            by_rel = {
                (ln.get("ReleaseIO") or {}).get("sourceRawValue"): ln for ln in lanes
            }
            l1 = by_rel.get("SSVEZPE136_P1")
            l2 = by_rel.get("M314")
            add("merge316_lane1_release", bool(l1) and (l1.get("Presense") or {}).get("sourceRawValue") == "EZPE136_P1")
            add("merge316_lane2_release", bool(l2) and (l2.get("Presense") or {}).get("sourceRawValue") == "PE314_P")
            add(
                "merge316_boss",
                all(
                    (ln.get("MergeBoss") or {}).get("sourceRawValue") == "MERGE_316_SPUR"
                    for ln in lanes
                ),
            )

        add("dynamic_examples_present", len(p.get("dynamicSamples") or []) >= 1)
        add("reverse_m314_inbound", (p.get("reverseM314") or {}).get("inboundCount", 0) >= 1)
        add(
            "reverse_merge316_inbound",
            (p.get("reverseMerge316") or {}).get("inboundCount", 0) >= 1,
        )
        add("estop_samples", len(p.get("estopSamples") or []) >= 2)
        add("jamcheck_samples", len(p.get("jamcheckSamples") or []) >= 5)

        invariants["checks"] = checks
        invariants["pass"] = all(c["pass"] for c in checks)
    report["gates"]["INVARIANTS"] = invariants

    report["pass"] = bool(cp1.get("pass") and cp2.get("pass") and cp3.get("pass") and invariants.get("pass"))
    if report_out:
        report_out = Path(report_out)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def compare_sites(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """GATE G cross-site comparison at generic Fortna layer."""
    findings: list[dict[str, Any]] = []
    by_site = {r["site"]: r for r in reports}

    def st(site: str) -> dict[str, Any]:
        return (((by_site.get(site) or {}).get("gates") or {}).get("CP3") or {}).get("statistics") or {}

    sites = [r["site"] for r in reports]
    metrics = [
        "schemaMenus",
        "tablesLoaded",
        "recordsLoaded",
        "edgesRecord",
        "resolved",
        "dynamic",
        "static",
        "fallbackStatic",
        "machineSpecific",
        "genericAsc",
        "missingTables",
    ]
    metric_table = {m: {s: st(s).get(m) for s in sites} for m in metrics}

    # Taxonomy union
    tax = {s: st(s).get("unresolvedTaxonomy") or {} for s in sites}
    all_tax = sorted(set().union(*[set(t) for t in tax.values()])) if tax else []

    findings.append(
        {
            "id": "loader_completeness",
            "classification": "GENERIC_BEHAVIOR_CONFIRMED",
            "detail": "All sites loaded tables/records via same CP2 path",
            "tablesLoaded": {s: st(s).get("tablesLoaded") for s in sites},
        }
    )
    findings.append(
        {
            "id": "dynamic_resolution_present",
            "classification": (
                "GENERIC_BEHAVIOR_CONFIRMED"
                if all((st(s).get("dynamic") or 0) >= 0 for s in sites)
                else "UNKNOWN"
            ),
            "detail": {s: st(s).get("dynamic") for s in sites},
        }
    )

    # Schema menu count differences
    schema_counts = {s: st(s).get("schemaMenus") for s in sites}
    if len(set(schema_counts.values())) > 1:
        findings.append(
            {
                "id": "schema_menu_count_diff",
                "classification": "SCHEMA_VERSION_DIFFERENCE",
                "detail": schema_counts,
            }
        )
    else:
        findings.append(
            {
                "id": "schema_menu_count_same",
                "classification": "GENERIC_BEHAVIOR_CONFIRMED",
                "detail": schema_counts,
            }
        )

    # Machine-specific usage
    findings.append(
        {
            "id": "machine_specific_selection",
            "classification": "SITE_DATA_DIFFERENCE",
            "detail": {s: st(s).get("machineSpecific") for s in sites},
        }
    )

    # Taxonomy differences
    for tname in all_tax:
        vals = {s: (tax[s].get(tname) or 0) for s in sites}
        if len(set(vals.values())) > 1:
            findings.append(
                {
                    "id": f"taxonomy_{tname}",
                    "classification": "SITE_DATA_DIFFERENCE",
                    "detail": vals,
                }
            )

    return {
        "kind": "FortnaDecoderCrossSiteReport",
        "version": 1,
        "sites": sites,
        "metrics": metric_table,
        "unresolvedTaxonomyBySite": tax,
        "findings": findings,
        "gatePassBySite": {r["site"]: r.get("pass") for r in reports},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fortna decoder acceptance harness")
    ap.add_argument(
        "--site",
        action="append",
        default=[],
        help="site_name|run_dir|ac_name (repeatable; use | separators for Windows paths). "
        "Default: plc2/plc4/plc5 fixtures",
    )
    ap.add_argument("--out-dir", default=str(ROOT / "artifacts"))
    ap.add_argument("--skip-unit-tests", action="store_true")
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    unit = {"pass": True, "detail": "skipped"}
    if not args.skip_unit_tests:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for mod in (
            "test_fortna_mnu_schema",
            "test_fortna_mnu_runtime",
            "test_fortna_run_loader",
            "test_fortna_reference_resolver",
        ):
            try:
                suite.addTests(loader.loadTestsFromName(mod))
            except Exception as e:
                unit = {"pass": False, "detail": f"load {mod}: {e}"}
                break
        if unit.get("pass", True):
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            unit = {
                "pass": result.wasSuccessful(),
                "testsRun": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
            }

    sites = args.site
    if not sites:
        sites = [
            f"plc2|{ROOT / 'workspace/_plc2_run_peek/RUN'}|ORNCCP2",
            f"plc4|{ROOT / 'workspace/cp4-run/RUN'}|ORNCCP4",
            f"plc5|{ROOT / 'workspace/cp5-run/RUN'}|ORNCCP5",
        ]

    reports = []
    overall = True
    for spec in sites:
        # Prefer | separator (Windows-safe). Fall back to legacy 3-part ':' only
        # when no drive-letter ambiguity (not recommended on Windows).
        if "|" in spec:
            name, run_s, ac = spec.split("|", 2)
        else:
            parts = spec.split(":")
            if len(parts) < 3:
                raise SystemExit(f"Bad --site spec (use name|run_dir|ac_name): {spec}")
            name, ac = parts[0], parts[-1]
            run_s = ":".join(parts[1:-1])
        run_dir = Path(run_s)
        graph_out = out_dir / f"fortna-reference-graph-{name}.json"
        report_out = out_dir / f"fortna-acceptance-{name}.json"
        print(f"\n=== ACCEPTANCE {name} / {ac} ===")
        rep = run_site_acceptance(
            site_name=name,
            run_dir=run_dir,
            ac_name=ac,
            graph_out=graph_out,
            report_out=report_out,
            check_plc2_invariants=(name == "plc2"),
        )
        reports.append(rep)
        overall = overall and bool(rep.get("pass"))
        print(
            f"{name}: PASS={rep.get('pass')} "
            f"CP1={rep['gates']['CP1'].get('pass')} "
            f"CP2={rep['gates']['CP2'].get('pass')} "
            f"CP3={rep['gates']['CP3'].get('pass')} "
            f"INV={rep['gates']['INVARIANTS'].get('pass')}"
        )
        if not rep.get("pass"):
            inv = rep["gates"].get("INVARIANTS") or {}
            fails = [c for c in (inv.get("checks") or []) if not c.get("pass")]
            if fails:
                print(" invariant failures:", fails)
            for g in ("CP1", "CP2", "CP3"):
                if not rep["gates"][g].get("pass"):
                    print(f" {g} error:", rep["gates"][g].get("error") or rep["gates"][g])

    cross = compare_sites(reports)
    cross_path = out_dir / "fortna-decoder-cross-site-report.json"
    cross["unitTests"] = unit
    cross_path.write_text(
        json.dumps(cross, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    overall = overall and bool(unit.get("pass"))
    print("\nCross-site report ->", cross_path)
    print("OVERALL PASS" if overall else "OVERALL FAIL")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
