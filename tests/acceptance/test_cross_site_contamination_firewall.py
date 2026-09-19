#!/usr/bin/env python3
"""Cross-site contamination firewall — virgin Indy must not inherit prior-site tags."""
from __future__ import annotations

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
ROOT = _SF_REPO
# --- end bootstrap ---

import tempfile
import unittest
from pathlib import Path

VIRGIN = ROOT / "workspace" / "_virgin_orindy" / "RUN"


@unittest.skipUnless((VIRGIN / "project.cfg").is_file(), "virgin ORINDY RUN missing")
class TestCrossSiteContaminationFirewall(unittest.TestCase):
    def test_virgin_effective_input_ignores_foreign_workbook_sorter_hosts(self) -> None:
        """Prior Greensboro-style sorter_build must not invent foreign divert hosts on Indy."""
        from fortna_workbook import build_effective_autogen_input

        contaminated = {
            "sorter_build": {
                "appliedAt": "t",
                "divert_host_conveyor": "P506",  # Greensboro pack template host
                "sorter_area_name": "GreensboroSorter",
                "divert_count": 15,
                "shipping_sorter_supported": True,
            },
            "include_programs": ["Sorter_Track", "ShippingSorter_Area_L3"],
        }
        # Virgin path: empty workbook (no contamination)
        virgin = build_effective_autogen_input(VIRGIN, {}, machine="ORINDYAC6")
        self.assertNotEqual(
            (virgin.sorter_build or {}).get("divert_host_conveyor"),
            "P506",
        )
        # Contaminated workbook is explicit engineer state — allowed as ENGINEER input,
        # but discovery model for ORINDY must still prove P610 as RUN host.
        from fortna_sorter_discovery import build_canonical_sorter_model

        model = build_canonical_sorter_model(VIRGIN, "ORINDYAC6")
        self.assertEqual(str(model.get("divert_host_conveyor") or "").upper(), "P610")
        self.assertNotEqual(str(model.get("sorter_area_name") or ""), "GreensboroSorter")

    def test_final_closure_flags_foreign_pack_hosts(self) -> None:
        from fortna_final_artifact_closure import validate_final_artifact

        fake = '<Tag Name="P506_Divert1"/><Tag Name="P610_Divert1"/>'
        r = validate_final_artifact(
            l5x_text=fake,
            machine="ORINDYAC6",
            allowed_divert_hosts=["P610"],
        )
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(r["orphan_count"] >= 1)

    def test_virgin_mode_ignores_contaminated_prior_workbook(self) -> None:
        """Qualification virgin path must start from empty site-specific state.

        Simulate: Site A workbook configured → clear → Site B virgin RUN.
        Expected: zero Site-A sorter hosts / Safety / include decisions survive.
        """
        from fortna_qualification_runner import _empty_workbook
        from fortna_workbook import build_effective_autogen_input

        site_a = {
            "machine": "ORLYGREENSBORO",
            "sorter_build": {
                "divert_host_conveyor": "P506",
                "sorter_area_name": "GreensboroSorter",
                "appliedAt": "t",
            },
            "include_programs": ["Sorter_Track", "ShippingSorter_Area_L3"],
            "safety_build": {
                "zones": [
                    {
                        "name": "Greensboro_ESZone1",
                        "members": ["ES_GSO_1"],
                        "operational": True,
                    }
                ]
            },
            "merges_2to1": [{"name": "P406", "discharge": "P406"}],
        }
        # After Clear / new-site: virgin workbook replaces prior site state.
        virgin_wb = _empty_workbook("ORINDYAC6")
        self.assertFalse(virgin_wb.get("sorter_build"))
        # Empty safety shell (zones=[]) is allowed; prior-site members must not survive.
        safety = virgin_wb.get("safety_build") or {}
        self.assertEqual(list(safety.get("zones") or []), [])
        self.assertFalse(virgin_wb.get("merges_2to1"))
        self.assertNotEqual(virgin_wb.get("machine"), site_a["machine"])

        effective = build_effective_autogen_input(
            VIRGIN, virgin_wb, machine="ORINDYAC6"
        )
        sb = effective.sorter_build or {}
        self.assertNotEqual(str(sb.get("divert_host_conveyor") or "").upper(), "P506")
        self.assertNotIn("GreensboroSorter", str(sb.get("sorter_area_name") or ""))
        # Prior-site merge identity must not appear from empty virgin workbook.
        merge_names = {
            str((m or {}).get("name") or "").upper()
            for m in (effective.merges_2to1 or [])
            if isinstance(m, dict)
        }
        self.assertNotIn("P406", merge_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
