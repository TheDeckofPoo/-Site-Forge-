#!/usr/bin/env python3
"""Blind/synthetic sorter leaf generation — no Greensboro constants."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_leaves import (  # noqa: E402
    build_synthetic_sorter_site,
    generate_sorter_leaves,
)

FORBIDDEN = ("ORNCCP", "Greensboro", "PLC2", "PLC4", "PLC5", "504_BELT", "SHIP_SORTER")


class TestSorterLeavesBlind(unittest.TestCase):
    def test_synthetic_generates_leaves_without_site_constants(self):
        site = build_synthetic_sorter_site()
        # Different lane/destination counts encoded only in synthetic names
        site["sorters"].append(
            {
                "raw_name": "BETA_DEST_BANK",
                "normalized_name": "BETA_DEST_BANK",
                "encoder_io": "ENC9555",
                "inclusion": "INCLUDED",
            }
        )
        site["encoders"].append(
            {
                "raw_name": "ENC9555",
                "encoder_io": "ENC9555_PULSE",
                "inclusion": "INCLUDED",
                "source_table": "Encoders.asc",
            }
        )
        result = generate_sorter_leaves(site)
        self.assertFalse(result.get("greensboro_constants"))
        self.assertFalse(result.get("gold_sorter_track_cloned"))
        self.assertIn("encoder_speed", result["generated_capability_names"])
        self.assertIn("scanner_association", result["generated_capability_names"])
        self.assertIn("reason_code", result["generated_capability_names"])
        self.assertIn("divert_trigger", result["unsupported"])
        blob = json.dumps(result)
        for bad in FORBIDDEN:
            self.assertNotIn(bad, blob)
        self.assertIn("ENC9001", result["tag_fragment_xml"])
        self.assertIn("ALPHA_SCAN_NORTH", result["tag_fragment_xml"])
        self.assertIn("REASON_NO_READ", result["tag_fragment_xml"])


if __name__ == "__main__":
    unittest.main()
