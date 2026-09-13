#!/usr/bin/env python3
"""Tests for Hardware/I/O model (PhysicalWordResolver consumer) — CP4 fixture."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_model import build_hardware_io_model  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"
MACHINE = "ORNCCP4"


class TestHardwareIoModelCp4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (CP4_RUN / "project.cfg").is_file(), f"missing CP4 RUN at {CP4_RUN}"
        cls.run_dir = CP4_RUN
        cls.machine = MACHINE
        cls.resolver = PhysicalWordResolver(cls.run_dir, cls.machine)
        cls.model = build_hardware_io_model(cls.run_dir, cls.machine)

    def test_model_ok(self):
        self.assertTrue(self.model.get("ok"))
        self.assertEqual(self.model["controller"]["machine"], MACHINE)

    def test_adapters_match_physical_map_rio_names(self):
        pm_rios = [
            a.get("rio_name")
            for a in (self.resolver.physical_map.get("adapters") or [])
        ]
        model_rios = [a.get("rio_name") for a in (self.model.get("adapters") or [])]
        self.assertEqual(model_rios, pm_rios)
        self.assertTrue(pm_rios, "expected at least one adapter from resolver")

    def test_at_least_one_channel_matches_by_word_bit(self):
        bwb = self.resolver.physical_map.get("by_word_bit") or {}
        self.assertTrue(bwb, "expected by_word_bit entries")
        matched = False
        for ad in self.model.get("adapters") or []:
            for mod in ad.get("modules") or []:
                for ch in mod.get("channels") or []:
                    addr = ch.get("physical_address")
                    key = ch.get("word_bit_key")
                    if key and key in bwb and addr == bwb[key].get("channel"):
                        matched = True
                        break
                if matched:
                    break
            if matched:
                break
        self.assertTrue(
            matched,
            "expected at least one module channel physical_address to match by_word_bit channel",
        )

    def test_no_invented_modules_beyond_eipcfg(self):
        """Every model module must come from eipcfg (resolver adapters) — no extras."""
        pm_keys = set()
        for ad in self.resolver.physical_map.get("adapters") or []:
            rio = ad.get("rio_name")
            for mod in ad.get("modules") or []:
                pm_keys.add((rio, int(mod.get("slot") or 0), mod.get("type") or ""))

        model_keys = set()
        for ad in self.model.get("adapters") or []:
            rio = ad.get("rio_name")
            for mod in ad.get("modules") or []:
                model_keys.add((rio, int(mod.get("slot") or 0), mod.get("type") or ""))

        self.assertEqual(model_keys, pm_keys)
        # Model must not invent modules outside eipcfg set
        self.assertFalse(model_keys - pm_keys)

    def test_panels_from_configio_only(self):
        panels = self.model["control_panels"]["panels"]
        self.assertEqual(panels, list(self.resolver.topology.get("panel_order") or []))
        # CP4 fixture evidence includes CP1 + CP4 — never invent conveyor-number CPs
        for p in panels:
            self.assertRegex(p, r"^CP\d+$")

    def test_io_word_map_passthrough(self):
        self.assertEqual(self.model.get("io_word_map"), self.resolver.io_word_map())

    def test_aent_included_as_adapter_card(self):
        found_head = False
        for ad in self.model.get("adapters") or []:
            for mod in ad.get("modules") or []:
                if mod.get("is_adapter_card"):
                    found_head = True
                    self.assertIn("AENT", (mod.get("type") or "").upper())
        self.assertTrue(found_head, "expected AENT head included as adapter card")


if __name__ == "__main__":
    unittest.main()
