#!/usr/bin/env python3
"""Permanent ORI-111 L5X acceptance auditor gates.

Proves:
1. Good MSCRENOPICK L5X → AUDIT_PASS
2. Deliberately damaged fixtures → AUDIT_FAIL (required reject set)
3. Loop protection: duplicate material hash refused; 3 material attempts → GENERATOR_DEFECT
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

from fortna_l5x_acceptance_auditor import (  # noqa: E402
    MAX_ATTEMPTS_PER_SIGNATURE,
    RepairAttempt,
    RepairLoopState,
    STATE_AUDIT_FAIL,
    STATE_AUDIT_PASS,
    STATE_GENERATOR_DEFECT,
    audit_l5x,
    build_expected_artifact_manifest,
    failure_signature,
    material_hash,
    run_acceptance_and_repair,
    write_generator_defect_case,
)

CURRENT = ROOT / "exports" / "current"
GOOD_L5X = next(
    iter(sorted(CURRENT.glob("MSCRENOPICK_*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True)),
    CURRENT / "MSCRENOPICK_MISSING.L5X",
)


class _FakeInp:
    machine = "MSCRENOPICK"
    project_name = "MSCRENOPICK"
    areas = ["MSCRENOPICK_Area"]
    include_io_map = True
    conveyors = [object()] * 47
    safety_zone_members = [
        {
            "name": "MSCRENOPICK_ESZone1",
            "status": "READY",
            "operational": True,
            "membersOrigin": "ENGINEER_ASSIGNED",
            "members": ["ESPB2", "ESPB24", "ESPB32", "ESLS2"],
            "area": "MSCRENOPICK_Area",
        }
    ]


def _manifest() -> dict:
    return build_expected_artifact_manifest(
        _FakeInp(), report={"conveyor_count": 47, "include_io_map": True}
    )


def _mutate(text: str, kind: str) -> str:
    if kind == "strip_safe_logic":
        return re.sub(
            r'<Routine Name="MSCRENOPICK_ESZone1_Safe_Logic"[^>]*>.*?</Routine>',
            "",
            text,
            count=1,
            flags=re.S,
        )
    if kind == "strip_safe_pi":
        return re.sub(
            r'<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"[^>]*>.*?</Routine>',
            "",
            text,
            count=1,
            flags=re.S,
        )
    if kind == "empty_main":
        # Operate only inside ES program body
        es = re.search(r'(<Program Name="ES"[^>]*>)(.*?)(</Program>)', text, re.S)
        if not es:
            return text
        body = es.group(2)
        body2 = re.sub(
            r'(<Routine Name="Main_Routine"[^>]*>.*?<RLLContent>).*?(</RLLContent>)',
            r"\1\2",
            body,
            count=1,
            flags=re.S,
        )
        return text[: es.start()] + es.group(1) + body2 + es.group(3) + text[es.end() :]
    if kind == "strip_io_map":
        return re.sub(
            r'<Program Name="IO_MAP"[^>]*>.*?</Program>',
            "",
            text,
            count=1,
            flags=re.S,
        )
    if kind == "empty_fast":
        # Empty all routines inside Area_Fast program
        def _empty_fast_prog(m: re.Match) -> str:
            body = m.group(0)
            body = re.sub(
                r"(<RLLContent>).*?(</RLLContent>)",
                r"\1<Rung Number=\"0\" Type=\"N\"><Text><![CDATA[NOP();]]></Text></Rung>\2",
                body,
                flags=re.S,
            )
            return body

        return re.sub(
            r'<Program Name="[^"]*_Fast"[^>]*>.*?</Program>',
            _empty_fast_prog,
            text,
            count=1,
            flags=re.S,
        )
    if kind == "blank_operand":
        # Inject into ES Main_Routine first rung text if possible
        return text.replace(
            "JSR(MSCRENOPICK_ESZone1_Safe_Logic,0);",
            "XIC()JSR(MSCRENOPICK_ESZone1_Safe_Logic,0);",
            1,
        )
    if kind == "foreign_residue":
        # Inject a foreign zone Name attribute
        return text.replace(
            'Name="MSCRENOPICK_ESZone1"',
            'Name="MSCRENOPICK_ESZone1" Desc="x"/><!-- Name="MSCRENOSHIP" -->',
            1,
        ).replace(
            "</Controller>",
            '<Tag Name="MSCRENOSHIP_ESZone1" TagType="Base" DataType="BOOL"></Tag></Controller>',
            1,
        )
    raise ValueError(kind)


@unittest.skipUnless(GOOD_L5X.is_file(), "MSCRENOPICK L5X missing under exports/current")
class TestAuditorAcceptsGoodMscrenopick(unittest.TestCase):
    def test_good_l5x_audit_pass(self) -> None:
        r = audit_l5x(GOOD_L5X, _manifest())
        self.assertEqual(r["status"], STATE_AUDIT_PASS, r.get("failures"))
        self.assertTrue(r["ok"])


@unittest.skipUnless(GOOD_L5X.is_file(), "MSCRENOPICK L5X missing under exports/current")
class TestAuditorRejectsBadFixtures(unittest.TestCase):
    """Each damaged fixture must produce AUDIT_FAIL with the expected signature family."""

    CASES = [
        ("strip_safe_logic", "SAFETY:MISSING_SAFE_LOGIC"),
        ("strip_safe_pi", "SAFETY:MISSING_SAFE_PI"),
        ("empty_main", "SAFETY:BLANK_MAIN_ROUTINE"),
        ("strip_io_map", "IO:MISSING_PROGRAM"),
        ("empty_fast", "TRANSPORT:EMPTY_CORE"),
        ("blank_operand", "LOGIX:BLANK_OPERAND"),
        ("foreign_residue", "RESIDUE:FOREIGN_SITE"),
    ]

    def test_all_required_rejects(self) -> None:
        raw = GOOD_L5X.read_text(encoding="utf-8", errors="replace")
        man = _manifest()
        rejected = 0
        for kind, sig_prefix in self.CASES:
            with self.subTest(kind=kind):
                damaged = _mutate(raw, kind)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / f"bad_{kind}.L5X"
                    p.write_text(damaged, encoding="utf-8")
                    r = audit_l5x(p, man)
                    self.assertEqual(r["status"], STATE_AUDIT_FAIL, r)
                    sigs = " | ".join(r.get("signatures") or [])
                    self.assertTrue(
                        any(s.startswith(sig_prefix) for s in (r.get("signatures") or [])),
                        f"{kind}: expected prefix {sig_prefix} in {sigs}",
                    )
                    rejected += 1
        self.assertEqual(rejected, len(self.CASES))


class TestLoopProtection(unittest.TestCase):
    def test_duplicate_material_hash_refused(self) -> None:
        loop = RepairLoopState(max_per_signature=3)
        sig = failure_signature("SAFETY:MISSING_SAFE_PI", zone="Z1")
        mat = material_hash({"a": 1})
        loop.record(
            RepairAttempt(
                signature=sig,
                material_hash=mat,
                level=1,
                disposition="X",
                ts="t",
            )
        )
        ok, why = loop.can_retry(sig, mat)
        self.assertFalse(ok)
        self.assertEqual(why, "DUPLICATE_MATERIAL_HASH")

    def test_three_material_attempts_generator_defect(self) -> None:
        loop = RepairLoopState(max_per_signature=MAX_ATTEMPTS_PER_SIGNATURE)
        sig = failure_signature("TRANSPORT:EMPTY_CORE", program="Area_Fast")
        for i in range(MAX_ATTEMPTS_PER_SIGNATURE):
            mat = material_hash({"attempt": i, "ai": f"answer-{i}"})
            ok, why = loop.can_retry(sig, mat)
            self.assertTrue(ok, why)
            loop.record(
                RepairAttempt(
                    signature=sig,
                    material_hash=mat,
                    level=2,
                    disposition="FAIL",
                    ts="t",
                )
            )
        self.assertTrue(loop.exhausted(sig))
        ok, why = loop.can_retry(sig, material_hash({"attempt": 99}))
        self.assertFalse(ok)
        self.assertEqual(why, "MAX_MATERIAL_ATTEMPTS")

        with tempfile.TemporaryDirectory() as td:
            # Need a real file for sha
            l5x = Path(td) / "x.L5X"
            l5x.write_text("<RSLogix5000Content/>", encoding="utf-8")
            case = write_generator_defect_case(
                Path(td),
                manifest={"machine": "TEST"},
                signature=sig,
                tickets=[{"signature": sig}],
                attempts=loop.attempts_by_signature[sig],
                l5x_paths=[l5x, l5x],
                ai_responses=[{"n": 1}],
                relay_responses=[{"n": 1}],
            )
            self.assertTrue(case.is_file())
            text = case.read_text(encoding="utf-8")
            self.assertIn("GENERATOR_DEFECT", text)
            self.assertIn(sig, text)

    def test_run_acceptance_stops_without_regen_on_fail(self) -> None:
        """Without regenerate_fn, AUDIT_FAIL is preserved (no silent promote)."""
        if not GOOD_L5X.is_file():
            self.skipTest("no MSCRENOPICK L5X")
        raw = GOOD_L5X.read_text(encoding="utf-8", errors="replace")
        damaged = _mutate(raw, "strip_safe_pi")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.L5X"
            p.write_text(damaged, encoding="utf-8")
            r = run_acceptance_and_repair(
                l5x_path=p,
                manifest=_manifest(),
                out_dir=td,
                regenerate_fn=None,
                live=False,
            )
            self.assertFalse(r.get("ok"))
            self.assertIn(r.get("status"), (STATE_AUDIT_FAIL, STATE_GENERATOR_DEFECT))
            self.assertFalse(r.get("promoted"))


if __name__ == "__main__":
    unittest.main()
