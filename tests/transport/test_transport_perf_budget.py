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

    def test_drag_does_not_full_redraw_each_move(self) -> None:
        # Group-drag mousemove must NOT schedule full schematic every sample
        self.assertIn("happens once on mouseup", self.src)
        # After the drag comment, the next scheduleDrawSchematic must not appear
        # before mouseup handler (mouseup still redraws once — that is OK).
        drag = self.src.find("Never persist localStorage during drag")
        self.assertGreater(drag, 0)
        mouseup = self.src.find("window.addEventListener('mouseup'", drag)
        self.assertGreater(mouseup, drag)
        between = self.src[drag:mouseup]
        self.assertNotIn("scheduleDrawSchematic(area)", between)

    def test_zoom_is_transform_only(self) -> None:
        # zoomByFactor must not call render() after applyViewportZoom
        zidx = self.src.find("function zoomByFactor")
        self.assertGreater(zidx, 0)
        chunk = self.src[zidx : zidx + 900]
        self.assertIn("applyViewportZoom()", chunk)
        self.assertNotIn("\n    render();\n", chunk)
        self.assertIn("Transform-only zoom", chunk)

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

    def test_lite_perf_instruments(self) -> None:
        self.assertIn("perfRecord('transport.drawLiteSchematic'", self.src)
        self.assertIn("perfRecord('transport.selectLite'", self.src)
        self.assertIn("perfRecord('transport.dragFrameLite'", self.src)
        self.assertIn("perfRecord('transport.renderScene'", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
