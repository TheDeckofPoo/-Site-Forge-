#!/usr/bin/env python3
"""POINT rack presentation — engineering schematic, not photoreal CAD.

Presentation-only checks against dashboard/hardware/point-rack.js.
Does not touch HardwareIOModel / Autogen semantics.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POINT_JS = ROOT / "dashboard" / "hardware" / "point-rack.js"
POINT_CSS = ROOT / "dashboard" / "hardware" / "point-hardware.css"
FLEX_JS = ROOT / "dashboard" / "hardware" / "flex-rack.js"


class TestPointRackPresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = POINT_JS.read_text(encoding="utf-8")
        cls.css = POINT_CSS.read_text(encoding="utf-8")
        cls.flex = FLEX_JS.read_text(encoding="utf-8")

    def test_no_photoreal_screws_in_renderer(self) -> None:
        self.assertNotIn("screwGrid", self.js)
        self.assertNotIn("point-screw", self.js)
        self.assertNotIn("point-term", self.js)
        self.assertNotIn("point-screws", self.js)

    def test_css_hides_legacy_photoreal(self) -> None:
        self.assertIn(".point-screw", self.css)
        self.assertIn("display: none !important", self.css)
        self.assertIn("min-height: 205px", self.css)
        self.assertIn("width: 108px", self.css)
        self.assertIn("width: 64px", self.css)
        self.assertIn("height: 160px", self.css)

    def test_preserves_data_hw_mod_and_selection(self) -> None:
        self.assertIn("data-hw-mod=", self.js)
        self.assertIn("selected", self.js)
        self.assertIn("moduleKey", self.js)

    def test_channel_resolution_not_live_plc(self) -> None:
        self.assertIn("Engineering-resolution indicators", self.js)
        self.assertIn("NOT live PLC", self.js)

    def test_flex_renderer_untouched_for_screws(self) -> None:
        # FLEX may still have its own visual language; we must not have deleted it
        self.assertIn("flex-adapter", self.flex)
        self.assertIn("renderRacks", self.flex)

    def test_node_render_fixture(self) -> None:
        """Execute PointRack in Node and assert schematic HTML shape."""
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const ctx = { window: {}, globalThis: {}, console };
ctx.global = ctx;
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(src, ctx);
const PR = ctx.PointRack || ctx.window.PointRack;
if (!PR) { console.error('NO_POINTRACK'); process.exit(2); }
const adapter = {
  rio_name: 'AENTR13', eipcfg_name: 'AENTR13', targetip: '10.0.0.1', panel: 'CP1',
  modules: [
    { slot: 0, is_adapter_card: true, catalog: '1734-AENTR', type: '1734-AENTR', channels: [] },
    { slot: 1, catalog: '1734-IB8', type: '1734-IB8', channel_capacity: 8, channels: [
      { fortna_bit: 0, logical_endpoint: { name: 'PE1' } },
      { fortna_bit: 1, owner_state: 'UNRESOLVED_OWNER' },
    ]},
    { slot: 2, catalog: '1734-OA4', type: '1734-OA4', channel_capacity: 4, channels: [] },
    { slot: 3, catalog: '1734-XYZ99', type: '1734-XYZ99', channels: [] },
  ],
};
const html = PR.renderRacks([adapter], { selectedKey: 'AENTR13::1' });
const checks = {
  has_aentr: html.includes('AENTR13'),
  has_1734_aentr: html.includes('1734-AENTR'),
  has_ib8: html.includes('1734-IB8'),
  has_oa4: html.includes('1734-OA4'),
  has_unknown_cat: html.includes('1734-XYZ99'),
  has_point_io: /POINT I\/O/.test(html),
  has_input: html.includes('INPUT'),
  has_output: html.includes('OUTPUT'),
  has_net_mod: html.includes('NET') && html.includes('MOD'),
  has_data_hw_mod: html.includes('data-hw-mod='),
  has_selected: html.includes('selected'),
  no_screw: !html.includes('point-screw') && !html.includes('point-term'),
  slot1: html.includes('SLOT 1'),
  slot2: html.includes('SLOT 2'),
  ch0: html.includes('>0<') || html.includes('>0</span>'),
};
console.log(JSON.stringify({ ok: Object.values(checks).every(Boolean), checks, len: html.length }));
fs.writeFileSync(process.argv[2], html, 'utf8');
"""
        with tempfile.TemporaryDirectory() as td:
            out_html = Path(td) / "point_rack_fixture.html"
            r = subprocess.run(
                ["node", "-e", harness, str(POINT_JS), str(out_html)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
            payload = None
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("{"):
                    import json
                    payload = json.loads(line)
            self.assertIsNotNone(payload)
            self.assertTrue(payload["ok"], payload)
            # Persist artifact for demo report
            art = ROOT / "exports" / "demo" / "point_rack_simplified.html"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text(
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<link rel='stylesheet' href='../../dashboard/hardware/point-hardware.css'>"
                "<style>body{background:#0a0f14;padding:24px;}</style></head><body>"
                + out_html.read_text(encoding="utf-8")
                + "</body></html>",
                encoding="utf-8",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
