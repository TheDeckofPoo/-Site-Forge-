#!/usr/bin/env python3
"""PATCH torture gate — Overnight Phase 2 regression/chaos entrypoint.

Runnable without Electron UI. Invokes unit/smoke lanes:

  P1 site-switch identity (SHIP↔PICK workbook/machine gates)
  P3 corrupt / incomplete RUN fail-closed
  P4 AI independence (deterministic I/O with AI down)
  P6 residue scan smoke (configured sorter pack)
  P7 static L5X quality smoke (convergence_final)
  P8 discovery timing smoke (SHIP / PICK)

Usage:
  python tools/scripts/patch_gate.py
  python tools/scripts/patch_gate.py fcabcb5
  python tools/scripts/patch_gate.py --json-only

Exit codes:
  0 = all required lanes PASS (skips allowed when fixtures absent)
  1 = one or more required lanes FAIL
  2 = SHA mismatch vs optional expected argument
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import traceback
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
DIAG = SCRIPTS / "diagnostics"
OUT_DIR = REPO / "exports" / "diagnostics" / "overnight_phase2"
RESULTS_JSON = OUT_DIR / "patch_torture_gate_results.json"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(DIAG))

from patch_torture_helpers import (  # noqa: E402
    discovery_timing,
    git_sha,
    git_sha_short,
    residue_scan_configured_sorter,
    resolve_convergence_l5x,
    scan_l5x_static_quality,
)


LANES: list[dict[str, Any]] = [
    {
        "id": "P1",
        "name": "site_switch_identity",
        "module": "tests.gate.test_p1_site_switch_identity",
        "required": True,
    },
    {
        "id": "P3",
        "name": "corrupt_run_fail_closed",
        "module": "tests.discovery.test_incomplete_run_fail_closed",
        "required": True,
    },
    {
        "id": "P4",
        "name": "ai_independence",
        "module": "tests.io.test_deterministic_io_no_ai",
        "required": True,
    },
    {
        "id": "P6",
        "name": "residue_scan_sorter",
        "module": "tests.sorter.test_sorter_foreign_description_residue",
        "required": True,
        "extra_smoke": "residue",
    },
    {
        "id": "P7",
        "name": "static_l5x_quality",
        "module": "tests.gate.test_patch_torture_gate.TestP7StaticL5xQualitySmoke",
        "required": True,
        "extra_smoke": "l5x",
    },
    {
        "id": "P8",
        "name": "discovery_timing",
        "module": "tests.gate.test_patch_torture_gate.TestP8DiscoveryTimingSmoke",
        "required": True,
        "extra_smoke": "timing",
    },
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_tests(module_path: str) -> unittest.TestSuite:
    """Load unittest suite from module or Module.Class path."""
    loader = unittest.defaultTestLoader
    if module_path.count(".") >= 3 and not module_path.startswith("tests."):
        # unexpected
        pass
    parts = module_path.split(".")
    # Module.Class form when last part starts with Test
    if parts and parts[-1].startswith("Test"):
        mod_name = ".".join(parts[:-1])
        class_name = parts[-1]
        mod = __import__(mod_name, fromlist=[class_name])
        cls = getattr(mod, class_name)
        return loader.loadTestsFromTestCase(cls)
    mod = __import__(module_path, fromlist=["*"])
    return loader.loadTestsFromModule(mod)


def _run_unittest_module(module_path: str) -> dict[str, Any]:
    suite = _load_tests(module_path)
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    skipped = len(getattr(result, "skipped", []) or [])
    errors = [
        {"test": str(t), "error": e.splitlines()[-1] if e else ""}
        for t, e in (result.errors + result.failures)
    ]
    ran = result.testsRun
    ok = result.wasSuccessful()
    return {
        "ok": ok,
        "tests_run": ran,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": skipped,
        "detail": errors[:8],
        "output_tail": "\n".join(stream.getvalue().splitlines()[-40:]),
    }


def _smoke_residue() -> dict[str, Any]:
    try:
        return residue_scan_configured_sorter()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()[-500:]}


def _smoke_l5x() -> dict[str, Any]:
    l5x = resolve_convergence_l5x()
    if l5x is None:
        return {"ok": False, "skipped": True, "reason": "CONVERGENCE_L5X_MISSING"}
    try:
        q = scan_l5x_static_quality(l5x)
        ok = (
            q["has_rslogix"]
            and q["has_controller"]
            and "MSCRENOSHIP" in str(q.get("controller_name") or "").upper()
            and int(q["blank_operand_count"]) == 0
            and q["has_io_map"]
            and int(q["bytes"]) > 100_000
        )
        q["ok"] = ok
        return q
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _smoke_timing() -> dict[str, Any]:
    out: dict[str, Any] = {"machines": {}, "ok": True}
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for machine in ("MSCRENOSHIP", "MSCRENOPICK"):
            try:
                r = discovery_timing(machine, base / machine)
            except Exception as exc:
                r = {"ok": False, "machine": machine, "error": str(exc)}
            out["machines"][machine] = r
            if r.get("skipped"):
                continue
            if not r.get("ok"):
                out["ok"] = False
    return out


def run_gate(*, expected_sha: str | None = None) -> dict[str, Any]:
    sha = git_sha(REPO)
    short = git_sha_short(REPO)
    report: dict[str, Any] = {
        "gate": "PATCH_TORTURE_GATE",
        "phase": "overnight_phase2",
        "generated_at": _ts(),
        "repository": str(REPO),
        "sha": sha,
        "sha_short": short,
        "expected_sha": expected_sha or "",
        "lanes": {},
        "ok": True,
        "sha_match": True,
    }
    if expected_sha:
        want = expected_sha.strip().lower()
        have = (sha or "").lower()
        report["sha_match"] = have.startswith(want) or want.startswith(have[: len(want)])
        if not report["sha_match"]:
            report["ok"] = False

    # Ensure tests package imports resolve from repo root.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    for lane in LANES:
        lid = lane["id"]
        entry: dict[str, Any] = {
            "id": lid,
            "name": lane["name"],
            "module": lane["module"],
            "required": bool(lane.get("required")),
        }
        try:
            ut = _run_unittest_module(lane["module"])
            entry["unittest"] = ut
            entry["ok"] = bool(ut.get("ok"))
        except Exception as exc:
            entry["unittest"] = {"ok": False, "error": str(exc)}
            entry["ok"] = False

        smoke_key = lane.get("extra_smoke")
        if smoke_key == "residue":
            entry["smoke"] = _smoke_residue()
            if entry["smoke"].get("skipped"):
                pass
            elif not entry["smoke"].get("ok", True):
                entry["ok"] = False
        elif smoke_key == "l5x":
            entry["smoke"] = _smoke_l5x()
            if entry["smoke"].get("skipped"):
                # Required lane with missing fixture → FAIL (truthful).
                entry["ok"] = False
                entry["reason"] = "CONVERGENCE_L5X_MISSING"
            elif not entry["smoke"].get("ok", True):
                entry["ok"] = False
        elif smoke_key == "timing":
            entry["smoke"] = _smoke_timing()
            if not entry["smoke"].get("ok", True):
                entry["ok"] = False

        report["lanes"][lid] = entry
        if lane.get("required") and not entry.get("ok"):
            report["ok"] = False

    report["summary"] = {
        "pass": [k for k, v in report["lanes"].items() if v.get("ok")],
        "fail": [k for k, v in report["lanes"].items() if not v.get("ok")],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PATCH Overnight Phase 2 torture gate")
    ap.add_argument(
        "sha",
        nargs="?",
        default="",
        help="Optional expected SHA (prefix ok, e.g. fcabcb5)",
    )
    ap.add_argument(
        "--json-only",
        action="store_true",
        help="Print JSON only (no human summary)",
    )
    ap.add_argument(
        "--out",
        default=str(RESULTS_JSON),
        help="Results JSON path",
    )
    args = ap.parse_args(argv)

    report = run_gate(expected_sha=args.sha or None)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not args.json_only:
        print(f"PATCH_TORTURE_GATE  sha={report.get('sha_short')}  ok={report.get('ok')}")
        if args.sha:
            print(f"  expected={args.sha}  sha_match={report.get('sha_match')}")
        for lid, lane in report.get("lanes", {}).items():
            status = "PASS" if lane.get("ok") else "FAIL"
            ut = lane.get("unittest") or {}
            print(
                f"  [{status}] {lid} {lane.get('name')}  "
                f"tests={ut.get('tests_run', '?')} "
                f"fail={ut.get('failures', 0)} err={ut.get('errors', 0)} "
                f"skip={ut.get('skipped', 0)}"
            )
            smoke = lane.get("smoke")
            if isinstance(smoke, dict) and smoke:
                if lid == "P8":
                    for m, r in (smoke.get("machines") or {}).items():
                        print(
                            f"         timing {m}: ok={r.get('ok')} "
                            f"secs={r.get('seconds')} equipment={r.get('equipment')}"
                        )
                elif lid == "P7":
                    print(
                        f"         l5x bytes={smoke.get('bytes')} "
                        f"blank={smoke.get('blank_operand_count')} "
                        f"controller={smoke.get('controller_name')}"
                    )
                elif lid == "P6":
                    print(
                        f"         residue hits={smoke.get('foreign_desc_count')} "
                        f"scrubbed={smoke.get('foreign_description_scrubbed')}"
                    )
        print(f"  results: {out_path}")

    if args.sha and not report.get("sha_match"):
        return 2
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
