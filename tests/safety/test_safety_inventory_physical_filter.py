"""Assignable Safety inventory requires current-site physical I/O (site-neutral)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SB = REPO / "dashboard" / "safety-build.js"


class TestSafetyPhysicalInventoryFilter(unittest.TestCase):
    def test_partition_helper_exists(self):
        src = SB.read_text(encoding="utf-8", errors="replace")
        self.assertIn("isAssignablePhysicalSafetyDevice", src)
        self.assertIn("partitionSafetyInventory", src)
        self.assertIn("nonphysical_aliases_suppressed", src)
        self.assertIn("canonical_physical", src)

    def test_filter_does_not_destroy_search_input(self):
        src = SB.read_text(encoding="utf-8", errors="replace")
        # Focus-preserving filter path
        self.assertIn("Filter without destroying the search input", src)
        self.assertIn("row.style.display", src)
        # Must not call renderInventory() from sb-device-filter input
        # (that was the focus-loss bug)
        m = re.search(
            r"sb-device-filter[\s\S]{0,400}?addEventListener\('input'",
            src,
        )
        self.assertIsNotNone(m)
        block = src[m.start() : m.start() + 800]
        self.assertNotIn("renderInventory()", block)

    def test_no_site_name_special_cases(self):
        src = SB.read_text(encoding="utf-8", errors="replace")
        for banned in ("ORNCCP2", "Greensboro", "Trash_Line", "ModuleC"):
            # Allow comments about historical bugs only if not in production ifs
            self.assertFalse(
                re.search(rf'if\s*\([^)]*{banned}', src),
                f"site-specific if involving {banned}",
            )


if __name__ == "__main__":
    unittest.main()
