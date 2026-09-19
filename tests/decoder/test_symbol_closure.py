#!/usr/bin/env python3
"""Gate 7 — symbol closure invariant tests."""
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


import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_symbol_closure import (  # noqa: E402
    CLOSURE_DECLARED,
    CLOSURE_FAIL,
    CLOSURE_MODULE_BOUND,
    check_symbol_closure,
    is_ethernet_vfd_command_root,
)


def _mini_l5x(*, extra_rung: str = "", extra_tag: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content>
<Controller Name="TEST" ProcessorType="1756-L82E">
<Tags>
<Tag Name="P500_VFD" TagType="Base" DataType="Motor_Starter_UDT" Constant="false" ExternalAccess="Read/Write"/>
{extra_tag}
</Tags>
<Modules>
<Module Name="CP5RIO0" CatalogNumber="1794-AENT"/>
</Modules>
<Programs>
<Program Name="IO_MAP" TestEdits="false" MainRoutineName="Main_Routine" Disabled="false" UseAsFolder="false">
<Tags/>
<Routines>
<Routine Name="CP_I" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(CP5RIO0:I.Data[0].0)OTE(P500_VFD.I.Auxiliary_Forward);]]></Text></Rung>
{extra_rung}
</RLLContent>
</Routine>
<Routine Name="CP_O" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(P500_VFD.O.Run)OTE(CP5RIO0:O.Data[0].0);]]></Text></Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""


class TestEthernetVfdCommandRoots(unittest.TestCase):
    def test_role_detection(self) -> None:
        self.assertTrue(is_ethernet_vfd_command_root("VFD118_JOG"))
        self.assertTrue(is_ethernet_vfd_command_root("VFD500_CLR_FLT"))
        self.assertTrue(is_ethernet_vfd_command_root("VFD216_DIR_BIT0"))
        self.assertTrue(is_ethernet_vfd_command_root("VFD216_LOC_CTRL"))
        self.assertTrue(is_ethernet_vfd_command_root("VFD216_MOP_INC"))
        self.assertTrue(is_ethernet_vfd_command_root("VFD216_ACC_BIT1"))
        self.assertFalse(is_ethernet_vfd_command_root("VFD118_EN"))
        self.assertFalse(is_ethernet_vfd_command_root("VFD118_AUX"))
        self.assertFalse(is_ethernet_vfd_command_root("P500_VFD"))


class TestSymbolClosureFailDanglingJog(unittest.TestCase):
    def test_dangling_vfd_jog_fails(self) -> None:
        l5x = _mini_l5x(
            extra_rung=(
                '<Rung Number="1" Type="N">'
                "<Text><![CDATA[XIC(CP5RIO0:I.Data[1].0)OTE(VFD118_JOG);]]></Text>"
                "</Rung>"
            )
        )
        report = check_symbol_closure(l5x)
        self.assertFalse(report.ok)
        roots = {f.root for f in report.failures}
        self.assertIn("VFD118_JOG", roots)
        jog = next(f for f in report.failures if f.root == "VFD118_JOG")
        self.assertEqual(jog.classification, CLOSURE_FAIL)
        self.assertIn("ETHERNET", jog.expected_owner.upper())


class TestSymbolClosureKnownDiscretePath(unittest.TestCase):
    def test_discrete_iomap_passes(self) -> None:
        report = check_symbol_closure(_mini_l5x())
        self.assertTrue(report.ok, [f.to_dict() for f in report.failures])
        classes = {f.classification for f in report.findings}
        self.assertTrue(classes & {CLOSURE_DECLARED, CLOSURE_MODULE_BOUND})

    def test_plc5_hotbuild_passes_or_external(self) -> None:
        path = ROOT / "exports" / "stabilization" / "plc5_hotbuild_full" / "ORNCCP5.L5X"
        if not path.is_file():
            self.skipTest("PLC5 hotbuild L5X missing")
        text = path.read_text(encoding="utf-8", errors="replace")
        report = check_symbol_closure(text)
        # Must not fail on dangling ethernet VFD command roles
        eth_fails = [f for f in report.failures if is_ethernet_vfd_command_root(f.root)]
        self.assertEqual(eth_fails, [], [f.to_dict() for f in eth_fails])
        self.assertTrue(
            report.ok,
            [f.to_dict() for f in report.failures[:8]],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
