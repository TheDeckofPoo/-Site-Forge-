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

from fortna_conveyor_section_model import (
    _motor_to_section,
    discover_sections,
    is_solenoid_device_signal,
)
from fortna_default_ownership import (
    is_default_area_program_bucket,
    is_default_safety_name,
)
from fortna_es_compiler import build_safety_zone_irs, emit_es_program
from fortna_prism_ingest import prism_disabled, prism_writes_enabled, _prism_root
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


class TestSolenoidNeverIndependentConveyor(unittest.TestCase):
    """GATE F — SSVEZPE*_P1/_P2 is DEVICE_SIGNAL, not CONTROL_SECTION."""

    def test_is_solenoid_device_signal(self) -> None:
        self.assertTrue(is_solenoid_device_signal("SSVEZPE134_P1"))
        self.assertTrue(is_solenoid_device_signal("SSVEZPE134_P2"))
        self.assertTrue(is_solenoid_device_signal("SSV150_P1"))
        self.assertFalse(is_solenoid_device_signal("EZPE134_P1"))
        self.assertFalse(is_solenoid_device_signal("P134"))
        self.assertFalse(is_solenoid_device_signal("M134"))

    def test_ssv_alone_does_not_promote_p1_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            fortna = run / "FORTNA"
            fortna.mkdir()
            (run / "project.cfg").write_text('MachineName="SYNTH_CTRL"\n', encoding="utf-8")
            # Mechanical master P134 + solenoid DEVICE_SIGNALs only (no EZPE _P1)
            hdr = "~".join(
                [
                    "IO_Name",
                    "Type",
                    "Machine_Name",
                    "IO_Address_Word",
                    "IO_Address_Bit",
                    "General_Description",
                    "Drive",
                ]
            )
            rows = [
                "~".join(["P134", "CURVE", "SYNTH_CTRL", "0", "0", "HAIRPIN", ""]),
                "~".join(
                    ["SSVEZPE134_P1", "TRIANG", "SYNTH_CTRL", "10", "0", "RELEASE SOL", ""]
                ),
                "~".join(
                    ["SSVEZPE134_P2", "TRIANG", "SYNTH_CTRL", "10", "1", "RELEASE SOL", ""]
                ),
                "~".join(["M134", "MOTOR", "SYNTH_CTRL", "20", "0", "MOTOR", ""]),
            ]
            (fortna / "Conveyor.asc").write_text(
                hdr + "\n" + "\n".join(rows) + "\n", encoding="utf-8"
            )
            mtr_hdr = "Motor_Name~Timer_Name~" + "~".join(
                f"Motor_Chained{i}" for i in range(1, 11)
            )
            (fortna / "Mtrchain.asc").write_text(mtr_hdr + "\n", encoding="utf-8")
            discovered = discover_sections(run, "SYNTH_CTRL")
            sections = discovered.get("sections") or {}
            self.assertIn("P134", sections, msg="master P134 must be kept/restored")
            self.assertNotIn("P134_P1", sections)
            self.assertNotIn("P134_P2", sections)
            self.assertFalse(
                (sections.get("P134") or {}).get("assembly_only"),
                msg="SSV-only must not suppress master P134 as assembly_only",
            )

    def test_ezpe_still_promotes_p1_section(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            fortna = run / "FORTNA"
            fortna.mkdir()
            (run / "project.cfg").write_text('MachineName="SYNTH_CTRL"\n', encoding="utf-8")
            hdr = "~".join(
                [
                    "IO_Name",
                    "Type",
                    "Machine_Name",
                    "IO_Address_Word",
                    "IO_Address_Bit",
                    "General_Description",
                    "Drive",
                ]
            )
            rows = [
                "~".join(["P150", "ZEROPRESSURE", "SYNTH_CTRL", "0", "0", "ZP MERGE", ""]),
                "~".join(
                    ["EZPE150_P1", "PHOTOCELL", "SYNTH_CTRL", "11", "0", "PRESENCE", ""]
                ),
                "~".join(
                    ["SSVEZPE150_P1", "TRIANG", "SYNTH_CTRL", "12", "0", "RELEASE SOL", ""]
                ),
                "~".join(["M150", "MOTOR", "SYNTH_CTRL", "20", "0", "MOTOR", ""]),
            ]
            (fortna / "Conveyor.asc").write_text(
                hdr + "\n" + "\n".join(rows) + "\n", encoding="utf-8"
            )
            mtr_hdr = "Motor_Name~Timer_Name~" + "~".join(
                f"Motor_Chained{i}" for i in range(1, 11)
            )
            (fortna / "Mtrchain.asc").write_text(mtr_hdr + "\n", encoding="utf-8")
            discovered = discover_sections(run, "SYNTH_CTRL")
            sections = discovered.get("sections") or {}
            self.assertIn("P150_P1", sections, msg="EZPE photocell must still promote")
            # Parent may be assembly_only when real PE sections exist
            self.assertTrue(
                (sections.get("P150") or {}).get("assembly_only")
                or "P150" in (discovered.get("suppress_as_assembly_only") or {}),
            )


class TestDefaultAreaProgramFilter(unittest.TestCase):
    """GATE K — Default Area must not emit as engineered Area programs."""

    def test_bucket_helper(self) -> None:
        self.assertTrue(is_default_area_program_bucket("Default Area"))
        self.assertTrue(is_default_area_program_bucket("Area_1"))
        self.assertTrue(is_default_area_program_bucket("Unassigned"))
        self.assertTrue(is_default_area_program_bucket(""))
        self.assertFalse(is_default_area_program_bucket("ModuleB_Area"))
        self.assertFalse(is_default_area_program_bucket("ORNCCP2_Area"))
        # Main_Area remains a provisional engineering name (emitible)
        self.assertFalse(is_default_area_program_bucket("Main_Area"))

    def test_build_l5x_withholds_default_area_programs(self) -> None:
        import fortna_autogen as ag

        lib = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        if not lib.is_file():
            self.skipTest(f"library missing: {lib}")
        inp = ag.AutogenInput(
            project_name="Synthetic_Default_Area",
            machine="SYNTH_CTRL",
            areas=["Default Area", "ModuleB_Area"],
            safety_zones=["ModuleB_ESZone1"],
            conveyors=[
                ag.ConveyorRow(
                    number=1,
                    conveyor="P901",
                    main_area="Default Area",
                    safety_zone="ModuleB_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                ),
                ag.ConveyorRow(
                    number=2,
                    conveyor="P902",
                    main_area="ModuleB_Area",
                    safety_zone="ModuleB_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                ),
            ],
        )
        l5x, report = ag.build_l5x(inp, lib)
        progs = report.get("programs") or []
        self.assertFalse(
            any(re.search(r"Default.?Area.*(Fast|Slow|L1|L2)", p, re.I) for p in progs),
            msg=f"Default Area programs leaked: {progs}",
        )
        self.assertTrue(
            any("ModuleB" in p for p in progs),
            msg=f"engineered Area missing: {progs}",
        )
        withheld = report.get("default_area_programs_withheld") or []
        self.assertTrue(
            any("default" in str(x).lower() for x in withheld),
            msg=f"withheld not recorded: {withheld}",
        )
        self.assertNotRegex(l5x, r'Name="Default_Area_(Fast|Slow|L1|L2)"')


class TestPrismIsolation(unittest.TestCase):
    def test_disable_env(self) -> None:
        with mock.patch.dict("os.environ", {"FORTNA_PRISM_DISABLE": "1"}, clear=False):
            self.assertTrue(prism_disabled())
            self.assertFalse(prism_writes_enabled())
        with mock.patch.dict(
            "os.environ",
            {"FORTNA_PRISM_DISABLE": "", "FORTNA_PRISM_ENABLE": "", "FORTNA_PRISM_ROOT": ""},
            clear=False,
        ):
            self.assertFalse(prism_disabled())

    def test_default_isolated_without_enable(self) -> None:
        """GATE R: missing ENABLE/ROOT → scratch, not shared C:\\dev\\worktree\\PRISM."""
        with mock.patch.dict(
            "os.environ",
            {
                "FORTNA_PRISM_DISABLE": "",
                "FORTNA_PRISM_ENABLE": "",
                "FORTNA_PRISM_ROOT": "",
            },
            clear=False,
        ):
            self.assertFalse(prism_writes_enabled())
            root = _prism_root()
            self.assertIn("_prism_disabled_scratch", str(root))
            self.assertNotEqual(root.resolve(), Path(r"C:\dev\worktree\PRISM").resolve())

    def test_enable_or_root_opts_in(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"FORTNA_PRISM_DISABLE": "", "FORTNA_PRISM_ENABLE": "1", "FORTNA_PRISM_ROOT": ""},
            clear=False,
        ):
            self.assertTrue(prism_writes_enabled())
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(
                "os.environ",
                {
                    "FORTNA_PRISM_DISABLE": "",
                    "FORTNA_PRISM_ENABLE": "",
                    "FORTNA_PRISM_ROOT": td,
                },
                clear=False,
            ):
                self.assertTrue(prism_writes_enabled())
                self.assertEqual(_prism_root().resolve(), Path(td).resolve())


class TestSlowFltSuspectNop(unittest.TestCase):
    """GATE P — FINISHED_SITE_DERIVED_SUSPECT Slow_Flt must not emit as success."""

    def test_clone_emits_nop_by_default(self) -> None:
        import fortna_autogen as ag

        lib = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        if not lib.is_file():
            self.skipTest(f"library missing: {lib}")
        text = lib.read_text(encoding="utf-8", errors="replace")
        with mock.patch.dict(
            "os.environ", {"FORTNA_SLOW_FLT_APPROVED_GENERIC": ""}, clear=False
        ):
            item = ag.clone_template_for_conveyor(
                text, "P1000_Conv", "P100", "Area_A", "", ""
            )
        flt = next(r for r in item["rungs"] if r["label"] == "Flt")
        self.assertIn("NOP()", flt["text"])
        self.assertNotIn("Slow_Flt(", flt["text"])
        self.assertIn("REVIEW_REQUIRED", flt.get("comment") or "")
        self.assertIn("FINISHED_SITE_DERIVED_SUSPECT", flt.get("comment") or "")

    def test_approved_generic_flag_emits_slow_flt(self) -> None:
        import fortna_autogen as ag

        lib = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        if not lib.is_file():
            self.skipTest(f"library missing: {lib}")
        text = lib.read_text(encoding="utf-8", errors="replace")
        with mock.patch.dict(
            "os.environ", {"FORTNA_SLOW_FLT_APPROVED_GENERIC": "1"}, clear=False
        ):
            item = ag.clone_template_for_conveyor(
                text, "P1000_Conv", "P100", "Area_A", "", ""
            )
        flt = next(r for r in item["rungs"] if r["label"] == "Flt")
        self.assertIn("Slow_Flt(", flt["text"])


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
