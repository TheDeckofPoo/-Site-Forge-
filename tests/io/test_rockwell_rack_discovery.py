#!/usr/bin/env python3
"""Rockwell catalog detector + rack discovery + display-name immutability."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_rack_discovery import discover_racks, rename_rack_display  # noqa: E402
from fortna_rockwell_catalog import detect_rockwell_catalogs, first_catalog  # noqa: E402

MSCATL = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"


class TestRockwellCatalogDetector(unittest.TestCase):
    def test_embedded_catalogs(self) -> None:
        cases = [
            ("CP3_LOCAL_1794-IA16-5", "1794-IA16", "-5"),
            ("T_RIO2_1794-OA8I-33", "1794-OA8I", "-33"),
            ("WHATEVER_1734-OA4", "1734-OA4", ""),
            ("1794-AENTR", "1794-AENTR", ""),
            ("1734-IB8", "1734-IB8", ""),
        ]
        for raw, cat, trail in cases:
            hits = detect_rockwell_catalogs(raw)
            self.assertTrue(hits, raw)
            self.assertEqual(hits[0].catalog_number, cat)
            self.assertEqual(hits[0].trailing_text, trail)

    def test_trailing_not_auto_slot(self) -> None:
        h = first_catalog("1794-IA16-5")
        self.assertIsNotNone(h)
        self.assertEqual(h.trailing_text, "-5")
        # Detector does not expose physical_slot field
        self.assertFalse(hasattr(h, "physical_slot"))


@unittest.skipUnless((MSCATL / "project.cfg").is_file(), "MSCATL missing")
class TestRackDiscoveryAtlanta(unittest.TestCase):
    def test_deterministic_provisional_order(self) -> None:
        a = discover_racks(MSCATL, "MSCATL_CP3")
        b = discover_racks(MSCATL, "MSCATL_CP3")
        names_a = [r["provisional_display_name"] for r in a["racks"]]
        names_b = [r["provisional_display_name"] for r in b["racks"]]
        self.assertEqual(names_a, names_b)
        self.assertEqual(names_a, [f"AREA_RIO_{i}" for i in range(1, len(names_a) + 1)])
        self.assertGreaterEqual(len(a["racks"]), 1)
        # Modules slotted
        self.assertGreater(a["stats"]["slotted_modules"], 0)

    def test_display_rename_does_not_change_identity(self) -> None:
        disc = discover_racks(MSCATL, "MSCATL_CP3")
        rid = disc["racks"][0]["canonical_adapter_id"]
        before = copy.deepcopy(disc["racks"][0])
        renamed = rename_rack_display(disc, rid, "MAIN_SORT_RACK")
        after = next(r for r in renamed["racks"] if r["canonical_adapter_id"] == rid)
        self.assertEqual(after["engineer_display_name"], "MAIN_SORT_RACK")
        self.assertEqual(after["canonical_adapter_id"], before["canonical_adapter_id"])
        self.assertEqual(after["ip_address"], before["ip_address"])
        self.assertEqual(
            [m["physical_slot"] for m in after["modules"]],
            [m["physical_slot"] for m in before["modules"]],
        )
        self.assertEqual(
            [m["catalog_number"] for m in after["modules"]],
            [m["catalog_number"] for m in before["modules"]],
        )
        self.assertEqual(after["provisional_display_name"], before["provisional_display_name"])

    def test_aggregate_tools(self) -> None:
        from fortna_ai_readonly_tools import SiteForgeReadOnlyContext, invoke_tool

        ctx = SiteForgeReadOnlyContext(MSCATL, "MSCATL_CP3", project="MSCATL_CP3")
        summ = invoke_tool(ctx, "get_configio_binding_cluster_summary")
        self.assertTrue(summ.get("ok"))
        self.assertGreaterEqual(summ.get("configio_word_count"), 1)
        bank = invoke_tool(ctx, "get_eip_bank_map")
        self.assertTrue(bank.get("ok"))
        self.assertGreater(bank.get("count"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
