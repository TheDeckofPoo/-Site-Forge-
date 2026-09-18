#!/usr/bin/env python3
"""Safety UI breathing room + AENT readability — Gates F/G/H/I source contracts."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "dashboard" / "index.html"
SAFETY = ROOT / "dashboard" / "safety-build.js"
FLEX_CSS = ROOT / "dashboard" / "hardware" / "flex-hardware.css"
FLEX_JS = ROOT / "dashboard" / "hardware" / "flex-rack.js"


class TestSafetyUiBreathingRoom(unittest.TestCase):
    def test_inventory_not_primary_layout(self) -> None:
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn('id="sb-zone-summary"', html)
        self.assertIn('id="sb-inventory"', html)
        # Inventory host is hidden from primary layout
        self.assertRegex(html, r'id="sb-inventory"[^>]*class="[^"]*hidden')

    def test_assign_devices_generous_viewport(self) -> None:
        js = SAFETY.read_text(encoding="utf-8", errors="replace")
        self.assertIn("min-h-[22rem]", js)
        self.assertIn("max-h-[55vh]", js)
        self.assertIn("function renderZoneSummary", js)
        self.assertIn("Selected zone", js)

    def test_aent_breathing_room_preserves_flex_io_width(self) -> None:
        css = FLEX_CSS.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(css, r"\.flex-io\s*\{[^}]*width:\s*84px")
        self.assertRegex(css, r"\.flex-adapter\s*\{[^}]*width:\s*100px")
        self.assertIn("line-height: 1.3", css)
        js = FLEX_JS.read_text(encoding="utf-8", errors="replace")
        face = js[js.index("function renderAdapterFace") : js.index("function renderIoFace")]
        self.assertNotIn('class="flex-port', face)


if __name__ == "__main__":
    unittest.main(verbosity=2)
