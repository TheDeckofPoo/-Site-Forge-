#!/usr/bin/env python3
"""PLC5 sorter deep evidence graph / autofill — no site-name production hardcodes."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_discovery import (  # noqa: E402
    AUTH_PROVEN,
    build_canonical_sorter_model,
    write_plc5_sorter_deep_reports,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
OUT = ROOT / "exports" / "stabilization"

EXPECTED_CP5 = {
    "504_BELT",
    "506_SHIP_SORTER",
    "508_SHIP_SORTER",
    "509_SHIP_SORTER",
    "510_SHIP_SORTER",
}
FORBIDDEN_PROD = [
    SCRIPTS / "fortna_sorter_discovery.py",
    SCRIPTS / "fortna_run_workspace_discover.py",
    SCRIPTS / "fortna_knowledge_enrich.py",
]


class TestPlc5SorterDeepAutofill(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CP5_RUN.is_dir():
            raise unittest.SkipTest(f"CP5 RUN missing: {CP5_RUN}")
        cls.model = build_canonical_sorter_model(CP5_RUN, "ORNCCP5")

    def test_no_site_hardcodes_in_production(self) -> None:
        for path in FORBIDDEN_PROD:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotRegex(
                text,
                r"""machine\s*==\s*['\"]ORNCCP5['\"]""",
                msg=f"{path.name} must not hardcode machine==ORNCCP5",
            )
            self.assertNotIn("504_BELT", text)
            self.assertNotIn("506_SHIP_SORTER", text)
            # Decision-logic hardcodes only (inventory notes may mention gold-pack sites).
            self.assertNotRegex(
                text,
                r"""if\s+.*Greensboro|machine\s*==\s*['\"]ORNCCP5['\"]|['\"]P504['\"]|['\"]ENC504['\"]|['\"]SHIP_SORTER['\"]""",
                msg=f"{path.name} must not use site identifiers as decision logic",
            )

    def test_deep_coverage_autofill(self) -> None:
        m = self.model
        self.assertEqual(m.get("sorter_count"), 5)
        names = {
            (s.get("name") or {}).get("value")
            if isinstance(s.get("name"), dict)
            else s.get("name")
            for s in (m.get("sorters") or [])
        }
        self.assertEqual(names, EXPECTED_CP5)
        cov = m.get("coverage") or {}
        self.assertEqual(cov.get("tracking_conveyors_resolved"), 5)
        self.assertEqual(cov.get("tracking_pes_resolved"), 5)
        self.assertEqual(cov.get("divert_outputs_resolved"), 32)
        self.assertEqual(cov.get("divert_topology_rows"), 32)
        induct = m.get("induct") or {}
        self.assertTrue(
            (induct.get("photoeye") or {}).get("value")
            if isinstance(induct.get("photoeye"), dict)
            else induct.get("photoeye")
        )
        self.assertTrue(
            (induct.get("conveyor") or {}).get("value")
            if isinstance(induct.get("conveyor"), dict)
            else induct.get("conveyor")
        )
        # No numeric-suffix-only path: conveyor must cite Mtrchain/EnableBit
        for t in m.get("tracking_path") or []:
            conv = t.get("conveyor") or {}
            src = conv.get("source") if isinstance(conv, dict) else ""
            val = conv.get("value") if isinstance(conv, dict) else conv
            if val:
                self.assertIn("Mtrchain", src)
                self.assertNotRegex(src or "", r"ENC\d+.*=.*P\d+")

    def test_divert_io_from_outpoints_not_lane_enable_invalid(self) -> None:
        for row in self.model.get("divert_rows") or []:
            auth = (row.get("authority") or {}).get("divert_output_io")
            io = row.get("divert_output_io") or {}
            val = io.get("value") if isinstance(io, dict) else io
            src = io.get("source") if isinstance(io, dict) else ""
            if auth == AUTH_PROVEN:
                self.assertTrue(val and str(val).upper() != "INVALID")
                self.assertIn("Outpoints", src)

    def test_gate_f_field_list_complete(self) -> None:
        fields = self.model.get("gate_f_fields") or []
        self.assertGreaterEqual(len(fields), 25)
        labels = " ".join(f.get("field", "") for f in fields)
        for needle in (
            "Sorter type",
            "Induct conveyor",
            "Induct PE",
            "Tracking conveyor",
            "Divert physical output",
            "PPI",
            "Maximum cartons",
        ):
            self.assertIn(needle, labels)

    def test_application_structure_not_name_inferred(self) -> None:
        app = self.model.get("application_structure") or {}
        self.assertIn("Outpoints", app.get("path") or "")
        note = (app.get("note") or "").lower()
        self.assertIn("not from name tokens", note)
        self.assertTrue(app.get("tracking_sections"))

    def test_plc2_still_zero(self) -> None:
        if not PLC2_RUN.is_dir():
            self.skipTest("PLC2 RUN missing")
        m = build_canonical_sorter_model(PLC2_RUN, "ORNCCP2")
        self.assertEqual(m.get("sorter_count"), 0)

    def test_write_reports(self) -> None:
        paths = write_plc5_sorter_deep_reports(self.model, OUT)
        for key in (
            "field_authority_md",
            "field_authority_json",
            "deep_autofill_md",
            "deep_autofill_json",
        ):
            p = Path(paths[key])
            self.assertTrue(p.is_file(), msg=f"missing {p}")
        auth = json.loads(
            Path(paths["field_authority_json"]).read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(auth.get("fields") or []), 25)
        deep = json.loads(Path(paths["deep_autofill_json"]).read_text(encoding="utf-8"))
        self.assertEqual(deep.get("sorters_discovered"), 5)
        self.assertEqual(deep.get("plc_generation"), "NOT_STARTED")
        cov = deep.get("autofill_coverage") or {}
        self.assertIn("PROVEN", cov)
        self.assertIn("DERIVED", cov)
        self.assertIn("ENGINEER_REQUIRED", cov)
        self.assertIn("UNKNOWN", cov)


if __name__ == "__main__":
    unittest.main(verbosity=2)
