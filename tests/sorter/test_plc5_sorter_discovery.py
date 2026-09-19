#!/usr/bin/env python3
"""PLC5 sorter blind RUN discovery — no machine==ORNCCP5 hardcoding in production path."""
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
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_run_workspace_discover import discover as workspace_discover  # noqa: E402
from fortna_sorter_discovery import (  # noqa: E402
    build_canonical_sorter_model,
    discover as sorter_discover,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"

# Expected CP5 entities — asserted as discovery *outcomes*, never injected into prod code.
EXPECTED_CP5 = {
    "504_BELT",
    "506_SHIP_SORTER",
    "508_SHIP_SORTER",
    "509_SHIP_SORTER",
    "510_SHIP_SORTER",
}
EXPECTED_ENC = {"ENC504", "ENC506", "ENC508", "ENC509", "ENC510"}


def _prod_sources() -> list[Path]:
    return [
        SCRIPTS / "fortna_sorter_discovery.py",
        SCRIPTS / "fortna_run_workspace_discover.py",
        SCRIPTS / "fortna_knowledge_enrich.py",
    ]


class TestPlc5SorterDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CP5_RUN.is_dir():
            raise unittest.SkipTest(f"CP5 RUN missing: {CP5_RUN}")

    def test_no_ornccp5_hardcode_in_production(self) -> None:
        for path in _prod_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotRegex(
                text,
                r"""machine\s*==\s*['\"]ORNCCP5['\"]""",
                msg=f"{path.name} must not hardcode machine==ORNCCP5",
            )
            self.assertNotIn("504_BELT", text, msg=f"{path.name} must not embed CP5 sorter names")
            self.assertNotIn("506_SHIP_SORTER", text)

    def test_canonical_finds_five_cp5_sorters(self) -> None:
        model = build_canonical_sorter_model(CP5_RUN, "ORNCCP5")
        names = {
            (s.get("name") or {}).get("value")
            if isinstance(s.get("name"), dict)
            else s.get("name")
            for s in (model.get("sorters") or [])
        }
        self.assertEqual(model.get("sorter_count"), 5)
        self.assertEqual(names, EXPECTED_CP5)
        encs = {
            (s.get("encoder_io") or {}).get("value")
            if isinstance(s.get("encoder_io"), dict)
            else s.get("encoder_io")
            for s in (model.get("sorters") or [])
        }
        self.assertEqual(encs, EXPECTED_ENC)
        apps = {
            (a.get("name") or {}).get("value")
            if isinstance(a.get("name"), dict)
            else a.get("name")
            for a in (model.get("app_controls") or [])
        }
        self.assertIn("SHIP_SORTER", apps)
        self.assertGreaterEqual(len(model.get("scan_bosses") or []), 1)
        self.assertGreaterEqual(len(model.get("divert_rows") or []), 1)
        self.assertGreaterEqual(len(model.get("zone_lanes") or []), 1)
        fa = model.get("field_authority") or {}
        self.assertEqual(fa.get("divert_lane_topology"), "PROVEN")
        # Deep join: Outpoints.Outpoint I/O via Lane name — PROVEN when present.
        self.assertIn(fa.get("divert_output_io"), {"PROVEN", "DERIVED", "REVIEW_REQUIRED"})
        self.assertEqual(model.get("plc_generation"), "PHASE1_SUPPORTED")
        proven_io = 0
        for row in model.get("divert_rows") or []:
            auth = row.get("authority") or {}
            self.assertIn(
                auth.get("divert_output_io"),
                {"PROVEN", "DERIVED", "REVIEW_REQUIRED"},
            )
            if auth.get("divert_output_io") == "PROVEN":
                proven_io += 1
        self.assertGreaterEqual(proven_io, 1)

    def test_sorter_discover_api(self) -> None:
        result = sorter_discover(CP5_RUN, "ORNCCP5")
        canon = result.get("canonical_sorter_model") or {}
        self.assertEqual(canon.get("sorter_count"), 5)
        sub = result.get("subsystem_model") or {}
        self.assertEqual(
            (sub.get("characterization") or {}).get("active_sorter_count", {}).get("value"),
            5,
        )

    def test_workspace_discover_editors_populated(self) -> None:
        out = ROOT / "workspace" / "_tmp_test_plc5_sorter_disc"
        summary = workspace_discover(CP5_RUN, "ORNCCP5", out, blind=True)
        self.assertIsInstance(summary, dict)
        site_path = out / "site_model.json"
        self.assertTrue(site_path.is_file())
        site = json.loads(site_path.read_text(encoding="utf-8"))
        self.assertEqual(len(site.get("sorters") or []), 5)
        self.assertEqual(len(site.get("encoders") or []), 5)
        ed = (site.get("editors") or {}).get("sorter") or {}
        self.assertTrue(ed.get("detected"))
        self.assertEqual(ed.get("sorter_count"), 5)
        self.assertGreaterEqual(len(ed.get("divert_rows") or []), 1)
        self.assertGreaterEqual(len(ed.get("tracking_path") or []), 5)
        self.assertEqual(ed.get("plc_generation"), "PHASE1_SUPPORTED")
        sm = site.get("sorter_model") or {}
        self.assertEqual(sm.get("sorter_count"), 5)

    def test_plc2_zero_sorters_when_run_available(self) -> None:
        if not PLC2_RUN.is_dir():
            self.skipTest(f"PLC2 RUN not available: {PLC2_RUN}")
        model = build_canonical_sorter_model(PLC2_RUN, "ORNCCP2")
        self.assertEqual(model.get("sorter_count"), 0)
        self.assertFalse(model.get("detected"))
        result = sorter_discover(PLC2_RUN, "ORNCCP2")
        self.assertEqual(
            (result.get("canonical_sorter_model") or {}).get("sorter_count"),
            0,
        )


if __name__ == "__main__":
    unittest.main()
