#!/usr/bin/env python3
"""Permanent overnight RC acceptance gates.

Future changes touching I/O, Transportation, Safety, workbook state, writers,
Autogen, or L5X output must fail CI/qualification if golden behavior regresses.

Required fixtures covered here:
- MSCRENOPICK full integration (I/O accounted + one-Area transport + ES Safety)
- ORINDYAC3 / virgin-site artifact acceptance + isolation
- Production repair rule: no staging-L5X mutation on real builds
- Auditor reject path still hard-fails half-built artifacts

Heavy rebuild lane (not imported into unit CI by default):
  python exports/delivery_gate_20261002/run_overnight_rc_qualification.py
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "exports" / "delivery_gate_20261002"
CURRENT = ROOT / "exports" / "current"
SCRIPTS = ROOT / "tools" / "scripts"
REPORT = GATE / "overnight_rc_qualification_report.json"
FINAL = GATE / "FINAL_SHA.txt"
CLAIMED = "f6e487021764e5893b4442aaeec90e3e14c7a559"

sys.path.insert(0, str(SCRIPTS))


def _latest(prefix: str) -> Path | None:
    cands = sorted(
        CURRENT.glob(f"{prefix}_*.L5X"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cands[0] if cands else None


def _load_report() -> dict | None:
    if not REPORT.is_file():
        return None
    return json.loads(REPORT.read_text(encoding="utf-8"))


class TestProductionRepairRule(unittest.TestCase):
    """Production ORI-111 must regenerate complete L5X — never patch staging."""

    def test_auditor_regenerate_contract_not_mutate(self) -> None:
        src = (SCRIPTS / "fortna_l5x_acceptance_auditor.py").read_text(encoding="utf-8")
        self.assertIn("regenerate_fn", src)
        # Advisory cannot mutate L5X
        self.assertIn("cannot mutate L5X", src)
        # Repair path records proposals then regenerates
        self.assertIn("run_acceptance_and_repair", src)

    def test_autonomous_repair_harness_is_fixture_only(self) -> None:
        harness = GATE / "run_autonomous_repair_proof.py"
        self.assertTrue(harness.is_file(), "repair proof harness missing")
        text = harness.read_text(encoding="utf-8")
        # Harness deliberately damages fixtures — must not be wired as production
        self.assertTrue(
            "Safe_PI" in text and ("strip" in text.lower() or "damage" in text.lower() or "mutate" in text.lower()),
            "harness must show fixture damage path",
        )
        # Must call regenerate path / acceptance loop, not silent CURRENT promote on FAIL
        self.assertIn("AUDIT_FAIL", text)
        self.assertIn("run_acceptance_and_repair", text)

    def test_autogen_promotes_only_after_audit_pass(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn("SITEFORGE_L5X_AUDITOR", src)
        self.assertIn("AUDIT_PASS", src)
        # Must reference staging before CURRENT
        self.assertTrue(
            "STAGING" in src or "staging" in src or "artifact_state" in src,
            "autogen missing staging/artifact_state promote path",
        )


class TestMscrenopickIntegrationArtifact(unittest.TestCase):
    """Assert CURRENT MSCRENOPICK L5X still carries I/O + one Area + ES Safety."""

    @unittest.skipUnless(_latest("MSCRENOPICK") is not None, "MSCRENOPICK L5X missing in CURRENT")
    def test_one_area_transport_programs(self) -> None:
        l5x = _latest("MSCRENOPICK")
        assert l5x is not None
        text = l5x.read_text(encoding="utf-8", errors="replace")
        for suffix in ("_Slow", "_Fast", "_L1", "_L2"):
            self.assertIn(f'Program Name="MSCRENOPICK_Area{suffix}"', text)
        # No invented extra Areas for ordinary transport
        areas = set(
            re.findall(r'<Program Name="((?:[^"]+)_Area)_(?:Slow|Fast|L1|L2)"', text)
        )
        self.assertEqual(areas, {"MSCRENOPICK_Area"})

    @unittest.skipUnless(_latest("MSCRENOPICK") is not None, "MSCRENOPICK L5X missing in CURRENT")
    def test_es_safety_populated(self) -> None:
        l5x = _latest("MSCRENOPICK")
        assert l5x is not None
        text = l5x.read_text(encoding="utf-8", errors="replace")
        self.assertIn('Program Name="ES"', text)
        for rn in (
            "Main_Routine",
            "MSCRENOPICK_ESZone1_Safe_Logic",
            "MSCRENOPICK_ESZone1_Safe_PI",
        ):
            m = re.search(
                rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
                text,
                re.S,
            )
            self.assertIsNotNone(m, f"missing routine {rn}")
            assert m is not None
            rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1), flags=re.S)
            nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
            self.assertTrue(nonempty, f"{rn} empty/NOP-only")
        for mem in ("ESPB2", "ESPB24", "ESPB32", "ESLS2"):
            self.assertRegex(text, rf"\b{mem}\b")

    @unittest.skipUnless(_latest("MSCRENOPICK") is not None, "MSCRENOPICK L5X missing in CURRENT")
    def test_io_map_program_present(self) -> None:
        l5x = _latest("MSCRENOPICK")
        assert l5x is not None
        text = l5x.read_text(encoding="utf-8", errors="replace")
        self.assertIn('Program Name="IO_MAP"', text)

    @unittest.skipUnless(_latest("MSCRENOPICK") is not None, "MSCRENOPICK L5X missing in CURRENT")
    def test_no_blank_operands(self) -> None:
        l5x = _latest("MSCRENOPICK")
        assert l5x is not None
        text = l5x.read_text(encoding="utf-8", errors="replace")
        bad = re.findall(
            r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
            text,
            flags=re.I,
        )
        self.assertEqual(bad, [], bad[:5])


class TestVirginSiteIsolation(unittest.TestCase):
    """ORINDYAC3 / TFCP1 CURRENT must not inherit MSCRENO residue."""

    def test_orindyac3_no_mscreno_residue(self) -> None:
        l5x = _latest("ORINDYAC3")
        if l5x is None:
            self.skipTest("ORINDYAC3 L5X missing in CURRENT")
        text = l5x.read_text(encoding="utf-8", errors="replace")
        for foreign in ("MSCRENOPICK", "MSCRENOSHIP", "MSCRENOPACK"):
            self.assertNotIn(foreign, text, f"foreign residue {foreign}")

    def test_tfcp1_no_mscreno_residue(self) -> None:
        l5x = _latest("TFCP1")
        if l5x is None:
            self.skipTest("TFCP1 L5X missing in CURRENT")
        text = l5x.read_text(encoding="utf-8", errors="replace")
        for foreign in ("MSCRENOPICK", "MSCRENOSHIP", "MSCRENOPACK"):
            self.assertNotIn(foreign, text, f"foreign residue {foreign}")


class TestOvernightRcReportContract(unittest.TestCase):
    """When overnight RC report exists, it must record YES/YES + no staging patch."""

    @unittest.skipUnless(REPORT.is_file(), "overnight RC report not yet produced")
    def test_report_yes_yes_and_no_staging_patch(self) -> None:
        rep = _load_report()
        assert rep is not None
        self.assertTrue(rep.get("qualification_complete"), rep)
        self.assertEqual(rep.get("CAN_CURTIS_OPEN_MSCRENOPICK"), "YES")
        self.assertEqual(rep.get("CAN_SAME_SHA_BUILD_ANOTHER_SITE"), "YES")
        self.assertEqual(
            rep.get("PRODUCTION_REPAIR_STAGING_L5X_PATCH_ON_REAL_BUILDS"), "NO"
        )
        self.assertEqual(rep.get("FINAL_PUSHED_SHA") or rep.get("claimed_sha"), CLAIMED)
        m = rep.get("mscrenopick") or {}
        self.assertTrue(m.get("pass"), m)
        self.assertTrue((m.get("io") or {}).get("accounted_equals_discovered"), m.get("io"))
        self.assertEqual((m.get("transportation") or {}).get("areas_expected"), ["MSCRENOPICK_Area"])
        s = m.get("safety") or {}
        self.assertTrue(s.get("Main_Routine"))
        self.assertTrue(s.get("Safe_Logic"))
        self.assertTrue(s.get("Safe_PI"))
        v = rep.get("virgin") or {}
        self.assertTrue(v.get("pass"), v)
        self.assertEqual(v.get("foreign_prior_site_residue_count"), 0)

    @unittest.skipUnless(FINAL.is_file(), "FINAL_SHA.txt missing")
    def test_final_sha_records_claimed(self) -> None:
        text = FINAL.read_text(encoding="utf-8")
        self.assertIn(f"FINAL_SHA={CLAIMED}", text)


class TestOrlAc3SafetyArtifact(unittest.TestCase):
    @unittest.skipUnless(_latest("ORL_AC3") is not None, "ORL_AC3 L5X missing")
    def test_orl_es_routines_populated(self) -> None:
        l5x = _latest("ORL_AC3")
        assert l5x is not None
        text = l5x.read_text(encoding="utf-8", errors="replace")
        self.assertIn('Program Name="ES"', text)
        main = re.search(
            r'<Routine Name="Main_Routine"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            text,
            re.S,
        )
        self.assertIsNotNone(main)
        assert main is not None
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", main.group(1), flags=re.S)
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        self.assertTrue(nonempty, "ORL_AC3 Main_Routine empty")


if __name__ == "__main__":
    unittest.main()
