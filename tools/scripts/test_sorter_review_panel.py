#!/usr/bin/env python3
"""Sorter Review Required panel — Gates G + I–N + X permanent contracts.

Asserts panel presence, status categories, resolution types, lifecycle,
persistence fingerprints, OPTIONAL isolation, and bulk divert provenance.
Uses model-driven field authority — no site-specific production hardcodes.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "dashboard" / "index.html"
PLUS = ROOT / "dashboard" / "fortna-plus.js"
LIFECYCLE_JSON = ROOT / "exports" / "stabilization" / "sorter_review_lifecycle.json"
QUALITY_JSON = ROOT / "exports" / "stabilization" / "sorter_phase1_quality.json"
SCRIPTS = ROOT / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_review_lifecycle import (  # noqa: E402
    RESOLUTION_TYPES,
    STATUS_CATS,
    accept_item,
    bulk_accept_derived_divert_pe,
    bulk_apply_value,
    collect_optional_items,
    collect_review_items,
    evidence_fingerprint,
    filter_active_items,
    merge_resolutions_preserving,
    status_counts,
    tracking_offset_item,
)

STATUS_CATS_TUPLE = STATUS_CATS


class TestSorterReviewPanel(unittest.TestCase):
    def test_panel_present_in_html(self) -> None:
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn('id="sorter-review-required"', html)
        self.assertIn("Sorter Review Required", html)
        self.assertIn('id="sorter-review-groups"', html)
        self.assertIn('id="sorter-review-status-counts"', html)
        self.assertIn('id="sorter-review-complete"', html)
        self.assertIn("SORTER REVIEW COMPLETE", html)
        self.assertIn('id="sorter-review-reviewed"', html)
        self.assertIn('id="sorter-tracking-offset"', html)
        self.assertIn('id="sorter-divert-bulk"', html)
        self.assertIn("OPTIONAL", html)
        self.assertIn("never mixed", html.lower())

    def test_status_categories_in_js(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("SORTER_STATUS_CATS", js)
        self.assertIn("SORTER_RESOLUTION_TYPES", js)
        self.assertIn("collectSorterReviewItems", js)
        self.assertIn("renderSorterReviewPanel", js)
        self.assertIn("collectSorterOptionalItems", js)
        self.assertIn("filterSorterReviewActiveResolved", js)
        self.assertIn("acceptSorterReviewItem", js)
        for cat in STATUS_CATS_TUPLE:
            self.assertIn(cat, js)
        for r in RESOLUTION_TYPES:
            self.assertIn(r, js)

    def test_optional_not_mixed_into_review(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        # Guard: OPTIONAL must be filtered out of actionable review push path
        self.assertIn("Never mix OPTIONAL into the review actionable list", js)
        self.assertRegex(
            js,
            re.compile(
                r"st === SORTER_STATUS_CATS\.OPTIONAL.*?return;",
                re.S,
            ),
        )

    def test_groups_sorter_tracking_divert(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("_sorterReviewGroup", js)
        self.assertIn("'divert'", js)
        self.assertIn("'tracking'", js)
        self.assertIn("'sorter'", js)
        self.assertIn("focusSorterReviewField", js)
        self.assertIn("SORTER_FIELD_FOCUS", js)
        # Gate L — previously missing tracking_offset
        self.assertIn("tracking_offset:", js)
        self.assertIn("global_track_offset:", js)
        self.assertIn("divert_pe:", js)
        self.assertIn("sorter-tracking-offset", js)

    def test_no_site_specific_production_ifs(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        collector = js[
            js.index("function collectSorterReviewItems") : js.index(
                "function collectSorterOptionalItems"
            )
        ]
        for banned in ("ORNCCP", "P504", "P506", "ENC504", "SHIP_SORTER"):
            self.assertNotIn(banned, collector)

    # ----- Permanent tests 7–11 -----

    def test_07_resolved_sorter_review_disappears(self) -> None:
        """Gate J — Resolved Sorter review disappears from active list immediately."""
        cfg = {
            "sorter_type": "shoe_sorter",
            "area_name": "Ship",
            "field_authority": {
                "tracking_offset": "REVIEW_REQUIRED",
                "divert_pe": "REVIEW_REQUIRED",
                "divert_output_io": "PROVEN",
            },
            "configuration_required": [],
            "divert_rows": [
                {
                    "name": "L1",
                    "lane": "L1",
                    "divert_output_io": "DO1",
                    "divert_pe": "",
                    "authority": {
                        "divert_output_io": "PROVEN",
                        "divert_pe": "REVIEW_REQUIRED",
                    },
                }
            ],
        }
        items = collect_review_items(cfg)
        self.assertTrue(any(i["field"] == "tracking_offset" for i in items))
        off = next(i for i in items if i["field"] == "tracking_offset")
        resolutions: dict = {}
        accept_item(resolutions, off, resolution="ACCEPTED", final_value="")
        active, resolved = filter_active_items(items, resolutions)
        self.assertNotIn("tracking_offset", [i["field"] for i in active])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["lifecycle"], "RESOLVED")
        # JS lifecycle wiring
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("PENDING_REVIEW", js)
        self.assertIn("filterSorterReviewActiveResolved", js)
        self.assertIn("Reviewed ✓", js)

    def test_08_review_acceptance_persists(self) -> None:
        """Gate X — Review acceptance persists across rebuild when fingerprint unchanged."""
        cfg = {
            "sorter_type": "shoe_sorter",
            "area_name": "A",
            "field_authority": {"tracking_offset": "REVIEW_REQUIRED"},
            "configuration_required": [],
            "divert_rows": [],
        }
        items = collect_review_items(cfg)
        off = next(i for i in items if i["field"] == "tracking_offset")
        resolutions: dict = {}
        accept_item(resolutions, off)
        # Simulate Auto Build regenerating identical derived evidence
        items2 = collect_review_items(cfg)
        merged = merge_resolutions_preserving(resolutions, items2)
        active, resolved = filter_active_items(items2, merged)
        self.assertEqual(len(resolved), 1)
        self.assertNotIn("tracking_offset", [i["field"] for i in active])
        # Fingerprint change invalidates
        cfg2 = dict(cfg)
        cfg2["tracking_offset"] = "123"
        cfg2["field_authority"] = {"tracking_offset": "DERIVED"}
        items3 = collect_review_items(cfg2)
        merged2 = merge_resolutions_preserving(resolutions, items3)
        active3, _ = filter_active_items(items3, merged2)
        # DERIVED with value may reappear as ACCEPT_DERIVED (different fingerprint)
        self.assertTrue(
            any(i["field"] == "tracking_offset" for i in active3)
            or not any(i["field"] == "tracking_offset" for i in items3)
        )
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("review_resolutions", js)
        self.assertIn("evidence_fingerprint", js)
        self.assertIn("ENGINEER_ACCEPTED", js)

    def test_09_review_item_always_actionable_or_unresolved_reason(self) -> None:
        """Gate I — every active item has resolution type or explicit unresolved reason."""
        cfg = {
            "sorter_type": "",
            "area_name": "",
            "field_authority": {
                "sorter_type": "REVIEW_REQUIRED",
                "transport_area": "UNKNOWN",
                "tracking_offset": "REVIEW_REQUIRED",
                "divert_pe": "REVIEW_REQUIRED",
                "mystery": "REVIEW_REQUIRED",
            },
            "configuration_required": ["sorter_type", "transport_area"],
            "divert_rows": [
                {
                    "name": "X",
                    "authority": {"divert_pe": "REVIEW_REQUIRED", "divert_output_io": "PROVEN"},
                    "divert_pe": "",
                    "divert_output_io": "Q0",
                }
            ],
        }
        items = collect_review_items(cfg)
        self.assertTrue(items)
        for it in items:
            self.assertIn(it.get("resolution_type"), RESOLUTION_TYPES)
            if it["resolution_type"] == "UNRESOLVED":
                self.assertTrue(str(it.get("why") or "").strip())
            else:
                self.assertTrue(str(it.get("resolution_type") or "").strip())
        # tracking_offset specifically
        off = tracking_offset_item(cfg)
        self.assertIsNotNone(off)
        assert off is not None
        self.assertIn(off["resolution_type"], ("COMMISSIONING_CONFIRM", "EDIT_REQUIRED", "UNRESOLVED"))
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("SORTER_RESOLUTION_TYPES", js)
        self.assertIn("_sorterReviewActionButtons", js)

    def test_10_optional_never_appears_as_active_review_required(self) -> None:
        """Gate I — OPTIONAL never appears as active REVIEW REQUIRED."""
        cfg = {
            "sorter_type": "shoe_sorter",
            "area_name": "A",
            "field_authority": {
                "divert_confirm_pe": "OPTIONAL",
                "something_optional": "OPTIONAL",
                "tracking_offset": "REVIEW_REQUIRED",
                "trig_window": "PROVEN",
                "induct_conveyor": "DERIVED",
            },
            "induct_conveyor": "P1",
            "induct_authority": {"conveyor": "DERIVED"},
            "configuration_required": [],
            "divert_rows": [],
        }
        items = collect_review_items(cfg)
        optional = collect_optional_items(cfg)
        self.assertTrue(any(o["status"] == "OPTIONAL" for o in optional))
        for it in items:
            self.assertNotEqual(it["status"], "OPTIONAL")
            self.assertNotEqual(it.get("resolution_type"), "OPTIONAL")
            self.assertNotIn(it["field"], ("divert_confirm_pe", "something_optional"))
        # field_authority PROVEN/DERIVED alone must not force review
        self.assertNotIn("trig_window", [i["field"] for i in items])
        self.assertNotIn("induct_conveyor", [i["field"] for i in items])

    def test_11_bulk_divert_acceptance_preserves_provenance(self) -> None:
        """Gate N — bulk divert acceptance preserves provenance; never UNKNOWN→PROVEN."""
        rows = [
            {
                "name": "A",
                "divert_pe": "PE_A",
                "authority": {"divert_pe": "DERIVED"},
            },
            {
                "name": "B",
                "divert_pe": "",
                "authority": {"divert_pe": "UNKNOWN"},
            },
            {
                "name": "C",
                "divert_pe": "PE_C",
                "authority": {"divert_pe": "PROVEN"},
            },
            {
                "name": "D",
                "divert_pe": "",
                "authority": {"divert_pe": "REVIEW_REQUIRED"},
            },
        ]
        updated = bulk_accept_derived_divert_pe(rows)
        self.assertEqual(updated[0]["authority"]["divert_pe"], "DERIVED")
        self.assertEqual(updated[0]["authority"]["divert_pe_acceptance"], "ENGINEER_ACCEPTED")
        self.assertEqual(updated[1]["authority"]["divert_pe"], "UNKNOWN")
        self.assertNotEqual(updated[1]["authority"]["divert_pe"], "PROVEN")
        self.assertEqual(updated[2]["authority"]["divert_pe"], "PROVEN")
        applied = bulk_apply_value(rows, [3], "PE_ENG")
        self.assertEqual(applied[3]["divert_pe"], "PE_ENG")
        self.assertEqual(applied[3]["divert_pe_acceptance"], "ENGINEER_ACCEPTED")
        self.assertNotEqual(applied[3]["authority"]["divert_pe"], "PROVEN")
        # Collector must not require approving 32 identical PROVEN divert IO rows
        proven_rows = [
            {
                "name": f"N{i}",
                "divert_output_io": f"DO{i}",
                "divert_pe": f"PE{i}",
                "authority": {"divert_output_io": "PROVEN", "divert_pe": "PROVEN"},
            }
            for i in range(32)
        ]
        cfg = {
            "sorter_type": "shoe_sorter",
            "area_name": "A",
            "field_authority": {
                "divert_output_io": "PROVEN",
                "divert_lane_topology": "PROVEN",
                "divert_pe": "PROVEN",
            },
            "configuration_required": ["divert_output_io"],
            "divert_rows": proven_rows,
        }
        items = collect_review_items(cfg)
        self.assertNotIn("divert_output_io", [i["field"] for i in items])
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Accept All Derived", js)
        self.assertIn("never UNKNOWN→PROVEN", js)
        self.assertIn("ENGINEER_ACCEPTED", js)
        self.assertIn("btn-divert-accept-derived", INDEX.read_text(encoding="utf-8"))
        # GATE 3 — per-row Derived/Proven Accept/Change (empty Select only when no candidate)
        self.assertIn("sorter-divert-pe-accept", js)
        self.assertIn("sorter-divert-pe-change", js)
        self.assertIn("hasCandidate", js)
        self.assertIn("Derived:", js)

    def test_lifecycle_artifact_present(self) -> None:
        self.assertTrue(LIFECYCLE_JSON.is_file())
        data = json.loads(LIFECYCLE_JSON.read_text(encoding="utf-8"))
        self.assertIn("resolution_types", data)
        self.assertIn("lifecycle", data)
        self.assertIn("gate_o_32_vs_16", data)
        self.assertEqual(data["gate_o_32_vs_16"]["phase1_multiplicity"], 32)
        self.assertIn("STRONGLY_SUPPORTED", data["gate_o_32_vs_16"]["finding"])
        self.assertTrue(QUALITY_JSON.is_file())
        q = json.loads(QUALITY_JSON.read_text(encoding="utf-8"))
        # Prefer gate_o_divert_multiplicity (current); legacy key divert_multiplicity_gate_o optional
        gate_o = q.get("gate_o_divert_multiplicity") or q.get("divert_multiplicity_gate_o") or {}
        self.assertIn(
            gate_o.get("relationship") or gate_o.get("classification"),
            ("STRONGLY_SUPPORTED", "UNKNOWN"),
        )
        self.assertEqual(
            gate_o.get("canonical_SrtZoneLane_rows") or gate_o.get("run_SrtZoneLane_rows"),
            32,
        )

    def test_counts_helper(self) -> None:
        active = [
            {"status": "REVIEW_REQUIRED"},
            {"status": "ENGINEER_REQUIRED"},
            {"status": "COMMISSIONING"},
        ]
        counts = status_counts(active, [{"status": "OPTIONAL"}], [{"lifecycle": "RESOLVED"}])
        self.assertEqual(counts["review_required"], 1)
        self.assertEqual(counts["engineer_required"], 1)
        self.assertEqual(counts["commissioning"], 1)
        self.assertEqual(counts["optional"], 1)
        self.assertEqual(counts["resolved"], 1)
        fp = evidence_fingerprint("tracking_offset", "", "SorterModel", "COMMISSIONING")
        self.assertIn("tracking_offset", fp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
