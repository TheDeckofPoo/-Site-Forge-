"""P0 truth-chain: mandatory site_model identity, sorter fail-closed, Pick Area unify, SHIP scanners, API check."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_area_symbol import (  # noqa: E402
    area_plc_symbol,
    is_provisional_controller_area,
    normalize_area_row,
)
from fortna_run_workspace_discover import (  # noqa: E402
    discover,
    site_model_identity_matches,
)
from fortna_workbook import (  # noqa: E402
    _unify_provisional_area_identity,
    apply_workbook_to_input,
)

RUN_ROOTS = [
    REPO / "workspace" / "_reno_peek",
    Path(r"C:\dev\worktree\FortnaPlus-mscreno-genclose\workspace\_reno_peek"),
]


def _run(machine: str) -> Path | None:
    needle = f"MSCRENO-{machine}-RUN"
    for root in RUN_ROOTS:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and needle.upper() in child.name.upper():
                run = child / "RUN"
                if run.is_dir() and (run / "project.cfg").is_file():
                    return run
    return None


class TestMandatorySiteModelIdentity(unittest.TestCase):
    def test_anonymous_model_rejected(self) -> None:
        ok, reason = site_model_identity_matches({"sorters": [{"raw_name": "X"}]})
        self.assertFalse(ok)
        self.assertEqual(reason, "SITE_MODEL_MISSING_CONTROLLER")

    def test_missing_run_fingerprint_rejected(self) -> None:
        site = {
            "machine_scope": "MSCRENOSHIP",
            "identity": {"machine_scope": "MSCRENOSHIP"},
        }
        ok, reason = site_model_identity_matches(
            site, machine="MSCRENOSHIP", run_fingerprint="want-fp"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "SITE_MODEL_MISSING_RUN_FINGERPRINT")

    def test_missing_fingerprint_even_without_want_rejected(self) -> None:
        site = {"machine_scope": "MSCRENOSHIP", "identity": {"machine_scope": "MSCRENOSHIP"}}
        ok, reason = site_model_identity_matches(site, machine="MSCRENOSHIP")
        self.assertFalse(ok)
        self.assertEqual(reason, "SITE_MODEL_MISSING_RUN_FINGERPRINT")

    def test_identity_mismatch_rejected(self) -> None:
        site = {
            "machine_scope": "MSCRENOSHIP",
            "run_fingerprint": "aaa",
            "identity": {"machine_scope": "MSCRENOSHIP", "run_fingerprint": "aaa"},
        }
        ok, reason = site_model_identity_matches(
            site, machine="MSCRENOSHIP", run_fingerprint="bbb"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "RUN_FINGERPRINT_MISMATCH")

    def test_matching_identity_accepted(self) -> None:
        site = {
            "machine_scope": "MSCRENOSHIP",
            "run_fingerprint": "fp1",
            "run_dir": r"C:\tmp\run",
            "identity": {
                "machine_scope": "MSCRENOSHIP",
                "run_fingerprint": "fp1",
                "run_dir": r"C:\tmp\run",
            },
        }
        ok, reason = site_model_identity_matches(
            site,
            machine="MSCRENOSHIP",
            run_dir=r"C:\tmp\run",
            run_fingerprint="fp1",
        )
        self.assertTrue(ok, reason)

    def test_main_js_rejects_missing_identity(self) -> None:
        main = (REPO / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("SITE_MODEL_MISSING_CONTROLLER", main)
        self.assertIn("SITE_MODEL_MISSING_RUN_FINGERPRINT", main)
        self.assertIn("DISCOVERY_REQUIRED", main)
        # Soft gate (both sides must exist) must not remain as the only check.
        self.assertNotIn(
            "if (wantFp && gotFp && wantFp !== gotFp)",
            main,
        )


class TestSorterFailClosedUi(unittest.TestCase):
    def test_dashboard_invalidates_stale_sorter_on_model_reject(self) -> None:
        js = (REPO / "dashboard" / "fortna-plus.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("invalidateStaleSorterDisplay", js)
        self.assertIn("SORTER DISCOVERY UNAVAILABLE / FAILED", js)
        self.assertIn("discovery_status", js)
        # Must not claim empty discovery when discovery itself failed.
        self.assertIn("discoveryFailed", js)

    def test_zero_canonical_sorter_clears_review_surface(self) -> None:
        js = (REPO / "dashboard" / "fortna-plus.js").read_text(encoding="utf-8", errors="replace")
        # Default sorter has empty known_sorters; invalidate wipes workbook.sorter_build.
        self.assertIn("delete autogenState.workbook.sorter_build", js)
        self.assertIn("localStorage.removeItem('fortna_sorter_build')", js)


class TestPickAreaCanonicalIdentity(unittest.TestCase):
    def test_provisional_vs_engineer_helpers(self) -> None:
        self.assertTrue(is_provisional_controller_area("MSCRENOPICK_Area", "MSCRENOPICK"))
        self.assertFalse(is_provisional_controller_area("Area_Test1", "MSCRENOPICK"))
        row = normalize_area_row("Area_Test1")
        self.assertEqual(row["display_name"], "Area_Test1")
        self.assertEqual(row["plc_symbol"], "Area_Test1")
        self.assertTrue(row["canonical_area_id"])

    def test_unify_provisional_into_area_test1(self) -> None:
        from fortna_autogen import AutogenInput, ConveyorRow

        inp = AutogenInput(
            machine="MSCRENOPICK",
            areas=["MSCRENOPICK_Area"],
            safety_zones=["MSCRENOPICK_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P101",
                    main_area="MSCRENOPICK_Area",
                    safety_zone="MSCRENOPICK_ESZone1",
                    type="Transport with MS",
                ),
                ConveyorRow(
                    number=2,
                    conveyor="P102",
                    main_area="MSCRENOPICK_Area",
                    safety_zone="MSCRENOPICK_ESZone1",
                    type="Transport with MS",
                ),
            ],
        )
        workbook = {
            "machine": "MSCRENOPICK",
            "areas": [{"name": "Area_Test1", "display_name": "Area_Test1"}],
            "safety_build": {
                "zones": [
                    {
                        "name": "Area_Test1_ESZone1",
                        "area": "Area_Test1",
                        "areaRef": "Area_Test1",
                        "members": ["ESPB1"],
                        "engineerEdited": True,
                        "conveyors": [],
                    }
                ]
            },
        }
        report = _unify_provisional_area_identity(inp, workbook)
        self.assertEqual(report.get("reason"), "unified")
        self.assertEqual(len(report.get("migrated_conveyors") or []), 2)
        for c in inp.conveyors:
            self.assertEqual(c.main_area, "Area_Test1")
            self.assertEqual(c.safety_zone, "Area_Test1_ESZone1")
        # Provisional retired from areas list
        area_syms = []
        for a in inp.areas:
            if isinstance(a, dict):
                area_syms.append(str(a.get("plc_symbol") or a.get("display_name") or ""))
            else:
                area_syms.append(str(a))
        self.assertIn("Area_Test1", area_syms)
        self.assertNotIn("MSCRENOPICK_Area", area_syms)

    def test_apply_workbook_unifies_before_pd0003_keys(self) -> None:
        from fortna_autogen import AutogenInput, ConveyorRow

        inp = AutogenInput(
            machine="MSCRENOPICK",
            areas=["MSCRENOPICK_Area"],
            safety_zones=["MSCRENOPICK_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P200",
                    main_area="MSCRENOPICK_Area",
                    safety_zone="MSCRENOPICK_ESZone1",
                    type="Transport with MS",
                ),
            ],
        )
        workbook = {
            "machine": "MSCRENOPICK",
            "safety_build": {
                "zones": [
                    {
                        "name": "Area_Test1_ESZone1",
                        "area": "Area_Test1",
                        "members": ["ESPB2", "ESPB24"],
                        "engineerEdited": True,
                    }
                ]
            },
        }
        apply_workbook_to_input(inp, workbook)
        self.assertEqual(inp.conveyors[0].main_area, "Area_Test1")
        self.assertEqual(area_plc_symbol(inp.conveyors[0].main_area), "Area_Test1")


class TestShipScannerDiscovery(unittest.TestCase):
    def test_ship_scanners_promoted_to_top_level(self) -> None:
        run = _run("MSCRENOSHIP")
        if run is None:
            self.skipTest("SHIP RUN missing")
        with tempfile.TemporaryDirectory() as td:
            discover(run, "MSCRENOSHIP", Path(td), blind=True)
            site = json.loads((Path(td) / "site_model.json").read_text(encoding="utf-8"))
        scanners = site.get("scanners") or []
        self.assertEqual(len(scanners), 7, "top-level scanners must match RUN ScnScanDevice")
        self.assertEqual((site.get("counts") or {}).get("scanners"), 7)
        nested = (site.get("sorter_model") or {}).get("scanners") or []
        self.assertEqual(len(nested), 7)
        names = []
        for s in scanners:
            n = s.get("name")
            if isinstance(n, dict):
                n = n.get("value")
            names.append(str(n or s.get("raw_name") or "").upper())
        self.assertIn("SHIPSCAN1", names)
        # No Greensboro residue
        blob = json.dumps(names)
        self.assertNotIn("504_BELT", blob)
        self.assertNotIn("ENC504", blob)


class TestApiKeyStatusCheck(unittest.TestCase):
    def test_check_api_accepts_project_context(self) -> None:
        from fortna_ai_io_analyze import main

        # --check-api must work WITH and WITHOUT --run-dir/--machine (no argparse crash).
        with mock.patch("fortna_ai_io_analyze.api_key_available", return_value=True):
            rc = main(["--check-api", "--run-dir", str(REPO), "--machine", "MSCRENOSHIP"])
            self.assertEqual(rc, 0)
        with mock.patch("fortna_ai_io_analyze.api_key_available", return_value=False):
            rc = main(["--check-api"])
            self.assertEqual(rc, 0)

    def test_main_js_passes_active_project_context(self) -> None:
        main = (REPO / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("ai-io-check-api", main)
        # Must pass the same active project context as escalation.
        idx = main.index("ai-io-check-api")
        chunk = main[idx : idx + 1200]
        self.assertIn("--check-api", chunk)
        self.assertIn("--run-dir", chunk)
        self.assertIn("--machine", chunk)
        self.assertIn("ACTIVE_DIR", chunk)


if __name__ == "__main__":
    unittest.main()
