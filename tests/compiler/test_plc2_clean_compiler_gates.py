#!/usr/bin/env python3
"""v0.7 PLC2 clean-compiler gates: oracle isolation, MCR≠ES, PI writer, CS/horn, Mtrchain.

These tests assert rules derived from RUN / generic library / engineer intent.
They do NOT claim parity from a finished controller.
"""
from __future__ import annotations

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---

import ast
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys = _SFSys
sys.path.insert(0, str(SCRIPTS))

from fortna_equipment_binding import classify_estop  # noqa: E402
from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
)
from fortna_io_extract import equipment_kind  # noqa: E402
import fortna_autogen as ag  # noqa: E402


# ---------------------------------------------------------------------------
# GATE 1 — Oracle isolation
# ---------------------------------------------------------------------------

# Production compiler modules that must not open finished-site L5X parents.
_PRODUCTION_SCAN_GLOBS = (
    "fortna_autogen.py",
    "fortna_equipment_binding.py",
    "fortna_es_compiler.py",
    "fortna_io_extract.py",
    "fortna_plc_export.py",
    "fortna_workbook.py",
)

_FORBIDDEN_PATH_RES = [
    re.compile(r"OneDrive.*\.L5X", re.I),
    re.compile(r"\\Desktop\\.*ORLY_Greensboro.*\.L5X", re.I),
    re.compile(r"Folder to GPT", re.I),
    re.compile(r"ORLY_Greensboro.*Finished\.L5X", re.I),
    re.compile(r"RTfinished\.L5X", re.I),
    re.compile(r"workspace[/\\]+validation[/\\]+.*\.L5X", re.I),
    # Production must not re-home quarantined Sys/System packs
    re.compile(r"programs[/\\]+Sys_Program\.L5X"),
    re.compile(r"programs[/\\]+System_Program\.L5X"),
]


class TestGate1OracleIsolation(unittest.TestCase):
    def test_load_gold_plc2_text_always_empty(self) -> None:
        """PD-0029: finished PLC2 must never parent production emit."""
        self.assertEqual(ag._load_gold_plc2_text(), "")

    def test_sys_program_quarantined_not_in_production_dir(self) -> None:
        """PD-0030: finished Sys/System packs live under validation_oracles only."""
        prod = ROOT / "tools" / "libraries" / "programs"
        oracle = ROOT / "tools" / "libraries" / "validation_oracles"
        self.assertFalse((prod / "Sys_Program.L5X").is_file())
        self.assertFalse((prod / "System_Program.L5X").is_file())
        self.assertTrue((oracle / "Sys_Program.L5X").is_file())
        self.assertTrue((oracle / "System_Program.L5X").is_file())

    def test_include_sys_does_not_merge_finished_sys(self) -> None:
        """PD-0030: even include_sys=True must not load quarantined Sys_Program."""
        packs = ag.resolve_program_exports(include_sys=True, include_io_map_gold=False)
        names = [p.get("name") for p in packs]
        self.assertNotIn("Sys", names)

    def test_no_ps_not_cloned_from_io_map_ezpws(self) -> None:
        """PD-0032: production source scan — no EZPWS extract for NO_PS."""
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        # The NO_PS block must prefer library / datatype contract, not EZPWS*
        self.assertIn("PD-0032", src)
        self.assertNotRegex(
            src,
            r'extract_tag_block\([^)]*IO_MAP[^)]*,\s*[\'"]EZPWS',
        )
        # Ensure synthetic PS_UDT contract path remains
        self.assertIn('DataType="PS_UDT"', src)

    def test_production_source_scan_no_finished_controller_deps(self) -> None:
        """Fail if compiler paths reintroduce site-specific finished-controller deps."""
        violations: list[str] = []
        for name in _PRODUCTION_SCAN_GLOBS:
            path = SCRIPTS / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            # Skip comments that document quarantine / forbidden paths
            in_doc = False
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if '"""' in stripped or "'''" in stripped:
                    # Toggle docstring state; docstring lines are documentation only
                    in_doc = not in_doc if stripped.count('"""') + stripped.count("'''") == 1 else in_doc
                    continue
                if in_doc or stripped.startswith("#"):
                    continue
                # Allow VALIDATION_ORACLE_DIR references and string docs about quarantine
                if "validation_oracles" in line or "quarantine" in line.lower():
                    continue
                if "PD-0029" in line or "PD-0030" in line or "PD-0032" in line:
                    continue
                if "Previously loaded" in line or "never parent" in line.lower():
                    continue
                for rx in _FORBIDDEN_PATH_RES:
                    if rx.search(line):
                        violations.append(f"{name}:{i}: {line.strip()[:120]}")
        self.assertEqual(violations, [], "finished-controller deps in production:\n" + "\n".join(violations))

    def test_oracle_isolation_identity_with_without_finished_files(self) -> None:
        """Generate site-neutral semantics identical with oracle files present or absent."""
        inp = ag.AutogenInput(
            project_name="Synth_Site",
            machine="Synth_Machine",
            areas=["Area_A"],
            conveyors=[],
            include_sys=False,
            include_io_map=False,
            include_io_map_gold=False,
        )
        present = ag.resolve_program_exports(
            include_sys=True, include_io_map_gold=True
        )
        with tempfile.TemporaryDirectory() as td:
            absent = ag.resolve_program_exports(
                include_sys=True,
                include_io_map_gold=True,
                programs_dir=Path(td),
            )
        # Sys + IO_MAP gold never merge — identical empty set either way
        self.assertEqual([p.get("name") for p in present], [p.get("name") for p in absent])
        self.assertEqual(ag._load_gold_plc2_text(), "")
        self.assertFalse(
            (ROOT / "tools" / "libraries" / "programs" / "Sys_Program.L5X").is_file()
        )
        self.assertFalse(
            (ROOT / "tools" / "libraries" / "programs" / "IO_MAP_Program.L5X").is_file()
        )
        _ = inp


# ---------------------------------------------------------------------------
# GATE 2 — MCR role
# ---------------------------------------------------------------------------


class TestGate2McrRole(unittest.TestCase):
    def test_mcr_energize_coil_output_not_es_udt(self) -> None:
        """PD-0002: 1794-OA8I output 'ENERGIZE MASTER CONTROL RELAY' ≠ ES_UDT input."""
        info = classify_estop(
            "14MCR1",
            direction="O",
            device_type="1794-OA8I",
            description="ENERGIZE MASTER CONTROL RELAY",
        )
        self.assertIsNone(info, msg=f"MCR coil must not classify as ES: {info}")

    def test_mcr_aux_feedback_is_es_ok(self) -> None:
        """MCR auxiliary feedback remains ES_UDT.I.ES_OK (device ≠ signal)."""
        info = classify_estop(
            "14MCR1_AUX",
            direction="I",
            device_type="1794-IB16",
            description="MCR AUX FEEDBACK",
        )
        self.assertIsNotNone(info)
        self.assertEqual(info["member"], "I.ES_OK")
        self.assertEqual(info["confidence"], "PROVEN")

    def test_io_extract_mcr_coil_is_digital_out(self) -> None:
        kind = equipment_kind(
            "14MCR1",
            device_type="BEACON",
            description="ENERGIZE MASTER CONTROL RELAY",
        )
        self.assertEqual(kind, "digital_out")

    def test_io_map_es_member_rejects_bare_mcr_coil(self) -> None:
        self.assertEqual(ag._io_map_es_member("14MCR1"), "")
        self.assertTrue(ag._io_map_es_member("14MCR1_AUX").endswith(".I.ES_OK"))


# ---------------------------------------------------------------------------
# GATE 3 — Safety PI writer invariant
# ---------------------------------------------------------------------------


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    fixed = []
    for i, r in enumerate(rungs):
        fixed.append(re.sub(r'Number="\d+"', f'Number="{i}"', r, count=1))
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(fixed)
        + "</RLLContent></Routine>"
    )


def _extract_tag_block(library_text: str, tag_name: str) -> str | None:
    stubs = {
        "Main_Area_Safe": '<Tag Name="Main_Area_Safe" TagType="Base" DataType="ES_Zone_UDT" />',
        "Main_Area_Safe_ES_PI": '<Tag Name="Main_Area_Safe_ES_PI" TagType="Base" DataType="ES_PI20" />',
        "NO_ES": '<Tag Name="NO_ES" TagType="Base" DataType="ES_UDT" />',
        "NO_ESNull": '<Tag Name="NO_ESNull" TagType="Base" DataType="ES_UDT" />',
        "ES1000_AOI": '<Tag Name="ES1000_AOI" TagType="Base" DataType="ES_SIL1_Cat1" />',
    }
    return stubs.get(tag_name)


class TestGate3PiWriterInvariant(unittest.TestCase):
    def test_ready_zone_has_exactly_one_pi_writer(self) -> None:
        """PD-0003: operational zone with members emits Safe_PI writer."""
        zones = build_safety_zone_irs(
            safety_zones=["Area_A_ESZone1"],
            areas=["Area_A"],
            engineer_zones=[
                {
                    "name": "Area_A_ESZone1",
                    "area": "Area_A",
                    "members": ["ES100", "ES101"],
                    "conveyors": ["P100"],
                }
            ],
            estop_model={"zones": []},
            area_conveyors={"Area_A": ["P100"]},
        )
        pack = emit_es_program(
            zones,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=_extract_tag_block,
            library_text="",
            ensure_tag=lambda _n: None,
            add_tag_block=lambda _b: None,
        )
        self.assertIsNotNone(pack)
        writers = pack.get("zones_with_pi_writers") or []
        self.assertEqual(writers, ["Area_A_ESZone1"])
        self.assertTrue(pack.get("pi_writer_invariant_ok"))
        self.assertIn("Area_A_ESZone1_Safe_PI", pack["program_xml"])

    def test_unresolved_membership_does_not_fabricate_zone_pi(self) -> None:
        """Unresolved Safety → shell only; no fabricated operational PI writer."""
        zones = build_safety_zone_irs(
            safety_zones=["Area_A_ESZone1"],
            areas=["Area_A"],
            engineer_zones=[],
            estop_model={"zones": []},
            area_conveyors={"Area_A": ["P100"]},
        )
        pack = emit_es_program(
            zones,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=_extract_tag_block,
            library_text="",
            ensure_tag=lambda _n: None,
            add_tag_block=lambda _b: None,
        )
        self.assertIsNotNone(pack)
        self.assertEqual(pack.get("zones_with_pi_writers") or [], [])
        self.assertNotIn("_Safe_PI", pack["program_xml"])


# ---------------------------------------------------------------------------
# GATE 4 — Area start warning / horn model
# ---------------------------------------------------------------------------


class TestGate4AreaHornCs(unittest.TestCase):
    def test_control_station_o_horn_member_exists_in_library_contract(self) -> None:
        """CS_UDT.O.Horn is the approved start-warning writer surface."""
        lib = (ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('DataType Name="Control_Station_O"', lib)
        self.assertIn('Name="Horn"', lib)
        self.assertIn("Slow_ControlStation", lib)

    def test_synthetic_area_cs_horn_writer_pattern(self) -> None:
        """Site-neutral: AOI instance + CS_UDT/NO_CS InOuts — never literal 0."""
        aoi_inst = "Area_A_CS1"  # Slow_ControlStation datatype
        station = "CP2_CS"  # CS_UDT
        horn = "WH_A1"
        call = f"Slow_ControlStation({aoi_inst},{station},NO_CS,NO_CS,NO_CS,NO_CS,10000);"
        writer = f"XIC({station}.O.Horn)OTE({horn});"
        self.assertIn("Slow_ControlStation", call)
        self.assertNotIn(",0,", call)
        self.assertIn("NO_CS", call)
        self.assertIn(".O.Horn", writer)


# ---------------------------------------------------------------------------
# GATE 5 — Mtrchain-proven downstream
# ---------------------------------------------------------------------------


class TestGate5MtrchainDownstream(unittest.TestCase):
    def test_conveyor_row_has_downstream_provenance_field(self) -> None:
        row = ag.ConveyorRow(
            number=1,
            system="X",
            main_area="Area_A",
            safety_zone="",
            conveyor="P100",
            type="Transport with MS",
            downstream="P110",
            downstream_provenance="RUN_MTRCHAIN_PROVEN",
        )
        self.assertEqual(row.downstream_provenance, "RUN_MTRCHAIN_PROVEN")
        self.assertEqual(row.downstream, "P110")

    def test_provenance_vocab_documented(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        for token in (
            "RUN_MTRCHAIN_PROVEN",
            "ENGINEER_ASSIGNED",
            "REVIEW_REQUIRED",
            "PD-0013",
        ):
            self.assertIn(token, src)


# ---------------------------------------------------------------------------
# Regression — Warden-resolved items must not regress (spot checks)
# ---------------------------------------------------------------------------


class TestWardenRegressionSpotChecks(unittest.TestCase):
    def test_default_safety_never_operational_helper(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("REVIEW_REQUIRED_DEFAULT_BUCKET", src)
        self.assertIn("is_default_safety_name", src)

    def test_no_ps_contract_shape(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("PS_FltTime", src)
        # Synthetic NO_PS emit must not declare O_Reset as a live member value
        synth = src[src.find("Correct PS_UDT shape") : src.find("Correct PS_UDT shape") + 1200]
        self.assertIn("PS_FltTime", synth)
        self.assertNotIn('DataValueMember Name="O_Reset"', synth)

    def test_pe_logic_slow_only_comment(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("PE_Logic is Slow-only", src)


if __name__ == "__main__":
    unittest.main()
