#!/usr/bin/env python3
"""Gate C/K — Safety Build membership must survive to ES compiler.

Reproduces Curtis HAHAHA_ESZone1 defect:
  UI assigned 4ES/5ES/6ES/ES422/CP2_ES… → READY
  but ES shell said Unresolved zones (no members)

Root cause: _looks_like_safety_device dropped Fortna panel names; engineer
members must be authoritative.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_es_compiler import (  # noqa: E402
    _looks_like_safety_device,
    build_safety_zone_irs,
    emit_es_program,
    safety_readiness,
)
from fortna_autogen import AutogenInput, ConveyorRow, build_l5x  # noqa: E402
from fortna_workbook import apply_workbook_to_input  # noqa: E402

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"

HAHAHA_MEMBERS = [
    "4ES", "5ES", "6ES", "ES422", "CP2_ES", "CP2_ESR1", "CP2_ESR2",
    "CP2_MCR1", "CP3_ES", "T_2MCR1", "ESLS125", "ESLS127", "ESLS141",
]


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    body = "".join(
        r.replace('Number="0"', f'Number="{i}"', 1) if 'Number="0"' in r else r
        for i, r in enumerate(rungs)
    )
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


class TestLooksLikeSafetyDevice(unittest.TestCase):
    def test_fortna_panel_and_cp_es_names(self) -> None:
        for n in ["4ES", "5ES", "2ES", "CP2_ES", "CP3_ES", "ES422", "CP2_ESR1", "CP2_MCR1"]:
            self.assertTrue(_looks_like_safety_device(n), n)


class TestHandoffBoundaries(unittest.TestCase):
    def test_counts_survive_each_boundary(self) -> None:
        safety_build = {
            "version": 1,
            "source": "safety_build",
            "appliedAt": "2026-09-17T20:00:00Z",
            "zones": [
                {
                    "name": "HAHAHA_ESZone1",
                    "area": "HAHAHA",
                    "areaRef": "HAHAHA",
                    "conveyors": [f"P{400 + i}" for i in range(10)],
                    "conveyorRefs": [f"P{400 + i}" for i in range(10)],
                    "members": list(HAHAHA_MEMBERS),
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "engineerEdited": True,
                    "status": "READY",
                }
            ],
            "devices": [{"name": m, "status": "ENGINEER_ASSIGNED", "safetyZoneRef": "HAHAHA_ESZone1"} for m in HAHAHA_MEMBERS],
            "unassignedDevices": ["CP3_ESR5"],
            "counts": {
                "devices": len(HAHAHA_MEMBERS) + 1,
                "devices_found": len(HAHAHA_MEMBERS) + 1,
                "unassigned": 1,
                "engineer_assigned": len(HAHAHA_MEMBERS),
            },
        }
        # Boundary: SafetyBuild
        self.assertEqual(len(safety_build["zones"][0]["members"]), 13)

        # Boundary: SavedCanonical / workbook overlay
        inp = AutogenInput(
            project_name="ORNCCP2",
            areas=["HAHAHA"],
            safety_zones=["HAHAHA_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=i + 1,
                    conveyor=f"P{400 + i}",
                    main_area="HAHAHA",
                    safety_zone="HAHAHA_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                )
                for i in range(10)
            ],
        )
        wb = {"safety_build": safety_build, "conveyors": [
            {"conveyor": f"P{400 + i}", "include": True, "main_area": "HAHAHA", "safety_zone": "HAHAHA_ESZone1"}
            for i in range(10)
        ]}
        inp2 = apply_workbook_to_input(inp, wb)
        self.assertEqual(len(inp2.safety_build.get("zones", [])[0]["members"]), 13)
        self.assertEqual(len(inp2.safety_zone_members[0]["members"]), 13)

        # Boundary: EffectiveModel / PLCCompiler IR
        eng = list(inp2.safety_build.get("zones") or [])
        irs = build_safety_zone_irs(
            safety_zones=["HAHAHA_ESZone1"],
            areas=["HAHAHA"],
            engineer_zones=eng,
            default_area="HAHAHA",
            area_conveyors={"HAHAHA": [f"P{400 + i}" for i in range(10)]},
        )
        self.assertEqual(len(irs), 1)
        self.assertEqual(len(irs[0].members), 13, irs[0].members)
        # Fortna 4ES/5ES/6ES → canonical Logix T_4ES/T_5ES/T_6ES
        self.assertIn("T_4ES", irs[0].members)
        self.assertIn("CP2_ES", irs[0].members)  # already-legal CP form unchanged
        self.assertTrue(all(re.match(r"^[A-Za-z_]", m) for m in irs[0].members), irs[0].members)
        self.assertEqual(irs[0].device_membership_status, "RESOLVED")
        ready = safety_readiness(irs, library_has_aois=True)
        self.assertEqual(ready["status"], "READY")

        # Boundary: ES emit — real Safe_Logic, not shell
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
        )
        self.assertIsNotNone(pack)
        assert pack is not None
        self.assertFalse(pack.get("shell"))
        self.assertIn("HAHAHA_ESZone1", pack.get("emitted_zones") or [])
        xml = pack["program_xml"]
        self.assertIn("HAHAHA_ESZone1_Safe_Logic", xml)
        self.assertIn("HAHAHA_ESZone1_Safe_PI", xml)
        self.assertIn("ES_SIL1_Cat1(", xml)
        self.assertIn("JSR(HAHAHA_ESZone1_Safe_Logic,0);", xml)


@unittest.skipUnless(LIBRARY.is_file(), "library missing")
class TestHandoffInL5X(unittest.TestCase):
    def test_build_l5x_emits_zone_routines(self) -> None:
        members = list(HAHAHA_MEMBERS)
        inp = AutogenInput(
            project_name="ORNCCP2",
            areas=["HAHAHA"],
            safety_zones=["HAHAHA_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=i + 1,
                    conveyor=f"P{400 + i}",
                    main_area="HAHAHA",
                    safety_zone="HAHAHA_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                )
                for i in range(4)
            ],
            safety_build={
                "zones": [{
                    "name": "HAHAHA_ESZone1",
                    "area": "HAHAHA",
                    "conveyors": [f"P{400 + i}" for i in range(4)],
                    "members": members,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "engineerEdited": True,
                    "status": "READY",
                }],
                "unassignedDevices": ["CP3_ESR5"],
                "counts": {"devices_found": len(members) + 1, "unassigned": 1},
            },
            safety_zone_members=[{
                "name": "HAHAHA_ESZone1",
                "area": "HAHAHA",
                "conveyors": [f"P{400 + i}" for i in range(4)],
                "members": members,
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
            }],
            include_sys=True,
            include_io_map=True,
        )
        l5x, report = build_l5x(inp, LIBRARY)
        self.assertIn('Program Name="ES"', l5x)
        self.assertIn("P01_Safety_20ms", l5x)
        self.assertIn("HAHAHA_ESZone1_Safe_Logic", l5x)
        self.assertIn("HAHAHA_ESZone1_Safe_PI", l5x)
        es = report.get("es_program") or {}
        self.assertNotEqual(es.get("shell"), True)
        self.assertIn("HAHAHA_ESZone1", es.get("emitted_zones") or [])
        # Partial: unassigned remain review
        self.assertTrue(
            es.get("status") in ("READY", "REVIEW_REQUIRED"),
            es.get("status"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
