#!/usr/bin/env python3
"""ORI-110 — Safety configuration gate + engineer-assigned ES emission.

1. ORL-style engineer assignment → Safe_Logic + Safe_PI + populated Main_Routine
2. TFCP1-style engineer assignment → Safe_Logic + Safe_PI + populated Main_Routine
3. FOUND>0 / 0 operational members → normal generate cannot silently shell-only
4. Default/Unassigned → zero operational ES references
5. Clear site A → site B → zero Safety residue (name isolation)

Full RUN→L5X reproduction for (1)/(2) was proven on SHA 804e5b4 in Phase 1/2
delivery-gate builds. These unit tests pin the compiler + Autogen gate contracts.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import AutogenInput, ConveyorRow, generate  # noqa: E402
from fortna_es_compiler import build_safety_zone_irs, emit_es_program  # noqa: E402
from fortna_workbook import apply_workbook_to_input  # noqa: E402

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    body = "".join(
        r.replace('Number="0"', f'Number="{i}"', 1) if 'Number="0"' in r else r
        for i, r in enumerate(rungs)
    )
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


def _engineer_zone(name: str, area: str, members: list[str]) -> dict:
    return {
        "name": name,
        "engineering_name": name,
        "area": area,
        "areaRef": area,
        "members": list(members),
        "membersOrigin": "ENGINEER_ASSIGNED",
        "engineerEdited": True,
        "createdBy": "engineer",
        "zoneOrigin": "ENGINEER",
        "operational": True,
        "status": "READY",
        "conveyors": [],
    }


def _default_bucket(members: list[str]) -> dict:
    return {
        "name": "Default Safety",
        "members": list(members),
        "membersOrigin": "UNASSIGNED",
        "isDefault": True,
        "isUnassignedBucket": True,
        "defaultSafety": True,
        "operational": False,
        "status": "REVIEW_REQUIRED",
    }


def _emit(zone: dict, area: str, conveyors: list[str]) -> dict:
    irs = build_safety_zone_irs(
        safety_zones=[zone["name"]],
        areas=[area],
        engineer_zones=[zone],
        estop_model={"zones": []},
        area_conveyors={area: conveyors},
    )
    return emit_es_program(
        irs,
        _rung_xml=_rung_xml,
        routine=_routine,
        extract_tag_block=lambda *_a, **_k: None,
        library_text="",
        ensure_tag=lambda *_a, **_k: None,
        add_tag_block=lambda *_a, **_k: None,
        # Unit tests supply synthetic writer graph so PI invariant can pass.
        written_tags={m for m in (zone.get("members") or [])},
    )


class TestOri110OrlStyleEngineerAssignment(unittest.TestCase):
    """1. ORL-style assign → Apply → Autogen IR → Safe_Logic + Safe_PI + Main."""

    def test_orl_engineer_zone_emits_safe_logic_and_pi(self) -> None:
        zone = _engineer_zone(
            "Area_Test1_ESZone1",
            "Area_Test1",
            ["1ES", "1ES1", "ESLS101", "ESLS103"],
        )
        pack = _emit(zone, "Area_Test1", ["P900", "P902"])
        self.assertIsNotNone(pack)
        xml = pack.get("program_xml") or ""
        self.assertIn("JSR(Area_Test1_ESZone1_Safe_Logic,0);", xml)
        self.assertIn("JSR(Area_Test1_ESZone1_Safe_PI,0);", xml)
        self.assertIn("Area_Test1_ESZone1_Safe_Logic", xml)
        self.assertIn("Area_Test1_ESZone1_Safe_PI", xml)
        self.assertIn("ES_SIL1_Cat1", xml)
        self.assertIn("ES_PI20", xml)
        self.assertIn("1ES", xml)
        self.assertIn("ESLS101", xml)
        self.assertIn("Area_Test1_ESZone1", pack.get("emitted_zones") or [])


class TestOri110Tfcp1StyleEngineerAssignment(unittest.TestCase):
    """2. TFCP1-style assign valid device → Safe_Logic + Safe_PI + Main."""

    def test_tfcp1_engineer_zone_emits_safe_logic_and_pi(self) -> None:
        zone = _engineer_zone(
            "TFCP1_ESZone1",
            "TFCP1_Area",
            ["ES300", "ESLS301", "ESLS400", "ESLS706"],
        )
        pack = _emit(zone, "TFCP1_Area", ["P100"])
        self.assertIsNotNone(pack)
        xml = pack.get("program_xml") or ""
        self.assertIn("JSR(TFCP1_ESZone1_Safe_Logic,0);", xml)
        self.assertIn("JSR(TFCP1_ESZone1_Safe_PI,0);", xml)
        self.assertIn("TFCP1_ESZone1_Safe_Logic", xml)
        self.assertIn("TFCP1_ESZone1_Safe_PI", xml)
        for m in zone["members"]:
            self.assertIn(m, xml)
        self.assertIn("TFCP1_ESZone1", pack.get("emitted_zones") or [])


@unittest.skipUnless(LIBRARY.is_file(), f"library missing: {LIBRARY}")
class TestOri110FoundZeroOperationalBlocksShell(unittest.TestCase):
    """3. FOUND>0 / zero operational members cannot silently produce ordinary shell ES."""

    def test_found_devices_zero_members_blocks_without_ack(self) -> None:
        devices = [
            {"name": "ES300", "status": "UNASSIGNED", "assignable": True},
            {"name": "ESLS301", "status": "UNASSIGNED", "assignable": True},
        ]
        inp = AutogenInput(
            project_name="TFCP1_SHELL_BLOCK",
            machine="TFCP1",
            areas=["TFCP1_Area"],
            safety_zones=[],
            safety_zone_members=[],
            safety_build={
                "version": 1,
                "source": "inventory",
                "zones": [_default_bucket(["ES300", "ESLS301"])],
                "devices": devices,
                "safetyDevices": devices,
                "unassignedDevices": ["ES300", "ESLS301"],
                "counts": {"devices_found": 2, "devices": 2, "unassigned": 2},
            },
            conveyors=[
                ConveyorRow(
                    number=100,
                    system="T",
                    main_area="TFCP1_Area",
                    conveyor="P100",
                )
            ],
            include_sys=True,
            include_io_map=False,
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                generate(inp, LIBRARY, Path(td))
        err = str(ctx.exception)
        self.assertIn("Safety configuration required", err)
        self.assertIn("2 Safety devices found", err)
        self.assertIn("0 assigned to operational Safety zones", err)
        self.assertIn("Open Safety Build", err)

    def test_ack_allows_explicit_shell_only_marking(self) -> None:
        devices = [
            {"name": "ES300", "status": "UNASSIGNED", "assignable": True},
        ]
        inp = AutogenInput(
            project_name="TFCP1_SHELL_ACK",
            machine="TFCP1",
            areas=["TFCP1_Area"],
            safety_zones=[],
            safety_zone_members=[],
            safety_build={
                "version": 1,
                "source": "inventory",
                "zones": [_default_bucket(["ES300"])],
                "devices": devices,
                "safetyDevices": devices,
                "unassignedDevices": ["ES300"],
                "counts": {"devices_found": 1, "devices": 1, "unassigned": 1},
                "acknowledge_safety_shell_only": True,
            },
            acknowledge_safety_shell_only=True,
            conveyors=[
                ConveyorRow(
                    number=100,
                    system="T",
                    main_area="TFCP1_Area",
                    conveyor="P100",
                )
            ],
            include_sys=True,
            include_io_map=False,
        )
        with tempfile.TemporaryDirectory() as td:
            outer = generate(inp, LIBRARY, Path(td))
        rep = outer.get("report") or {}
        es = rep.get("es_program") or {}
        detail = str(es.get("detail") or "")
        self.assertTrue(es.get("shell") or "SHELL" in detail.upper(), detail or es)
        self.assertTrue(
            es.get("shell_acknowledged")
            or "SAFETY NOT GENERATED — ES SHELL ONLY" in detail,
            detail or es,
        )
        l5x = Path(str(outer.get("l5x") or ""))
        if l5x.is_file():
            xml = l5x.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("_Safe_Logic", xml)
            self.assertNotIn("_Safe_PI", xml)


class TestOri110DefaultUnassignedNotOperational(unittest.TestCase):
    """4. Default/Unassigned → zero operational ES references."""

    def test_default_bucket_does_not_emit_safe_logic(self) -> None:
        zones = build_safety_zone_irs(
            safety_zones=["Default Safety"],
            areas=["TFCP1_Area"],
            engineer_zones=[_default_bucket(["ES300", "ESLS301"])],
            estop_model={"zones": []},
            area_conveyors={"TFCP1_Area": ["P100"]},
        )
        ready = [z for z in zones if z.members]
        self.assertEqual(ready, [])
        pack = emit_es_program(
            zones,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_a, **_k: None,
            library_text="",
            ensure_tag=lambda *_a, **_k: None,
            add_tag_block=lambda *_a, **_k: None,
        )
        self.assertIsNotNone(pack)
        xml = pack.get("program_xml") or ""
        self.assertNotIn("_Safe_Logic", xml)
        self.assertNotIn("_Safe_PI", xml)
        self.assertNotIn("ES300", xml)


class TestOri110CrossSiteSafetyResidue(unittest.TestCase):
    """5. Clear site A → site B: zero Safety residue in workbook handoff."""

    def test_workbook_overlay_does_not_keep_foreign_zone(self) -> None:
        site_a_zone = _engineer_zone(
            "MSCRENOPICK_ESZone1",
            "MSCRENOPICK_Area",
            ["ESPB2", "ESPB24"],
        )
        site_b_zone = _engineer_zone(
            "TFCP1_ESZone1",
            "TFCP1_Area",
            ["ES300"],
        )
        inp = AutogenInput(
            project_name="TFCP1",
            machine="TFCP1",
            areas=["TFCP1_Area"],
            safety_zones=["MSCRENOPICK_ESZone1"],
            safety_zone_members=[site_a_zone],
            safety_build={"zones": [site_a_zone]},
        )
        wb = {
            "version": 1,
            "machine": "TFCP1",
            "project_name": "TFCP1",
            "areas": [{"name": "TFCP1_Area"}],
            "options": {"areas": ["TFCP1_Area"], "safety_zones": ["TFCP1_ESZone1"]},
            "safety_build": {"version": 1, "source": "engineer", "zones": [site_b_zone]},
            "conveyors": [],
        }
        out = apply_workbook_to_input(inp, wb)
        names = [
            str(z.get("name") or "")
            for z in (out.safety_zone_members or [])
            if isinstance(z, dict)
        ]
        self.assertIn("TFCP1_ESZone1", names)
        self.assertNotIn("MSCRENOPICK_ESZone1", names)
        joined = " ".join(names)
        self.assertNotIn("MSCRENO", joined.upper())
        sb_names = [
            str(z.get("name") or "")
            for z in ((out.safety_build or {}).get("zones") or [])
            if isinstance(z, dict)
        ]
        self.assertEqual(sb_names, ["TFCP1_ESZone1"])


if __name__ == "__main__":
    unittest.main()
