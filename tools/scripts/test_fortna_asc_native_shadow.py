#!/usr/bin/env python3
"""GATE 1 — Native FortnaPlus ASC shadow precedence.

Native get_one_amenu: if Table.asc.<MACHINE> exists → use ONLY that file's
rows; else Table.asc. Do NOT merge absent base rows into an existing machine
overlay.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    MODE_LEGACY_UNION,
    MODE_NATIVE_SHADOW,
    SCOPE_BASE_FALLBACK,
    SCOPE_MACHINE_OVERLAY,
    merge_table_rows,
)


class TestNativeAscShadow(unittest.TestCase):
    def test_orindyac6_overlay_excludes_absent_base_identities(self):
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td)
            (fortna / "Table.asc").write_text(
                '"Name"~"Value"\n'
                "P136~base136\n"
                "P406~base406\n"
                "P600~base600\n",
                encoding="utf-8",
            )
            (fortna / "Table.asc.ORINDYAC6").write_text(
                '"Name"~"Value"\n'
                "P600~overlay600\n",
                encoding="utf-8",
            )

            native = merge_table_rows(fortna, "Table.asc", "ORINDYAC6")
            ids = {r["identity"] for r in native["rows"]}
            self.assertEqual(ids, {"P600"})
            self.assertEqual(native["mode"], MODE_NATIVE_SHADOW)
            self.assertEqual(native["resolution"], "native_shadow_overlay")
            row = native["rows"][0]
            self.assertEqual(row["source_scope"], SCOPE_MACHINE_OVERLAY)
            self.assertEqual(row["row"]["Value"], "overlay600")
            self.assertFalse(
                any(r["source_scope"] == SCOPE_BASE_FALLBACK for r in native["rows"])
            )

    def test_legacy_union_imports_absent_base_identities(self):
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td)
            (fortna / "Table.asc").write_text(
                '"Name"~"Value"\n'
                "P136~base136\n"
                "P406~base406\n"
                "P600~base600\n",
                encoding="utf-8",
            )
            (fortna / "Table.asc.ORINDYAC6").write_text(
                '"Name"~"Value"\n'
                "P600~overlay600\n",
                encoding="utf-8",
            )

            legacy = merge_table_rows(
                fortna, "Table.asc", "ORINDYAC6", mode=MODE_LEGACY_UNION
            )
            by_id = {r["identity"]: r for r in legacy["rows"]}
            self.assertEqual(set(by_id), {"P136", "P406", "P600"})
            self.assertEqual(by_id["P406"]["source_scope"], SCOPE_BASE_FALLBACK)
            self.assertEqual(by_id["P600"]["source_scope"], "controller_overlay")
            self.assertEqual(by_id["P600"]["row"]["Value"], "overlay600")

    def test_no_overlay_uses_base_only(self):
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td)
            (fortna / "Table.asc").write_text(
                '"Name"~"Value"\n'
                "P136~base136\n"
                "P406~base406\n"
                "P600~base600\n",
                encoding="utf-8",
            )
            native = merge_table_rows(fortna, "Table.asc", "ORINDYAC6")
            ids = {r["identity"] for r in native["rows"]}
            self.assertEqual(ids, {"P136", "P406", "P600"})
            self.assertEqual({r["source_scope"] for r in native["rows"]}, {"base"})
            self.assertEqual(native["resolution"], "base_only")


if __name__ == "__main__":
    unittest.main()
