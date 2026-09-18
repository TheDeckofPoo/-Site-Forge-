#!/usr/bin/env python3
"""Regression: PLC5 Configio words 516/520/522 must stay distinct Logix endpoints.

False-collision pattern (before fix):
  Bank516.0 (EZPWS442) and Bank520.0 (SSVEZPE442_P) both → T_1794_AENT_3:O.Data[1].0

Truth (EIPModules.asc.ORNCCP5 + Configio NODE Desc):
  516 / NODE52-7 / Configio Bank 40 → AENT-2 IA16 slot7 InputBank=40 → CP5RIO1:I.Data[6]
  520 / NODE53-1 / Configio Bank 40 → AENT-3 OB16P slot1 OutputBank=40 → CP5RIO2:O.Data[0]
  522 / NODE53-3 / Configio Bank 44 → AENT-3 OB16P slot3 OutputBank=44 → CP5RIO2:O.Data[2]

Also keeps PLC2 P220 lettered-motor duplicate protection intact.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_physical_word_resolver import (  # noqa: E402
    build_physical_word_map,
    parse_configio_node_desc,
    resolve_word_bit,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"


def _plc2_run() -> Path | None:
    try:
        from fortna_io_extract import read_project_meta
    except Exception:
        read_project_meta = None  # type: ignore
    for cand in (
        ROOT / "workspace" / "active" / "RUN",
        ROOT / "workspace" / "_plc2_run_peek" / "RUN",
        ROOT / "workspace" / "active_rio_audit" / "RUN",
    ):
        if not (cand / "project.cfg").is_file():
            continue
        if read_project_meta is None:
            return cand
        try:
            mach = (read_project_meta(cand).get("machine_name") or "").upper()
        except Exception:
            mach = ""
        if mach == "ORNCCP2" or not mach:
            return cand
    return None


PLC2_RUN = _plc2_run()


class TestPlc5IoEndpointCollision(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (CP5_RUN / "project.cfg").is_file():
            raise unittest.SkipTest(f"PLC5 RUN missing: {CP5_RUN}")
        cls.pm = build_physical_word_map(CP5_RUN, "ORNCCP5")

    def test_node_desc_parse(self) -> None:
        hit = parse_configio_node_desc("CP5-NODE52-7A")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["panel"], "CP5")
        self.assertEqual(hit["node"], 52)
        self.assertEqual(hit["desc_slot"], 7)
        self.assertEqual(hit["lohi"], "Low")
        # missing hyphen after panel still parses
        hit2 = parse_configio_node_desc("CP5NODE53-1A")
        self.assertIsNotNone(hit2)
        assert hit2 is not None
        self.assertEqual(hit2["node"], 53)
        self.assertEqual(hit2["desc_slot"], 1)

    def test_bank516_and_bank520_not_same_channel(self) -> None:
        a = resolve_word_bit(self.pm, 516, 0)
        b = resolve_word_bit(self.pm, 520, 0)
        self.assertIsNotNone(a, "Bank516.0 unresolved")
        self.assertIsNotNone(b, "Bank520.0 unresolved")
        assert a is not None and b is not None
        self.assertNotEqual(
            a.get("channel"),
            b.get("channel"),
            "Bank516.0 and Bank520.0 must not share a Logix channel",
        )
        self.assertEqual(a.get("channel"), "CP5RIO1:I.Data[6].0")
        self.assertEqual(a.get("direction"), "I")
        self.assertEqual(a.get("type"), "1794-IA16")
        self.assertEqual(b.get("channel"), "CP5RIO2:O.Data[0].0")
        self.assertEqual(b.get("direction"), "O")
        self.assertEqual(b.get("type"), "1794-OB16P")
        print(f"  [PASS] 516→{a.get('channel')} ; 520→{b.get('channel')}")

    def test_bank520_and_bank522_distinct_ob16p_modules(self) -> None:
        b520 = resolve_word_bit(self.pm, 520, 0)
        b522 = resolve_word_bit(self.pm, 522, 0)
        self.assertIsNotNone(b520)
        self.assertIsNotNone(b522)
        assert b520 is not None and b522 is not None
        self.assertNotEqual(b520.get("channel"), b522.get("channel"))
        self.assertEqual(b520.get("channel"), "CP5RIO2:O.Data[0].0")
        self.assertEqual(b522.get("channel"), "CP5RIO2:O.Data[2].0")
        self.assertEqual(int(b520.get("eip_slot") or -1), 1)
        self.assertEqual(int(b522.get("eip_slot") or -1), 3)
        self.assertEqual(b520.get("provenance", {}).get("output_bank"), 40)
        self.assertEqual(b522.get("provenance", {}).get("output_bank"), 44)
        print(f"  [PASS] 520→{b520.get('channel')} ; 522→{b522.get('channel')}")

    def test_assign_how_uses_eipmodules_not_bank_math(self) -> None:
        for w in (516, 520, 522):
            e = (self.pm.get("words") or {}).get(str(w)) or {}
            self.assertEqual(e.get("assign_how"), "configio_node_eipmodules_bank")
            self.assertIn("EIPModules", (e.get("provenance") or {}).get("source_tables") or [])


class TestPlc2P220DuplicateProtectionStillWorks(unittest.TestCase):
    """Do not weaken PLC2 lettered-motor / duplicate OUTPUT protections."""

    def test_m220_aux_lettered_identity(self) -> None:
        import re

        # Mirror fortna_autogen._motor_to_p_base post-PL-3 contract (nested helper).
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn("M220_AUX != M220A_AUX", src)
        self.assertIn("NAME_NORMALIZATION_COLLISION", src)
        self.assertIn("never strip to P220", src)

        def motor_to_p_base(mot_core: str, known_convs: set[str]) -> str:
            mm = re.match(r"^M(\d{2,4})([A-Z]?)$", mot_core, re.I)
            if not mm:
                return ""
            digits, letters = mm.group(1), (mm.group(2) or "").upper()
            full = f"P{digits}{letters}"
            if full in known_convs:
                return full
            if letters:
                return ""
            base = f"P{digits}"
            if base in known_convs:
                return base
            p1 = f"{base}_P1"
            if p1 in known_convs:
                return p1
            return ""

        def aux_ote(mot_core: str, known: set[str]) -> str:
            pbase = motor_to_p_base(mot_core, known)
            m = re.match(r"^M(\d{2,4}[A-Z]?)$", mot_core, re.I)
            digits = m.group(1) if m else ""
            return (
                f"{pbase}_MS.I.Auxiliary_Forward"
                if pbase
                else f"P{digits}_MS.I.Auxiliary_Forward"
            )

        known = {"P220", "P220A", "P100"}
        a = aux_ote("M220", known)
        b = aux_ote("M220A", known)
        self.assertEqual(a, "P220_MS.I.Auxiliary_Forward")
        self.assertEqual(b, "P220A_MS.I.Auxiliary_Forward")
        self.assertNotEqual(a, b)

        known2 = {"P220A", "P100"}
        a2 = aux_ote("M220", known2)
        b2 = aux_ote("M220A", known2)
        self.assertEqual(b2, "P220A_MS.I.Auxiliary_Forward")
        self.assertNotIn("P220A", a2)
        print("  [PASS] P220 / P220A AUX identities remain distinct")

    def test_plc2_physical_int229_vs_m402_still_distinct(self) -> None:
        if PLC2_RUN is None or not (PLC2_RUN / "project.cfg").is_file():
            self.skipTest("PLC2 RUN missing")
        pm = build_physical_word_map(PLC2_RUN, "ORNCCP2")
        m402 = resolve_word_bit(pm, 206, 6)
        int229 = resolve_word_bit(pm, 207, 6)
        self.assertIsNotNone(m402)
        self.assertIsNotNone(int229)
        assert m402 is not None and int229 is not None
        self.assertEqual(m402.get("channel"), "CP2RIO0:O.Data[6].6")
        self.assertEqual(int229.get("channel"), "CP2RIO0:I.Data[7].6")
        self.assertNotEqual(m402.get("channel"), int229.get("channel"))
        print("  [PASS] PLC2 M402/INT229 channels still distinct")

    def test_preflight_duplicate_ote_still_errors(self) -> None:
        from fortna_studio_preflight import _check_iomap_duplicate_otes

        target = "CP2RIO0:O.Data[6].6"
        l5x = f"""<?xml version="1.0"?>
<RSLogix5000Content>
  <Controller>
    <Programs>
      <Program Name="IO_MAP">
        <Routines>
          <Routine Name="CP_O" Type="RLL">
            <RLLContent>
              <Rung Number="1" Type="N">
                <Text><![CDATA[XIC(INT229)OTE({target});]]></Text>
              </Rung>
              <Rung Number="2" Type="N">
                <Text><![CDATA[XIC(P402_Conv.O.Run)OTE({target});]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>
"""
        findings: list[dict] = []

        def add(sev, kind, message, **extra):
            findings.append({"severity": sev, "kind": kind, "message": message, **extra})

        _check_iomap_duplicate_otes(l5x, add)
        dups = [f for f in findings if f.get("kind") == "iomap_duplicate_ote"]
        self.assertTrue(dups, f"expected duplicate OTE blocker, got {findings}")
        print(f"  [PASS] duplicate OTE still blocked: {dups[0].get('message', '')[:120]}")


def main() -> int:
    print("=== test_plc5_io_endpoint_collision ===")
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPlc5IoEndpointCollision))
    suite.addTests(loader.loadTestsFromTestCase(TestPlc2P220DuplicateProtectionStillWorks))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ALL PASS" if result.wasSuccessful() else "FAIL")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
