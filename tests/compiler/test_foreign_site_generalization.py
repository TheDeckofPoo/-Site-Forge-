#!/usr/bin/env python3
"""Foreign-site generalization contracts (ORINDYAC3 Warden findings → generic rules).

No finished-PLC / Brownsburg answer-key coupling.
"""
from __future__ import annotations
# --- siteforge test path bootstrap ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# --- end bootstrap ---

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fortna_conveyor_section_model import _motor_to_section
from fortna_default_ownership import is_default_safety_name
from fortna_es_compiler import build_safety_zone_irs, emit_es_program
from fortna_prism_ingest import prism_disabled
from fortna_run_logic_triggers import (
    mcr_command_writers_from_run,
    parse_logic_asc,
)


def _rung_xml(num, text, comment=""):
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(rungs)
        + "</RLLContent></Routine>"
    )


def _extract(_lib, _tag):
    return None


class TestDefaultSafetyNeverOperational(unittest.TestCase):
    def test_underscore_alias_detected(self) -> None:
        self.assertTrue(is_default_safety_name("Default_Safety"))
        self.assertTrue(is_default_safety_name("Default Safety"))
        self.assertTrue(is_default_safety_name("UNASSIGNED_SAFETY"))
        self.assertFalse(is_default_safety_name("ModuleB_ESZone1"))

    def test_default_safety_not_in_es_ir(self) -> None:
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "Default_Safety",
                    "area": "Main_Area",
                    "members": ["ES100", "ES101"],
                    "engineerEdited": True,
                },
                {
                    "name": "Trash_ESZone1",
                    "area": "ModuleB_Area",
                    "members": ["ES406"],
                    "engineerEdited": True,
                },
            ],
            default_area="ModuleB_Area",
        )
        names = {z.name for z in irs}
        self.assertNotIn("Default_Safety", names)
        self.assertIn("Trash_ESZone1", names)

    def test_emit_asserts_zero_default_ops(self) -> None:
        from fortna_es_compiler import SafetyZoneIR

        z = SafetyZoneIR(
            name="Default_Safety",
            area="Main_Area",
            members=["ES100"],
        )
        with self.assertRaises(AssertionError) as ctx:
            emit_es_program(
                [z],
                _rung_xml=_rung_xml,
                routine=_routine,
                extract_tag_block=_extract,
                library_text="",
            )
        self.assertIn("PD-DEFAULT", str(ctx.exception))


class TestMultiConditionMcrParse(unittest.TestCase):
    def test_and_if_conditions_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td) / "FORTNA"
            fortna.mkdir()
            # Synthetic multi-condition MCR trigger (generic — not ORINDY-specific #)
            (fortna / "Logic.asc").write_text(
                "IF part named PS100 AIR PRESSURE IS ADEQUATE at I/O address 1 "
                "AND IF part named ES200 E-STOP IS ON at I/O address 2 "
                "AND IF part named PB300 RESET IS ON at I/O address 3 "
                "THEN TURN ON part named 1MCR1 MASTER CONTROL RELAY at I/O address 4 "
                "REFERENCE Trigger #99 Name MULTI COND MCR\n",
                encoding="utf-8",
            )
            triggers = parse_logic_asc(td)
            self.assertEqual(len(triggers), 1)
            conds = triggers[0]["conditions"]
            self.assertEqual(len(conds), 3, msg=f"conditions dropped: {conds}")
            self.assertEqual([c["io"] for c in conds], ["PS100", "ES200", "PB300"])
            writers = mcr_command_writers_from_run(td)
            self.assertTrue(writers)
            w = writers[0]
            self.assertEqual(w.get("condition_count"), 3)
            # Either PROVEN compound rung or REVIEW — never silently shortened to 1 cond
            if w.get("status") == "PROVEN":
                rung = w.get("rung") or ""
                self.assertIn("OTE(", rung)
                # All three operands must appear (as raw or resolved form)
                for token in ("PS100", "ES200", "PB300"):
                    self.assertTrue(
                        token in rung
                        or any(token in str(r.get("raw") or "") for r in (w.get("resolved_conditions") or []))
                        or any(token in str(r.get("operand") or "") for r in (w.get("resolved_conditions") or [])),
                        msg=f"{token} missing from multi-cond rung {rung}",
                    )
            else:
                self.assertEqual(w.get("status"), "REVIEW_REQUIRED")
                self.assertEqual(len(w.get("conditions") or []), 3)


class TestAuxNeverFakeConveyor(unittest.TestCase):
    def test_motor_aux_not_pnnnaux_section(self) -> None:
        # Role suffix stripped → parent section; never P1000AUX fake conveyor
        self.assertEqual(_motor_to_section("M1000AUX"), "P1000")
        self.assertEqual(_motor_to_section("M1000_AUX"), "P1000")
        self.assertEqual(_motor_to_section("M130A"), "P130A")
        self.assertEqual(_motor_to_section("M130A_AUX"), "P130A")
        self.assertNotEqual(_motor_to_section("M1000AUX"), "P1000AUX")
        self.assertFalse(str(_motor_to_section("M1122AUX") or "").endswith("AUX"))


class TestPrismIsolation(unittest.TestCase):
    def test_disable_env(self) -> None:
        with mock.patch.dict("os.environ", {"FORTNA_PRISM_DISABLE": "1"}):
            self.assertTrue(prism_disabled())
        with mock.patch.dict("os.environ", {"FORTNA_PRISM_DISABLE": ""}):
            self.assertFalse(prism_disabled())


class TestManyToManyStillGreen(unittest.TestCase):
    """ce65acb stale-zone + many-to-many must remain intact."""

    def test_shared_aux_two_zones(self) -> None:
        from fortna_default_ownership import assign_safety_members, delete_safety_zone_return_to_default

        zones = [
            {"name": "ZoneA", "source_id": "sz_a", "members": [], "engineerEdited": True},
            {"name": "ZoneB", "source_id": "sz_b", "members": [], "engineerEdited": True},
        ]
        zones = assign_safety_members(zones, ["ES406", "2MCR1_AUX"], "ZoneA")
        zones = assign_safety_members(zones, ["2MCR1_AUX"], "ZoneB")
        a = next(z for z in zones if z["name"] == "ZoneA")
        b = next(z for z in zones if z["name"] == "ZoneB")
        self.assertIn("2MCR1_AUX", a["members"])
        self.assertIn("2MCR1_AUX", b["members"])
        zones = delete_safety_zone_return_to_default(zones, "ZoneA")
        b2 = next(z for z in zones if z["name"] == "ZoneB")
        self.assertEqual(set(b2["members"]), {"2MCR1_AUX"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
