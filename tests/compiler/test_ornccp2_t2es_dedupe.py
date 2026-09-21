#!/usr/bin/env python3
"""ORNCCP2 smoke: 2ES/T_2ES alias emits one T_2ES controller tag."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

RUN = _SF_REPO / "workspace" / "_plc2_run_peek" / "RUN"
LIBRARY = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"


@unittest.skipUnless((RUN / "project.cfg").is_file(), "ORNCCP2 RUN peek missing")
@unittest.skipUnless(LIBRARY.is_file(), "OReilly library missing")
class TestOrnccp2T2esDedupe(unittest.TestCase):
    def test_alias_members_emit_t_2es_once(self) -> None:
        from fortna_autogen import build_l5x, load_from_run
        from fortna_studio_preflight import preflight_l5x

        inp = load_from_run(RUN)
        members = ["2ES", "T_2ES", "3ES", "T_3ES", "ES400", "2MCR1", "T_2MCR1"]
        inp.safety_build = {
            "version": 1,
            "zones": [
                {
                    "name": "Default_Safety",
                    "area": (inp.areas or ["Default_Area"])[0],
                    "conveyors": ["P1000"],
                    "members": members,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "engineerEdited": True,
                }
            ],
        }
        inp.safety_zones = ["Default_Safety"]
        l5x, report = build_l5x(inp, LIBRARY)
        self.assertEqual(
            len(re.findall(r'<Tag\b[^>]*\bName="T_2ES"', l5x)),
            1,
        )
        self.assertEqual(
            len(re.findall(r'<Tag\b[^>]*\bName="T_3ES"', l5x)),
            1,
        )
        self.assertTrue((report.get("generation_assertions") or {}).get("ok"))
        self.assertEqual((report.get("tag_registry") or {}).get("conflicts"), [])
        out = _SF_REPO / "exports" / "diagnostics" / "ornccp2_t2es_fix" / "_pytest.L5X"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(l5x, encoding="utf-8")
        pf = preflight_l5x(out)
        dups = [i for i in (pf.get("issues") or []) if i.get("kind") == "duplicate_tag"]
        self.assertEqual(dups, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
