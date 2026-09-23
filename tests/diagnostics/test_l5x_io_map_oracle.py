#!/usr/bin/env python3
"""Diagnostics oracle parser tests — never part of production binder path."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIAG = REPO / "tools" / "diagnostics"
SCRIPTS = REPO / "tools" / "scripts"
ORACLE = REPO / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X"

if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from l5x_io_map_oracle import build_oracle_io_map, parse_io_map_routines  # noqa: E402


class TestL5xIoMapOracle(unittest.TestCase):
    @unittest.skipUnless(ORACLE.is_file(), "finished Greensboro PLC2 L5X not present")
    def test_oracle_finds_es406_es_ok_mapping(self) -> None:
        oracle = build_oracle_io_map(ORACLE)
        hits = [
            r
            for r in oracle["mappings"]
            if (r.get("logical_tag") or "") == "ES406.I.ES_OK"
        ]
        self.assertTrue(hits, "expected ES406.I.ES_OK in finished IO_MAP")
        row = hits[0]
        self.assertEqual(row["device"], "ES406")
        self.assertEqual(row["member"], "I.ES_OK")
        self.assertEqual(row["datatype"], "ES_UDT")
        self.assertRegex(row["endpoint"], r"^CP2RIO0:I\.Data\[\d+\]\.\d+$")
        # Canonical Greensboro example from the finished map.
        self.assertEqual(row["endpoint"], "CP2RIO0:I.Data[1].8")
        self.assertIn(row["routine"], {"CP_I", "CP_O"})

    @unittest.skipUnless(ORACLE.is_file(), "finished Greensboro PLC2 L5X not present")
    def test_parse_routines_cover_cp_i_and_cp_o(self) -> None:
        rows = parse_io_map_routines(ORACLE)
        routines = {r["routine"] for r in rows}
        self.assertIn("CP_I", routines)
        self.assertIn("CP_O", routines)
        self.assertGreaterEqual(len(rows), 50)

    def test_production_modules_do_not_import_oracle(self) -> None:
        """Static import firewall: production binders must not reference oracle."""
        targets = [
            SCRIPTS / "fortna_autogen.py",
            SCRIPTS / "fortna_equipment_binding.py",
        ]
        import_shaped = re.compile(
            r"^\s*(?:from|import)\s+.*(?:l5x_io_map_oracle|greensboro_plc2_oracle_compare)",
            re.I | re.M,
        )
        for path in targets:
            self.assertTrue(path.is_file(), f"missing {path}")
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIsNone(
                import_shaped.search(text),
                f"{path.name} must not import diagnostics oracle modules",
            )
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if "l5x_io_map_oracle" in line or "greensboro_plc2_oracle_compare" in line:
                    self.fail(
                        f"{path.name}:{i} references diagnostics oracle module: {line.strip()}"
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
