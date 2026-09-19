#!/usr/bin/env python3
"""GATE 5 — P406 contamination boundary under legacy_union vs native_shadow.

Shows that for ORINDYAC6, when Table.asc.<MACHINE> exists with P600 only,
legacy_union imports P406 via base_fallback while native_shadow does not.

First contamination boundary: fortna_site_model.merge_table_rows(mode=...).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    MODE_LEGACY_UNION,
    MODE_NATIVE_SHADOW,
    SCOPE_BASE_FALLBACK,
    SCOPE_MACHINE_OVERLAY,
    merge_table_rows,
)

MACHINE = "ORINDYAC6"
EXPORT_JSON = ROOT / "exports" / "stabilization" / "fortnaplus_native_resolution.json"


def _write_fixture(fortna: Path) -> None:
    (fortna / "Table.asc").write_text(
        '"Name"~"Value"\n'
        "P136~base136\n"
        "P406~base406\n"
        "P600~base600\n",
        encoding="utf-8",
    )
    (fortna / f"Table.asc.{MACHINE}").write_text(
        '"Name"~"Value"\n'
        "P600~overlay600\n",
        encoding="utf-8",
    )


class TestP406Contamination(unittest.TestCase):
    def test_p406_enters_via_base_fallback_legacy_only(self):
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td)
            _write_fixture(fortna)

            legacy = merge_table_rows(
                fortna, "Table.asc", MACHINE, mode=MODE_LEGACY_UNION
            )
            native = merge_table_rows(
                fortna, "Table.asc", MACHINE, mode=MODE_NATIVE_SHADOW
            )

            legacy_p406 = next(
                (r for r in legacy["rows"] if r.get("identity") == "P406"), None
            )
            native_ids = {r["identity"] for r in native["rows"]}

            self.assertIsNotNone(legacy_p406)
            assert legacy_p406 is not None
            self.assertEqual(legacy_p406["source_scope"], SCOPE_BASE_FALLBACK)
            self.assertEqual(
                legacy_p406["evidence"][0].get("note"),
                "identity absent from controller overlay",
            )

            self.assertNotIn("P406", native_ids)
            self.assertEqual(native_ids, {"P600"})
            self.assertEqual(
                {r["source_scope"] for r in native["rows"]},
                {SCOPE_MACHINE_OVERLAY},
            )

            report = {
                "kind": "P406ContaminationBoundary",
                "version": 1,
                "machine": MACHINE,
                "first_contamination_boundary": (
                    "fortna_site_model.merge_table_rows"
                ),
                "scenario": {
                    "base": ["P136", "P406", "P600"],
                    "overlay": ["P600"],
                    "overlay_file": f"Table.asc.{MACHINE}",
                },
                "legacy_union": {
                    "active_identities": sorted(
                        r["identity"] for r in legacy["rows"] if r.get("identity")
                    ),
                    "p406_present": True,
                    "p406_scope": SCOPE_BASE_FALLBACK,
                },
                "native_shadow": {
                    "active_identities": sorted(native_ids),
                    "p406_present": False,
                    "p406_scope": None,
                },
                "conclusion": (
                    "P406 enters ORINDYAC6 active set only under legacy_union "
                    "base_fallback when a machine overlay exists. native_shadow "
                    "matches FortnaPlus get_one_amenu (overlay-only)."
                ),
            }
            # Keep report embeddable; full export written by docs/export step.
            self.assertTrue(report["legacy_union"]["p406_present"])
            self.assertFalse(report["native_shadow"]["p406_present"])
            self._last_report = report  # type: ignore[attr-defined]

    def test_export_payload_shape_matches_gate5(self):
        """Ensure stabilization export documents the contamination boundary."""
        if not EXPORT_JSON.is_file():
            self.skipTest(f"missing {EXPORT_JSON}")
        data = json.loads(EXPORT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(data.get("kind"), "FortnaPlusNativeResolution")
        boundary = data.get("p406_contamination") or {}
        self.assertEqual(boundary.get("machine"), MACHINE)
        self.assertTrue(boundary.get("legacy_union", {}).get("p406_present"))
        self.assertFalse(boundary.get("native_shadow", {}).get("p406_present"))
        self.assertIn("merge_table_rows", boundary.get("first_contamination_boundary", ""))


if __name__ == "__main__":
    unittest.main()
