#!/usr/bin/env python3
"""Safety UI breathing room + AENT readability — Gates F/G/H/I source contracts."""
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


import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "dashboard" / "index.html"
SAFETY = ROOT / "dashboard" / "safety-build.js"
FLEX_CSS = ROOT / "dashboard" / "hardware" / "flex-hardware.css"
FLEX_JS = ROOT / "dashboard" / "hardware" / "flex-rack.js"


class TestSafetyUiBreathingRoom(unittest.TestCase):
    def test_inventory_in_document_scroll_layout(self) -> None:
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn('id="sb-zone-summary"', html)
        self.assertIn('id="sb-inventory"', html)
        # Field stabilization: inventory is part of primary document scroll
        # (not locked in a tiny nested max-h pane / not hidden).
        inv = html[html.index('id="sb-inventory"') : html.index('id="sb-inventory"') + 220]
        self.assertNotIn("max-h-[34vh]", inv)
        self.assertNotRegex(inv, r'\bhidden\b')

    def test_assign_devices_natural_growth(self) -> None:
        js = SAFETY.read_text(encoding="utf-8", errors="replace")
        self.assertIn("min-h-[18rem]", js)
        self.assertIn("Required zone roles", js)
        self.assertIn("function renderZoneSummary", js)
        self.assertIn("Selected zone", js)
        self.assertIn("SAFETY APPLIED", js)

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
