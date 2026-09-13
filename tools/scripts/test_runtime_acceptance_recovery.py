#!/usr/bin/env python3
"""Integration tests for the Electron-equivalent Import→Discover→Build chain."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_knowledge_enrich import build_sawtooth_editor_v2  # noqa: E402
from fortna_runtime_acceptance_recovery import _l5x_counts  # noqa: E402
from fortna_sitemodel_to_autogen import (  # noqa: E402
    site_model_to_sawtooth_build,
    site_model_to_sorter_build,
)


class RuntimeAcceptanceRecoveryTests(unittest.TestCase):
    def test_studio_candidates_exist_with_io(self):
        for mach in ("ORNCCP2", "ORNCCP4", "ORNCCP5"):
            p = ROOT / "exports" / "studio-validation" / f"{mach}_ui_candidate.L5X"
            self.assertTrue(p.is_file(), f"missing {p}")
            c = _l5x_counts(p)
            self.assertGreater(c.get("module_entries") or 0, 0, mach)
            self.assertGreater(c.get("io_map_xic_ote_refs") or 0, 0, mach)
            self.assertFalse(c.get("io_map_nop_only"), mach)
            self.assertIn("IO_MAP", c.get("programs") or [])

    def test_cp4_sawtooth_in_studio_candidate(self):
        p = ROOT / "exports" / "studio-validation" / "ORNCCP4_ui_candidate.L5X"
        c = _l5x_counts(p)
        self.assertTrue(c.get("has_sawtooth_merge"), c.get("programs"))

    def test_site_model_to_sawtooth_bridge(self):
        # Prefer per-machine discovery if present
        candidates = [
            ROOT / "exports" / "run-discovery" / "ORNCCP4" / "site_model.json",
            ROOT / "exports" / "run-discovery" / "site_model.json",
        ]
        site_path = next((p for p in candidates if p.is_file()), None)
        if not site_path:
            self.skipTest("no site_model.json")
        site = json.loads(site_path.read_text(encoding="utf-8"))
        if not (site.get("sawtooth_merges") or []):
            self.skipTest("fixture has no sawtooth")
        site.setdefault("editors", {})["sawtooth"] = build_sawtooth_editor_v2(site)
        sb = site_model_to_sawtooth_build(site)
        self.assertIsNotNone(sb)
        self.assertTrue(sb.get("collector_conveyor") or sb.get("lanes"))
        self.assertFalse(sb.get("discovery_source") == "dev_prefill_plc4")

    def test_sorter_bridge_marks_unresolved(self):
        candidates = [
            ROOT / "exports" / "run-discovery" / "ORNCCP4" / "site_model.json",
            ROOT / "exports" / "run-discovery" / "site_model.json",
        ]
        site_path = next((p for p in candidates if p.is_file()), None)
        if not site_path:
            self.skipTest("no site_model.json")
        site = json.loads(site_path.read_text(encoding="utf-8"))
        if not (site.get("sorters") or []):
            self.skipTest("fixture has no sorter")
        sr = site_model_to_sorter_build(site)
        self.assertIsNotNone(sr)
        self.assertTrue(sr.get("detected") or sr.get("sorters_detected") or sr.get("encoders"))
        self.assertTrue(sr.get("configuration_required"))


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
