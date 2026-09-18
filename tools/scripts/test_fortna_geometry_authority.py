#!/usr/bin/env python3
"""Permanent geometry authority tests (Gates B–H / G / Y).

1. Fortna geometry survives normalization
2. Relative X/Y preserved
3. Angle preserved
4. Body and hit target same transform
5. Engineer geometry override survives reload
6. P500/P536 require no name-specific code
"""
from __future__ import annotations

import copy
import json
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_geometry_authority import (  # noqa: E402
    DERIVED_TOPOLOGY,
    ENGINEER_ASSIGNED,
    FALLBACK_LAYOUT,
    MISMATCH,
    PROVEN_RUN,
    REQUIRED_RENDER_FIELDS,
    SCHEMA_FIELDS,
    apply_engineer_override,
    count_provenance,
    display_transform,
    has_usable_run_xy,
    normalize_system,
    relative_deltas,
    resolve_object_geometry,
    resolve_rows,
    validate_topology_geometry,
)
from fortna_physical_geometry import build_equipment_geometry  # noqa: E402

RUN_CONV = ROOT / "workspace" / "_plc2_run_peek" / "RUN" / "FORTNA" / "Conveyor.asc"
TB = ROOT / "dashboard" / "transport-build.js"
PASS2 = ROOT / "dashboard" / "transport-build-pass2.js"
AUTH_PY = SCRIPTS / "fortna_geometry_authority.py"


def _approx(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= eps


def _load_rows(*tags: str) -> dict[str, dict]:
    if not RUN_CONV.is_file():
        raise unittest.SkipTest(f"missing {RUN_CONV}")
    _hdr, rows = read_asc(RUN_CONV)
    by = {str(r.get("IO_Name") or "").strip().upper(): r for r in rows}
    out = {}
    for t in tags:
        if t.upper() not in by:
            raise unittest.SkipTest(f"missing conveyor {t}")
        out[t.upper()] = by[t.upper()]
    return out


class TestFortnaGeometryAuthority(unittest.TestCase):
    def test_schema_spelling_x_cord_not_x_coord(self) -> None:
        self.assertIn("X_cord", SCHEMA_FIELDS)
        self.assertIn("Y_cord", SCHEMA_FIELDS)
        self.assertNotIn("X_coord", SCHEMA_FIELDS)
        self.assertNotIn("Y_coord", SCHEMA_FIELDS)
        src = AUTH_PY.read_text(encoding="utf-8")
        # Authority module must document X_cord spelling; must not prefer X_coord
        self.assertIn("X_cord", src)
        self.assertIn("NOT X_coord", src)

    def test_proven_beats_fallback(self) -> None:
        row = {
            "IO_Name": "P312",
            "X_cord": 64950,
            "Y_cord": 85700,
            "Angle": 90,
            "Length": 3000,
            "Width": 200,
            "Type": "ZEROPRESSURE",
        }
        fallback = {"x": 0, "y": 0, "angle": 0, "length": 100}
        rec = resolve_object_geometry(row, fallback=fallback, tag="P312")
        self.assertEqual(rec["geometry_provenance"], PROVEN_RUN)
        self.assertAlmostEqual(rec["entry_endpoint"]["x"], 64950, places=3)
        self.assertAlmostEqual(rec["entry_endpoint"]["y"], 85700, places=3)
        # source untouched even if we later add override
        src_xy = rec["source_geometry"]["fields"]["X_cord"]
        self.assertAlmostEqual(src_xy, 64950, places=3)

    def test_fallback_only_when_no_proven(self) -> None:
        row = {"IO_Name": "PX", "Type": "STRAIGHT"}  # no XY
        fallback = {"x": 10, "y": 20, "angle": 0, "length": 100, "width": 50}
        rec = resolve_object_geometry(row, fallback=fallback, tag="PX")
        self.assertEqual(rec["geometry_provenance"], FALLBACK_LAYOUT)
        self.assertAlmostEqual(rec["entry_endpoint"]["x"], 10)

    def test_engineer_override_does_not_mutate_source(self) -> None:
        row = {
            "IO_Name": "P314",
            "X_cord": 64950,
            "Y_cord": 88700,
            "Angle": 90,
            "Length": 2500,
            "Width": 200,
            "Type": "BELT",
        }
        base = resolve_object_geometry(row, tag="P314")
        src_before = copy.deepcopy(base["source_geometry"])
        overridden = apply_engineer_override(
            base,
            {
                "X_cord": 100,
                "Y_cord": 200,
                "Angle": 0,
                "Length": 500,
                "Width": 200,
                "Type": "STRAIGHT",
            },
        )
        self.assertEqual(overridden["geometry_provenance"], ENGINEER_ASSIGNED)
        self.assertEqual(overridden["source_geometry"], src_before)
        self.assertFalse(overridden["override_provenance"]["source_geometry_mutated"])
        self.assertAlmostEqual(overridden["entry_endpoint"]["x"], 100)
        self.assertAlmostEqual(overridden["source_geometry"]["fields"]["X_cord"], 64950)

    def test_engineer_override_survives_reload(self) -> None:
        """Serialize override + source, reload, effective still engineer, source intact."""
        row = {
            "IO_Name": "P100",
            "X_cord": 1000,
            "Y_cord": 2000,
            "Angle": 0,
            "Length": 1500,
            "Width": 200,
            "Type": "STRAIGHT",
        }
        rec = resolve_object_geometry(
            row,
            engineer_override={
                "X_cord": 1111,
                "Y_cord": 2222,
                "Angle": 90,
                "Length": 800,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            tag="P100",
        )
        blob = json.dumps(rec)
        loaded = json.loads(blob)
        # "reload" = re-resolve from stored source + stored override
        restored = resolve_object_geometry(
            {
                "IO_Name": "P100",
                **loaded["source_geometry"]["fields"],
            },
            engineer_override={
                "X_cord": 1111,
                "Y_cord": 2222,
                "Angle": 90,
                "Length": 800,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            tag="P100",
        )
        self.assertEqual(restored["geometry_provenance"], ENGINEER_ASSIGNED)
        self.assertAlmostEqual(restored["entry_endpoint"]["x"], 1111)
        self.assertAlmostEqual(restored["source_geometry"]["fields"]["X_cord"], 1000)
        self.assertAlmostEqual(restored["angle"], 90)

    def test_normalization_preserves_relative_xy_and_angle(self) -> None:
        rows = [
            {
                "IO_Name": "A",
                "X_cord": 0,
                "Y_cord": 0,
                "Angle": 90,
                "Length": 1000,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            {
                "IO_Name": "B",
                "X_cord": 0,
                "Y_cord": 1000,
                "Angle": 90,
                "Length": 500,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            {
                "IO_Name": "C",
                "X_cord": 500,
                "Y_cord": 1000,
                "Angle": 0,
                "Length": 800,
                "Width": 200,
                "Type": "STRAIGHT",
            },
        ]
        recs = resolve_rows(rows)
        before = relative_deltas(recs, use_source=True)
        # angles before
        angles_before = {r["tag"]: r["angle"] for r in recs}
        normed = normalize_system(recs, scale=0.045, translate=(120.0, 120.0), flip_y=False)
        after = relative_deltas(normed, use_source=False)
        # Relative ratios preserved under uniform scale
        for tag in before:
            bx, by = before[tag]["dx"], before[tag]["dy"]
            ax, ay = after[tag]["dx"], after[tag]["dy"]
            self.assertTrue(_approx(ax, bx * 0.045, 1e-4), f"{tag} dx")
            self.assertTrue(_approx(ay, by * 0.045, 1e-4), f"{tag} dy")
        for r in normed:
            self.assertTrue(_approx(r["angle"], angles_before[r["tag"]], 1e-6))
            self.assertFalse(r["normalization"]["source_geometry_mutated"])
            # source geometry absolute values unchanged
            src = r["source_geometry"]["fields"]
            orig = next(x for x in rows if x["IO_Name"] == r["tag"])
            self.assertAlmostEqual(src["X_cord"], float(orig["X_cord"]))
            self.assertAlmostEqual(src["Angle"], float(orig["Angle"]))

    def test_body_and_hit_target_same_transform(self) -> None:
        row = {
            "IO_Name": "P312",
            "X_cord": 64950,
            "Y_cord": 85700,
            "Angle": 90,
            "Length": 3000,
            "Width": 200,
            "Type": "ZEROPRESSURE",
        }
        rec = resolve_object_geometry(row, tag="P312")
        xf = display_transform(rec, offset={"dx": 40, "dy": -10})
        self.assertTrue(xf["same_transform"])
        self.assertEqual(xf["body"]["center"], xf["hit_target"]["center"])
        self.assertEqual(xf["body"]["entry"], xf["hit_target"]["entry"])
        self.assertEqual(xf["body"]["exit"], xf["hit_target"]["exit"])
        self.assertEqual(xf["body"]["center"], xf["context_menu_target"]["center"])
        self.assertEqual(xf["selection"]["center"], xf["hover"]["center"])
        # move/rotate/normalize then still same
        moved = normalize_system([rec], scale=2.0, translate=(5, 7))
        xf2 = display_transform(moved[0], offset={"dx": 1, "dy": 2})
        self.assertEqual(xf2["body"]["center"], xf2["hit_target"]["center"])
        self.assertEqual(xf2["body"]["center"], xf2["context_menu_target"]["center"])

    def test_required_render_fields_present(self) -> None:
        row = {
            "IO_Name": "P312",
            "X_cord": 64950,
            "Y_cord": 85700,
            "Angle": 90,
            "Length": 3000,
            "Width": 200,
            "Type": "ZEROPRESSURE",
        }
        rec = resolve_object_geometry(row, tag="P312")
        for f in REQUIRED_RENDER_FIELDS:
            self.assertIn(f, rec)
            self.assertIsNotNone(rec[f], f)

    def test_topology_mismatch_flagged_not_snapped(self) -> None:
        a = resolve_object_geometry(
            {
                "IO_Name": "A",
                "X_cord": 0,
                "Y_cord": 0,
                "Angle": 0,
                "Length": 100,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            tag="A",
        )
        b = resolve_object_geometry(
            {
                "IO_Name": "B",
                "X_cord": 5000,
                "Y_cord": 5000,
                "Angle": 0,
                "Length": 100,
                "Width": 200,
                "Type": "STRAIGHT",
            },
            tag="B",
        )
        flags = validate_topology_geometry([a, b], [{"from": "A", "to": "B", "kind": "mtrchain"}])
        self.assertTrue(any(f["code"] == MISMATCH for f in flags))
        self.assertTrue(all(f.get("snapped") is False for f in flags))
        # endpoints unchanged
        self.assertAlmostEqual(a["exit_endpoint"]["x"], 100)
        self.assertAlmostEqual(b["entry_endpoint"]["x"], 5000)

    def test_p500_p536_no_name_specific_production_code(self) -> None:
        """Gate F/Y — acceptance examples only; no if name==P500 production branches."""
        for path in (AUTH_PY, TB, PASS2):
            text = path.read_text(encoding="utf-8", errors="replace")
        # Authority module: no P500/P536 at all
        auth = AUTH_PY.read_text(encoding="utf-8")
        self.assertNotIn("P500", auth)
        self.assertNotIn("P536", auth)
        # transport-build: only inside geometryDiagnosticSiteNotes (report-only)
        js = TB.read_text(encoding="utf-8")
        # No production if name == "P500"
        self.assertIsNone(re.search(r'if\s*\([^)]*name\s*===\s*["\']P500["\']', js))
        self.assertIsNone(re.search(r'if\s*\([^)]*name\s*===\s*["\']P536["\']', js))
        self.assertIsNone(re.search(r'if\s*\([^)]*==\s*["\']P500["\']', js.split("geometryDiagnosticSiteNotes")[0]))
        # drawSchematic must not branch on these tags
        draw_start = js.index("function drawSchematic")
        draw_end = js.find("\n  function ", draw_start + len("function drawSchematic"))
        draw = js[draw_start:draw_end if draw_end > 0 else draw_start + 8000]
        self.assertNotIn("P500", draw)
        self.assertNotIn("P536", draw)
        # Auto-layout guard must not special-case tags
        p2 = PASS2.read_text(encoding="utf-8")
        layout_fn = p2[p2.index("function autoLayoutNodes") : p2.index("function autoLayoutArea")]
        self.assertNotIn("P500", layout_fn)
        self.assertNotIn("P536", layout_fn)

    def test_p500_p536_resolve_as_proven_run(self) -> None:
        rows = _load_rows("P500", "P536")
        for tag, row in rows.items():
            self.assertTrue(has_usable_run_xy(row), tag)
            rec = resolve_object_geometry(row, tag=tag)
            self.assertEqual(rec["geometry_provenance"], PROVEN_RUN, tag)
            self.assertIsNotNone(rec["entry_endpoint"])
            self.assertIsNotNone(rec["exit_endpoint"])
            self.assertIsNotNone(rec["body_center"])
            g = build_equipment_geometry(row)
            self.assertTrue(_approx(rec["entry_endpoint"]["x"], g["entry"]["x"], 1e-3))
            self.assertTrue(_approx(rec["angle"], float(str(row["Angle"]).strip()), 1e-6))

    def test_ui_hooks_present(self) -> None:
        js = TB.read_text(encoding="utf-8")
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function getDisplayTransform", js)
        self.assertIn("function applyEngineerGeometryOverride", js)
        self.assertIn("function mayApplyFallbackLayout", js)
        self.assertIn("function fitSystem", js)
        self.assertIn("function centerSelected", js)
        self.assertIn("function homeView", js)
        self.assertIn("function setGeometryAuthorityMode", js)
        self.assertIn("geometryAuthorityMode", js)
        self.assertIn('id="tb-geometry-mode"', html)
        self.assertIn('id="tb-fit-system"', html)
        self.assertIn('id="tb-home"', html)
        self.assertIn("Fit System", html)
        self.assertIn("RUN / Physical", html)

    def test_site_specific_branch_count_zero_in_authority(self) -> None:
        auth = AUTH_PY.read_text(encoding="utf-8")
        # Count production-style name equality branches — must be 0
        branches = re.findall(r'if\s+.*(?:name|tag|IO_Name).*(?:P500|P536)', auth)
        self.assertEqual(len(branches), 0)


class TestProvenCountsMeasurable(unittest.TestCase):
    def test_count_provenance(self) -> None:
        recs = [
            {"geometry_provenance": PROVEN_RUN},
            {"geometry_provenance": PROVEN_RUN},
            {"geometry_provenance": FALLBACK_LAYOUT},
            {"geometry_provenance": ENGINEER_ASSIGNED},
            {"geometry_provenance": DERIVED_TOPOLOGY},
        ]
        c = count_provenance(recs)
        self.assertEqual(c[PROVEN_RUN], 2)
        self.assertEqual(c[FALLBACK_LAYOUT], 1)
        self.assertEqual(c[ENGINEER_ASSIGNED], 1)
        self.assertEqual(c[DERIVED_TOPOLOGY], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
