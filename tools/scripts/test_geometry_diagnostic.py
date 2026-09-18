#!/usr/bin/env python3
"""Gate K — transport geometry diagnostic artifact field contracts.

Diagnostic is report/inspector only — must not alter production layout code paths
with site-specific production ifs (P500/P536 notes are report-only).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TB = ROOT / "dashboard" / "transport-build.js"
INDEX = ROOT / "dashboard" / "index.html"
PASS2 = ROOT / "dashboard" / "transport-build-pass2.js"

REQUIRED_RUN_FIELDS = (
    "X",
    "Y",
    "Length",
    "Width",
    "Angle",
    "Type",
    "Inside_Radius",
)

REQUIRED_TOP_FIELDS = (
    "run",
    "rendered",
    "hitbox",
    "upstream",
    "downstream",
    "provenance",
)


class TestGeometryDiagnostic(unittest.TestCase):
    def test_ui_toggle_and_export_present(self) -> None:
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn('id="tb-advanced-debug"', html)
        self.assertIn("Geometry debug view", html)
        self.assertIn('id="tb-export-geom-diag"', html)
        self.assertIn('id="tb-insp-geom-diag"', html)
        self.assertIn('id="tb-insp-geom-diag-body"', html)

    def test_builder_emits_required_fields(self) -> None:
        js = TB.read_text(encoding="utf-8", errors="replace")
        self.assertIn("function buildGeometryDiagnostic", js)
        self.assertIn("function exportGeometryDiagnostic", js)
        self.assertIn("TransportGeometryDiagnostic", js)
        for f in REQUIRED_TOP_FIELDS:
            self.assertIn(f, js)
        for f in REQUIRED_RUN_FIELDS:
            self.assertIn(f, js)
        self.assertIn("schematic_hit_width_px", js)
        self.assertIn("entry", js)
        self.assertIn("exit", js)
        self.assertIn("centers", js)
        self.assertIn("anchors", js)

    def test_p500_p536_report_only_not_production_layout(self) -> None:
        js = TB.read_text(encoding="utf-8", errors="replace")
        # Site notes helper must exist and declare report-only policy
        self.assertIn("function geometryDiagnosticSiteNotes", js)
        self.assertIn("site_specific_notes_are_report_only", js)
        self.assertIn("production_layout_unchanged", js)
        # P500/P536 may appear in diagnostic notes — not in drawSchematic layout
        draw_start = js.index("function drawSchematic")
        # Slice until next top-level helper after drawSchematic body starts
        draw_end = js.find("\n  function ", draw_start + len("function drawSchematic"))
        if draw_end < 0:
            draw_end = draw_start + 8000
        draw = js[draw_start:draw_end]
        self.assertNotIn("P500", draw)
        self.assertNotIn("P536", draw)
        notes_fn = js[
            js.index("function geometryDiagnosticSiteNotes") : js.index(
                "async function exportGeometryDiagnostic"
            )
        ]
        self.assertIn("P500", notes_fn)
        self.assertIn("P536", notes_fn)
        self.assertIn("diagnostic", notes_fn)
        self.assertIn("layout not altered", notes_fn)

    def test_export_button_wired(self) -> None:
        p2 = PASS2.read_text(encoding="utf-8", errors="replace")
        self.assertIn("tb-export-geom-diag", p2)
        self.assertIn("exportGeometryDiagnostic", p2)

    def test_synthetic_artifact_shape(self) -> None:
        """Mirror JS diagnostic shape in a pure-Python stand-in for contract checks."""
        diag = {
            "kind": "TransportGeometryDiagnostic",
            "version": 1,
            "node_id": "n1",
            "conveyor_tag": "P100",
            "run": {
                "X": 10.0,
                "Y": 20.0,
                "Length": 100.0,
                "Width": 30.0,
                "Angle": 0.0,
                "Type": "Transport with MS",
                "Inside_Radius": None,
            },
            "rendered": {
                "anchors": {"entry": {"x": 0, "y": 0}, "exit": {"x": 100, "y": 0}},
                "centers": {"x": 50, "y": 0},
                "entry": {"x": 0, "y": 0},
                "exit": {"x": 100, "y": 0},
            },
            "hitbox": {"schematic_hit_width_px": 50},
            "upstream": [],
            "downstream": "P102",
            "provenance": {"geometry": "IMPORTED"},
        }
        for f in REQUIRED_TOP_FIELDS:
            self.assertIn(f, diag)
        for f in REQUIRED_RUN_FIELDS:
            self.assertIn(f, diag["run"])
        # Round-trip JSON (export artifact form)
        blob = json.dumps({"diagnostic": diag}, indent=2)
        loaded = json.loads(blob)
        self.assertEqual(loaded["diagnostic"]["conveyor_tag"], "P100")


if __name__ == "__main__":
    unittest.main(verbosity=2)
