#!/usr/bin/env python3
"""Transport performance budget — MSCRENOPICK-scale projects must stay interactive.

This is a structural fixture: node-index Map + coalesced redraw contract.
Browser timings are recorded by dashboard/transport-build.js perfRecord().
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
TB = ROOT / "dashboard" / "transport-build.js"


class TestTransportPerfContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = TB.read_text(encoding="utf-8")

    def test_raf_coalesced_schematic_redraw(self) -> None:
        self.assertIn("scheduleDrawSchematic", self.src)
        self.assertIn("requestAnimationFrame", self.src)
        self.assertIn("drawSchematicNow", self.src)
        # Drag path must not call drawSchematicNow synchronously
        # (mousemove uses scheduleDrawSchematic)
        self.assertIn("scheduleDrawSchematic(area)", self.src)

    def test_node_index_map_not_nested_find(self) -> None:
        self.assertIn("function nodeIndex(area)", self.src)
        self.assertIn("byId.get(tb.moving.id)", self.src)
        self.assertIn("byId.get(o.id)", self.src)

    def test_no_localstorage_during_drag_comment(self) -> None:
        self.assertIn("Never persist localStorage during drag", self.src)

    def test_perf_instrumentation_present(self) -> None:
        self.assertIn("perfRecord('transport.drawSchematic'", self.src)
        self.assertIn("perfRecord('transport.drawWires'", self.src)
        self.assertIn("perfSnapshot", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
