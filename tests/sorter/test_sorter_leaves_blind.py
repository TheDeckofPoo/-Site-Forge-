#!/usr/bin/env python3
"""Blind/synthetic sorter leaf generation — no Greensboro constants."""
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
        self.assertIn("track_offset", result["capabilities"])
        self.assertEqual(
            result["capabilities"]["track_offset"]["state"],
            "CONFIGURATION_REQUIRED",
        )
        blob = json.dumps(result)
        for bad in FORBIDDEN:
            self.assertNotIn(bad, blob)
        self.assertIn("ENC9001", result["tag_fragment_xml"])
        self.assertIn("ALPHA_SCAN_NORTH", result["tag_fragment_xml"])
        self.assertIn("REASON_NO_READ", result["tag_fragment_xml"])


if __name__ == "__main__":
    unittest.main()
