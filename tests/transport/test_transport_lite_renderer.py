#!/usr/bin/env python3
"""Transportation Lite Schematic — presentation-only performance contract.

Rendering mode MUST NOT alter canonical Transport / Autogen graph.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TB = ROOT / "dashboard" / "transport-build.js"
PASS2 = ROOT / "dashboard" / "transport-build-pass2.js"
INDEX = ROOT / "dashboard" / "index.html"
SVG_EXPORT = ROOT / "tools" / "scripts" / "fortna_schematic_svg_export.py"


class TestTransportLiteRenderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = TB.read_text(encoding="utf-8")
        cls.pass2 = PASS2.read_text(encoding="utf-8")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.svg_export = SVG_EXPORT.read_text(encoding="utf-8")

    def test_lite_is_default_render_mode(self) -> None:
        self.assertIn("renderMode: 'lite'", self.src)
        self.assertIn("function isLiteRenderMode()", self.src)
        self.assertIn("function setRenderMode(mode)", self.src)
        self.assertIn('id="tb-mode-lite"', self.html)
        self.assertIn('id="tb-mode-detailed"', self.html)

    def test_lite_svg_centerline_structure(self) -> None:
        self.assertIn("function drawLiteSchematicNow", self.src)
        self.assertIn("tb-lite-node", self.src)
        self.assertIn("tb-lite-belt", self.src)
        self.assertIn("tb-lite-hit", self.src)
        self.assertIn("tb-lite-label", self.src)
        self.assertIn("function liteStraightPath", self.src)
        self.assertIn("function liteCurvePath", self.src)
        self.assertIn("marker-end=\"url(#tbArrow)\"", self.src)

    def test_lite_always_shows_p_tags(self) -> None:
        # Fit System used to zoom to ~5% and hide every label — arrows-only is not usable.
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        body = self.src[lite_fn:lite_end]
        self.assertIn("const showLabels = true", body)
        self.assertIn("tb-lite-label", body)

    def test_lite_skips_expensive_algorithms(self) -> None:
        # Lite path must short-circuit before detailed schematic construction
        idx = self.src.find("function drawSchematicNow")
        self.assertGreater(idx, 0)
        chunk = self.src[idx : idx + 500]
        self.assertIn("isLiteRenderMode()", chunk)
        self.assertIn("drawLiteSchematicNow", chunk)
        # Expensive helpers remain in detailed path only (still present in file)
        self.assertIn("falseAbutmentInsets", self.src)
        self.assertIn("placeSchematicLabels", self.src)
        self.assertIn("projectSharedTopologyJoints", self.src)
        # But drawLiteSchematicNow body must not call them
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertNotIn("falseAbutmentInsets(", lite_body)
        self.assertNotIn("placeSchematicLabels(", lite_body)
        self.assertNotIn("annularBeltPathDFromCenterline(", lite_body)
        self.assertNotIn("projectSharedTopologyJoints(", lite_body)

    def test_native_hit_testing_not_scan_on_hover(self) -> None:
        self.assertIn("function nodeIdFromLiteEvent", self.src)
        self.assertIn("updateLiteHover", self.src)
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertIn("nodeIdFromLiteEvent", lite_body)
        self.assertNotIn("pickSchematicNodeAt(", lite_body)

    def test_select_does_not_full_render_in_lite(self) -> None:
        self.assertIn("function selectLiteNode", self.src)
        sel = self.src.find("function selectLiteNode")
        chunk = self.src[sel : sel + 1200]
        self.assertIn("renderInspector()", chunk)
        self.assertNotIn("renderScene()", chunk)
        self.assertNotIn("\n    render();\n", chunk)
        # selectNode delegates to lite
        sn = self.src.find("function selectNode")
        sn_chunk = self.src[sn : sn + 400]
        self.assertIn("isLiteRenderMode()", sn_chunk)
        self.assertIn("selectLiteNode", sn_chunk)

    def test_lite_drag_is_transform_then_commit(self) -> None:
        self.assertIn("translate(${ddx} ${ddy})", self.src)
        self.assertIn("transport.dragFrameLite", self.src)
        self.assertIn("transport.dragCommitLite", self.src)
        self.assertIn("presentationOnly: true", self.src)

    def test_relationships_off_by_default(self) -> None:
        self.assertIn("showRelationships: false", self.src)
        self.assertIn("relationships: false", self.src)
        self.assertIn("function setShowRelationships", self.src)
        self.assertIn("relationships_off", self.src)

    def test_decoupled_panel_renderers(self) -> None:
        self.assertIn("function renderScene()", self.src)
        self.assertIn("function renderInspector()", self.src)
        self.assertIn("function renderTopologyPanel()", self.src)
        self.assertIn("function renderInventoryPanel()", self.src)
        self.assertIn("function renderValidationPanel()", self.src)
        # Full render must not always paint topology in lite
        r = self.src.find("function render()")
        chunk = self.src[r : r + 900]
        self.assertIn("if (!isLiteRenderMode())", chunk)
        self.assertIn("renderTopologyPanel()", chunk)

    def test_lazy_topology_dropdowns(self) -> None:
        self.assertIn("data-topo-ds-edit", self.src)
        self.assertIn("Lazy editors", self.src)
        # Default row is a button, not a select with every option
        self.assertIn("tb-topo-ds-btn", self.src)

    def test_validation_event_driven(self) -> None:
        self.assertIn("function markValidationDirty", self.src)
        self.assertIn("function getValidationCached", self.src)
        self.assertIn("validationDirty: true", self.src)

    def test_geometry_and_model_caches(self) -> None:
        self.assertIn("_liteGeomCache", self.src)
        self.assertIn("function liteCachedPath", self.src)
        self.assertIn("function invalidateLiteGeom", self.src)
        self.assertIn("function transportModelCacheKey", self.src)
        self.assertIn("function clearTransportModelCache", self.src)
        self.assertIn("Erased Means Erased", self.src)

    def test_canonical_apply_ignores_render_mode(self) -> None:
        """buildCanonicalApplyGraph must not read tb.renderMode."""
        idx = self.src.find("function buildCanonicalApplyGraph")
        self.assertGreater(idx, 0)
        # Until next major function
        nxt = self.src.find("\n  function setWorkflowStep", idx)
        body = self.src[idx:nxt]
        self.assertNotIn("renderMode", body)
        self.assertNotIn("isLiteRenderMode", body)
        self.assertNotIn("drawLite", body)
        # Hash also presentation-free
        hidx = self.src.find("function canonicalTransportHash")
        hbody = self.src[hidx : self.src.find("\n  function currentProjectIdentity", hidx)]
        self.assertNotIn("renderMode", hbody)
        self.assertIn("Excludes presentation", hbody)

    def test_pass2_lite_contextmenu_uses_native_hit(self) -> None:
        self.assertIn("nodeIdFromLiteEvent", self.pass2)
        self.assertIn("isLiteRenderMode", self.pass2)

    def test_svg_export_supports_lite_mode(self) -> None:
        self.assertIn('mode: str = "detailed"', self.svg_export)
        self.assertIn("def _lite_path_d", self.svg_export)
        self.assertIn("tb-lite-node", self.svg_export)

    def test_perf_export_helpers_present(self) -> None:
        self.assertIn("function buildPerfReport", self.src)
        self.assertIn("function writeTransportGuiPerf", self.src)
        self.assertIn("transport_gui_perf.json", self.src)


class TestTransportLiteCanonicalParityStatic(unittest.TestCase):
    """Static proof that compiler path cannot branch on Lite vs Detailed."""

    def test_no_render_mode_in_apply_path(self) -> None:
        src = TB.read_text(encoding="utf-8")
        # Apply entry uses buildCanonicalApplyGraph — ensure no mode gate nearby
        apply = src.find("async function applyMergesToAutogenUi")
        self.assertGreater(apply, 0)
        chunk = src[apply : apply + 2500]
        self.assertIn("buildCanonicalApplyGraph", chunk)
        self.assertNotIn("renderMode", chunk)
        self.assertNotIn("isLiteRenderMode", chunk)


if __name__ == "__main__":
    unittest.main(verbosity=2)
