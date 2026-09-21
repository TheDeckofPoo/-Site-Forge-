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
        self.assertIn("showAllLabels", body)
        self.assertIn("tb-lite-label", body)
        # Far-zoom still keeps merge/selected (+ Readable) labels
        self.assertIn("merge || sel", body)

    def test_readable_schematic_display_only(self) -> None:
        self.assertIn("readableSchematic: false", self.src)
        self.assertIn("schematicStyle: 'raw'", self.src)
        self.assertIn("function isReadableSchematic()", self.src)
        self.assertIn("function setReadableSchematic(on)", self.src)
        self.assertIn("function setSchematicStyle(style)", self.src)
        self.assertIn("function computeLiteReadableOffsets", self.src)
        self.assertIn("function liteLabelCollisionPlan", self.src)
        self.assertIn('id="tb-style-raw"', self.html)
        self.assertIn('id="tb-style-readable"', self.html)
        # Offsets must not mutate canonical node.x / node.y in the Lite path
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertIn("dispOff", lite_body)
        self.assertIn("transform=\"translate(", lite_body)
        self.assertNotIn("n.x =", lite_body)
        self.assertNotIn("n.y =", lite_body)
        # Apply path ignores readable flag
        apply = self.src.find("function buildCanonicalApplyGraph")
        nxt = self.src.find("\n  function setWorkflowStep", apply)
        body = self.src[apply:nxt]
        self.assertNotIn("readableSchematic", body)
        self.assertNotIn("computeLiteReadableOffsets", body)

    def test_packed_components_display_only(self) -> None:
        self.assertIn("function isPackedSchematic()", self.src)
        self.assertIn("function computeLitePackedOffsets", self.src)
        self.assertIn("function listLiteTransportComponents", self.src)
        self.assertIn('id="tb-style-packed"', self.html)
        self.assertIn("Packed Components", self.html)
        packed_fn = self.src.find("function computeLitePackedOffsets")
        # Include preceding JSDoc (display-only contract)
        packed_doc = self.src.find("Packed Components", max(0, packed_fn - 400))
        packed_end = self.src.find("\n  function liteLabelCollisionPlan", packed_fn)
        packed_body = self.src[packed_doc:packed_end]
        self.assertIn("Never writes node.x/y", packed_body)
        self.assertNotIn("n.x =", packed_body)
        self.assertNotIn("n.y =", packed_body)
        self.assertNotIn(".provenance", packed_body)
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertIn("computeLitePackedOffsets", lite_body)
        self.assertNotIn("n.x =", lite_body)
        self.assertNotIn("n.y =", lite_body)
        apply = self.src.find("function buildCanonicalApplyGraph")
        nxt = self.src.find("\n  function setWorkflowStep", apply)
        body = self.src[apply:nxt]
        self.assertNotIn("computeLitePackedOffsets", body)
        self.assertNotIn("schematicStyle", body)

    def test_lite_arrow_scale_constant(self) -> None:
        self.assertIn("const LITE_ARROW_SCALE = 0.375", self.src)
        self.assertIn("LITE_ARROW_MARKER_SIZE", self.src)
        m = re.search(r"const LITE_ARROW_SCALE\s*=\s*([0-9.]+)", self.src)
        self.assertIsNotNone(m)
        scale = float(m.group(1))
        self.assertGreaterEqual(scale, 0.35)
        self.assertLessEqual(scale, 0.40)
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertIn("LITE_ARROW_MARKER_SIZE", lite_body)
        self.assertNotIn('markerWidth="7"', lite_body)

    def test_lite_legend_and_tooltip(self) -> None:
        self.assertIn('id="tb-lite-legend"', self.html)
        self.assertIn("tb-leg-conv", self.html)
        self.assertIn("tb-leg-merge", self.html)
        self.assertIn("tb-leg-selected", self.html)
        self.assertIn("tb-leg-review", self.html)
        self.assertIn(".tb-lite-belt.tb-review", self.html)
        lite_fn = self.src.find("function drawLiteSchematicNow")
        lite_end = self.src.find("function drawSchematic(", lite_fn)
        lite_body = self.src[lite_fn:lite_end]
        self.assertIn("kindTitle", lite_body)
        self.assertIn("<title>", lite_body)

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
