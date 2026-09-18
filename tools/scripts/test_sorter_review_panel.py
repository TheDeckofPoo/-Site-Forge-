#!/usr/bin/env python3
"""Gate G — Sorter Review Required panel source contracts.

Asserts panel presence, status categories, and that OPTIONAL is never mixed
into REVIEW_REQUIRED actionable lists. Uses model-driven field authority —
no site-specific production hardcodes.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "dashboard" / "index.html"
PLUS = ROOT / "dashboard" / "fortna-plus.js"

STATUS_CATS = (
    "PROVEN",
    "DERIVED",
    "REVIEW_REQUIRED",
    "ENGINEER_REQUIRED",
    "COMMISSIONING",
    "OPTIONAL",
)


class TestSorterReviewPanel(unittest.TestCase):
    def test_panel_present_in_html(self) -> None:
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn('id="sorter-review-required"', html)
        self.assertIn("Sorter Review Required", html)
        self.assertIn('id="sorter-review-groups"', html)
        self.assertIn("OPTIONAL", html)
        self.assertIn("never mixed", html.lower())

    def test_status_categories_in_js(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("SORTER_STATUS_CATS", js)
        self.assertIn("collectSorterReviewItems", js)
        self.assertIn("renderSorterReviewPanel", js)
        self.assertIn("collectSorterOptionalItems", js)
        for cat in STATUS_CATS:
            self.assertIn(cat, js)

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

    def test_no_site_specific_production_ifs(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        # Gate G collector must not hard-code site equipment lists
        collector = js[js.index("function collectSorterReviewItems") : js.index("function collectSorterOptionalItems")]
        for banned in ("ORNCCP", "P504", "P506", "ENC504", "SHIP_SORTER"):
            self.assertNotIn(banned, collector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
