#!/usr/bin/env python3
"""Tests for RUN-driven SiteModel discovery foundation.

Covers CP4/CP2 discovery, activity buckets, Area_1 default, table precedence,
no finished-PLC paths, and change_report.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_activity_classify import classify_object, classify_site_model  # noqa: E402
from fortna_run_workspace_discover import (  # noqa: E402
    assert_no_finished_plc_usage,
    discover,
)
from fortna_site_model import (  # noqa: E402
    ACTIVE_CONFIRMED,
    AVAILABLE,
    DEFAULT_AREA_ID,
    EXCLUDED,
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
    INCLUDED,
    PROV_ENGINEER_REQUIRED,
    change_report,
    merge_table_rows,
    write_json,
)

CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"
CP2_RUN = ROOT / "workspace" / "active" / "RUN"


class TestTablePrecedence(unittest.TestCase):
    def test_overlay_wins_base_fills_absent(self):
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td)
            # base: A + B
            (fortna / "Demo.asc").write_text(
                '"Name"~"Value"\n'
                "A~baseA\n"
                "B~baseB\n",
                encoding="utf-8",
            )
            # overlay: redefines A, adds C
            (fortna / "Demo.asc.CTRL1").write_text(
                '"Name"~"Value"\n'
                "A~overlayA\n"
                "C~overlayC\n",
                encoding="utf-8",
            )
            merged = merge_table_rows(fortna, "Demo.asc", "CTRL1")
            by_id = {r["identity"]: r for r in merged["rows"]}
            self.assertEqual(merged["resolution"], "merged_overlay_over_base")
            self.assertEqual(by_id["A"]["source_scope"], "controller_overlay")
            self.assertEqual(by_id["A"]["row"]["Value"], "overlayA")
            self.assertEqual(by_id["B"]["source_scope"], "base_fallback")
            self.assertEqual(by_id["B"]["row"]["Value"], "baseB")
            self.assertEqual(by_id["C"]["source_scope"], "controller_overlay")
            self.assertEqual(by_id["C"]["row"]["Value"], "overlayC")


class TestActivityClassifier(unittest.TestCase):
    def test_inactive_never_included(self):
        obj = {
            "normalized_name": "P999",
            "raw_name": "P999",
            "Offline": "Y",
            "evidence": [{"kind": "controller_io"}],
            "kind": "equipment",
        }
        classify_object(obj, machine="ORNCCP4", related_links={"P999"}, in_machine_scope=True)
        self.assertEqual(obj["active_state"], INACTIVE_CONFIRMED)
        self.assertEqual(obj["inclusion"], EXCLUDED)

    def test_historical_excluded(self):
        obj = {
            "normalized_name": "OLD1",
            "source_scope": "historical",
            "evidence": [],
            "kind": "equipment",
        }
        classify_object(obj, machine="ORNCCP4", superseded=True)
        self.assertEqual(obj["active_state"], HISTORICAL_OR_STALE)
        self.assertEqual(obj["inclusion"], EXCLUDED)

    def test_buckets_produced(self):
        model = {
            "equipment": [
                {
                    "canonical_id": "equipment:P1",
                    "normalized_name": "P1",
                    "raw_name": "P1",
                    "evidence": [{"kind": "ownership"}, {"kind": "controller_io"}],
                    "source_scope": "controller_overlay",
                    "kind": "equipment",
                    "IO_Address_Word": "10",
                }
            ],
            "relationships": [{"from": "M1", "to": "P1"}],
            "motors": [],
            "vfds": [],
            "photoeyes": [],
            "encoders": [],
            "estop_zones": [],
            "sawtooth_merges": [],
            "sorters": [],
            "tracking_systems": [],
            "wcs_interfaces": [],
            "areas": [],
            "controllers": [],
        }
        activity = classify_site_model(model, "ORNCCP4")
        self.assertIn("by_active_state", activity["counts"])
        self.assertIn("by_inclusion", activity["counts"])
        self.assertTrue(activity["counts"]["by_active_state"])
        self.assertEqual(model["equipment"][0]["inclusion"], INCLUDED)
        self.assertEqual(model["equipment"][0]["active_state"], ACTIVE_CONFIRMED)


@unittest.skipUnless(CP4_RUN.is_dir(), "CP4 RUN missing")
class TestCP4Discovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix="run_disc_cp4_"))
        cls.result = discover(CP4_RUN, "ORNCCP4", cls.out)
        cls.site = json.loads((cls.out / "site_model.json").read_text(encoding="utf-8"))
        cls.sub = json.loads((cls.out / "subsystems.json").read_text(encoding="utf-8"))
        cls.activity = json.loads(
            (cls.out / "activity_classification.json").read_text(encoding="utf-8")
        )
        cls.change = json.loads((cls.out / "change_report.json").read_text(encoding="utf-8"))

    def test_transport_populated(self):
        self.assertGreater(len(self.site.get("transport", {}).get("nodes") or []), 0)
        self.assertGreater(self.site["counts"]["transport_nodes"], 0)

    def test_sawtooth_populated(self):
        self.assertGreater(len(self.site.get("sawtooth_merges") or []), 0)
        self.assertTrue(self.sub["sawtooth"]["present"])
        self.assertGreater(self.sub["sawtooth"]["counts"]["lanes"], 0)

    def test_area_default(self):
        areas = self.site.get("areas") or []
        self.assertTrue(areas)
        a0 = areas[0]
        self.assertEqual(a0.get("normalized_name"), DEFAULT_AREA_ID.upper())
        self.assertEqual(a0.get("provenance"), PROV_ENGINEER_REQUIRED)
        included = [e for e in self.site["equipment"] if e.get("inclusion") == INCLUDED]
        self.assertTrue(included)
        self.assertTrue(all(e.get("area_id") == DEFAULT_AREA_ID for e in included))

    def test_inactive_excluded_not_included(self):
        for bucket in ("equipment", "motors", "vfds", "sorters", "sawtooth_merges"):
            for obj in self.site.get(bucket) or []:
                if obj.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                    self.assertEqual(obj.get("inclusion"), EXCLUDED)

    def test_activity_buckets(self):
        self.assertTrue(self.activity["counts"]["by_active_state"])
        self.assertTrue(self.activity["counts"]["by_inclusion"])

    def test_change_report_runs(self):
        self.assertIn(self.change.get("status"), {"NO_PREVIOUS", "COMPARED"})
        # second pass should compare
        discover(CP4_RUN, "ORNCCP4", self.out)
        change2 = json.loads((self.out / "change_report.json").read_text(encoding="utf-8"))
        self.assertEqual(change2.get("status"), "COMPARED")

    def test_no_finished_plc_paths_in_sources(self):
        for name in (
            "fortna_run_workspace_discover.py",
            "fortna_site_model.py",
            "fortna_activity_classify.py",
        ):
            assert_no_finished_plc_usage((SCRIPTS / name).read_text(encoding="utf-8"))


@unittest.skipUnless(CP2_RUN.is_dir(), "CP2 RUN missing")
class TestCP2Discovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix="run_disc_cp2_"))
        cls.result = discover(CP2_RUN, "ORNCCP2", cls.out)
        cls.site = json.loads((cls.out / "site_model.json").read_text(encoding="utf-8"))
        cls.sub = json.loads((cls.out / "subsystems.json").read_text(encoding="utf-8"))

    def test_transport_populated(self):
        self.assertGreater(len(self.site.get("transport", {}).get("nodes") or []), 0)

    def test_no_fake_sawtooth(self):
        # CP2 overlay SawMerge/SawLane has no active named merges
        self.assertEqual(len(self.site.get("sawtooth_merges") or []), 0)
        self.assertFalse(self.sub["sawtooth"]["present"])

    def test_area_default_when_needed(self):
        areas = self.site.get("areas") or []
        self.assertTrue(areas)
        self.assertEqual(areas[0].get("provenance"), PROV_ENGINEER_REQUIRED)


class TestChangeReportUnit(unittest.TestCase):
    def test_delta(self):
        prev = {
            "generated_at": "t0",
            "counts": {"equipment": 1},
            "equipment": [
                {"canonical_id": "equipment:P1", "normalized_name": "P1", "inclusion": INCLUDED}
            ],
            "sawtooth_merges": [],
            "sorters": [],
            "vfds": [],
            "encoders": [],
            "areas": [],
        }
        cur = {
            "generated_at": "t1",
            "counts": {"equipment": 2},
            "equipment": [
                {"canonical_id": "equipment:P1", "normalized_name": "P1", "inclusion": AVAILABLE},
                {"canonical_id": "equipment:P2", "normalized_name": "P2", "inclusion": INCLUDED},
            ],
            "sawtooth_merges": [],
            "sorters": [],
            "vfds": [],
            "encoders": [],
            "areas": [],
        }
        rep = change_report(prev, cur)
        self.assertEqual(rep["status"], "COMPARED")
        self.assertEqual(rep["count_delta"]["equipment"], 1)
        self.assertTrue(any(a["canonical_id"] == "equipment:P2" for a in rep["added"]))
        self.assertTrue(any(c["canonical_id"] == "equipment:P1" for c in rep["changed_inclusion"]))


if __name__ == "__main__":
    unittest.main()
