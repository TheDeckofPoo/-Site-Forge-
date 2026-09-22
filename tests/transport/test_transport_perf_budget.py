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

    def test_area_assign_batch_primitive(self) -> None:
        self.assertIn("function moveNodesToArea(ids, destAreaId, opts)", self.src)
        self.assertIn("function moveNodeToArea(nodeId, destAreaId, opts)", self.src)
        # Single-node path must delegate to batch
        slim = self.src.find("function moveNodeToArea(nodeId, destAreaId, opts)")
        self.assertGreater(slim, 0)
        slim_chunk = self.src[slim : slim + 220]
        self.assertIn("moveNodesToArea(", slim_chunk)
        self.assertIn("perfRecord('transport.areaAssign'", self.src)
        self.assertIn("sync_ms", self.src)
        self.assertIn("AREA_ASSIGN_SAVE_MS = 75", self.src)
        self.assertIn("function flushAreaAssignPersist()", self.src)
        self.assertIn("function scheduleAreaAssignPersist()", self.src)
        # Membership change must not unlock presentation layout
        batch = self.src.find("function moveNodesToArea(ids, destAreaId, opts)")
        batch_end = self.src.find("function moveNodeToArea(nodeId, destAreaId, opts)", batch)
        batch_body = self.src[batch:batch_end]
        self.assertIn("invalidateNodeIndex(a)", batch_body)
        self.assertNotIn("forcePresentationRelayout = true", batch_body)
        self.assertNotIn("requestPresentationRelayout", batch_body)


class TestTransportAreaAssignPass2Callers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = (ROOT / "dashboard" / "transport-build-pass2.js").read_text(encoding="utf-8")

    def test_bulk_context_selection_use_batch(self) -> None:
        self.assertIn("moveNodesToArea(ids, destId", self.src)
        self.assertIn("moveNodesToArea(ids, destArea", self.src)
        self.assertIn("moveNodesToArea(ids, dest.id", self.src)
        # No per-id moveNodeToArea loops for bulk/context/selection
        self.assertNotIn("ids.forEach((id) => {\n      if (destId) moveNodeToArea(id, destId);", self.src)
        self.assertNotIn("if (destArea) moveNodeToArea(id, destArea);", self.src)
        self.assertNotIn("ids.forEach((id) => {\n      moveNodeToArea(id, dest.id);", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
