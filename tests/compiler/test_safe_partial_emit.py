#!/usr/bin/env python3
"""SAFE PARTIAL EMIT — engineer-first quarantine contract (Tests A–G + helpers).

A local undefined tag must not kill an otherwise usable controller.
Safety-critical unresolved conditions fail closed.
True structural failures remain BLOCKED.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_build_issues import (  # noqa: E402
    SECTION_ORDER,
    build_issues_manifest,
    classify_build_status,
    render_build_issues_txt,
)
from fortna_rung_quarantine import (  # noqa: E402
    actionable_issue_count,
    quarantine_l5x,
)
from fortna_symbol_closure import check_symbol_closure  # noqa: E402


def _minimal_controller(
    *,
    extra_tags: str = "",
    programs: str = "",
    name: str = "TESTSITE",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="32.00">
<Controller Name="{name}" ProcessorType="1756-L82E" MajorRev="32" MinorRev="11">
<Tags>
<Tag Name="AlwaysOn" TagType="Base" DataType="BOOL"/>
<Tag Name="P15_Conv" TagType="Base" DataType="P3000_Conv"/>
{extra_tags}
</Tags>
<Programs>
{programs}
</Programs>
</Controller>
</RSLogix5000Content>
"""


def _program(name: str, routines: str) -> str:
    return f"""<Program Name="{name}" TestEdits="false" MainRoutineName="Main" Disabled="false">
<Tags/>
<Routines>
{routines}
</Routines>
</Program>"""


def _routine(name: str, rungs: str) -> str:
    return f"""<Routine Name="{name}" Type="RLL">
<RLLContent>
{rungs}
</RLLContent>
</Routine>"""


def _rung(n: int, text: str) -> str:
    return f"""<Rung Number="{n}" Type="N">
<Text><![CDATA[{text}]]></Text>
</Rung>"""


class TestALocalUndefinedTag(unittest.TestCase):
    """TEST A — local undefined tag → PARTIAL, Program/Routine retained, NOP placeholder."""

    def test_a_local_undefined_quarantined_not_blocked(self) -> None:
        programs = _program(
            "TESTSITE_Area_Slow",
            _routine(
                "Area_Logic",
                _rung(0, "XIC(AlwaysOn)OTE(P15_Conv.O.Run);")
                + _rung(3, "XIO(SomeUndefinedTag.Member)OTE(P15_Conv.O.Fault);"),
            ),
        )
        l5x = _minimal_controller(programs=programs)
        q = quarantine_l5x(l5x)
        self.assertTrue(q.ok)
        self.assertFalse(q.blocked)
        self.assertGreaterEqual(q.quarantined_rung_count, 1)
        self.assertIn("NOP();", q.l5x_text)
        self.assertIn("SITE FORGE ISSUE SF-", q.l5x_text)
        self.assertIn('Program Name="TESTSITE_Area_Slow"', q.l5x_text)
        self.assertIn('Routine Name="Area_Logic"', q.l5x_text)
        # Invalid operand must not remain as live Text logic (comment may retain it).
        live = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", q.l5x_text, re.S)
        self.assertFalse(any("SomeUndefinedTag" in t for t in live))
        # Valid sibling rung retained.
        self.assertIn("XIC(AlwaysOn)OTE(P15_Conv.O.Run);", q.l5x_text)

        issue = next(i for i in q.issues if "SomeUndefinedTag" in i.operand)
        self.assertEqual(issue.program, "TESTSITE_Area_Slow")
        self.assertEqual(issue.routine, "Area_Logic")
        self.assertEqual(issue.rung, "3")
        self.assertIn("SomeUndefinedTag", issue.operand)
        self.assertEqual(issue.site_forge_action, "QUARANTINED")

        # Post-quarantine symbol closure must be clean for hard failures.
        closure = check_symbol_closure(q.l5x_text)
        self.assertTrue(closure.ok)

        report = {
            "ok": True,
            "build_failed": False,
            "generation_assertions": {"ok": True, "failures": []},
            "symbol_closure": closure.to_dict(),
            "studio_preflight": {"ok": True, "issues": []},
            "rung_quarantine": q.to_dict(),
            "runnability": {"COMMISSIONING_READY": "NO"},
        }
        self.assertEqual(
            classify_build_status(report, structural_ok=True, promoted=True),
            "PARTIAL",
        )
        manifest = build_issues_manifest(
            report,
            site="TESTSITE",
            l5x_generated=True,
            l5x_promoted=True,
            build_status="PARTIAL",
            commissioning_ready="NO",
        )
        self.assertEqual(manifest["BUILD STATUS"], "PARTIAL")
        self.assertFalse(manifest["BLOCKERS"])
        self.assertTrue(manifest["QUARANTINED LOGIC"])
        txt = render_build_issues_txt(manifest)
        self.assertIn("Program:", txt)
        self.assertIn("TESTSITE_Area_Slow", txt)
        self.assertIn("Area_Logic", txt)
        self.assertIn("SomeUndefinedTag", txt)


class TestBDeviceFunctionFailure(unittest.TestCase):
    """TEST B — unresolved device-specific function withheld; rest survives."""

    def test_b_device_function_quarantined(self) -> None:
        programs = (
            _program(
                "TESTSITE_Area_Fast",
                _routine(
                    "Device_Logic",
                    _rung(0, "XIC(AlwaysOn)OTE(P15_Conv.O.Run);")
                    + _rung(1, "XIC(UnresolvedDivert99.Cmd)OTE(UnresolvedDivert99.Fired);"),
                ),
            )
            + _program(
                "TESTSITE_Other",
                _routine("Keep_Alive", _rung(0, "XIC(AlwaysOn)NOP();")),
            )
        )
        l5x = _minimal_controller(programs=programs)
        q = quarantine_l5x(l5x)
        self.assertTrue(q.ok)
        self.assertFalse(q.blocked)
        self.assertIn('Program Name="TESTSITE_Area_Fast"', q.l5x_text)
        self.assertIn('Program Name="TESTSITE_Other"', q.l5x_text)
        self.assertIn("XIC(AlwaysOn)OTE(P15_Conv.O.Run);", q.l5x_text)
        live = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", q.l5x_text, re.S)
        self.assertFalse(any("UnresolvedDivert99" in t for t in live))
        devices = {i.object_device for i in q.issues}
        self.assertTrue(any("UnresolvedDivert99" in d for d in devices))
        self.assertTrue(check_symbol_closure(q.l5x_text).ok)


class TestCSafetyCriticalUnresolved(unittest.TestCase):
    """TEST C — unresolved Safety/run permissive → FAIL_CLOSED; motion not enabled."""

    def test_c_safety_fail_closed(self) -> None:
        programs = _program(
            "TESTSITE_Area_Slow",
            _routine(
                "Area_Logic",
                _rung(0, "XIC(AlwaysOn)OTE(P15_Conv.O.Fault);")
                + _rung(
                    2,
                    "XIO(Default_Safety.PI.Tripped)XIC(AlwaysOn)OTE(Area.Run);",
                ),
            ),
        )
        l5x = _minimal_controller(programs=programs)
        q = quarantine_l5x(l5x)
        self.assertTrue(q.ok)
        self.assertFalse(q.blocked)
        self.assertGreaterEqual(q.fail_closed_count, 1)
        # Motion enable via unresolved Safety must not survive as live Text logic.
        live = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", q.l5x_text, re.S)
        self.assertFalse(any("Default_Safety.PI.Tripped" in t for t in live))
        self.assertFalse(any("OTE(Area.Run)" in t for t in live))
        self.assertIn("NOP();", q.l5x_text)
        self.assertIn("XIC(AlwaysOn)OTE(P15_Conv.O.Fault);", q.l5x_text)
        fc = next(i for i in q.issues if i.site_forge_action == "FAIL_CLOSED")
        self.assertEqual(fc.program, "TESTSITE_Area_Slow")
        self.assertEqual(fc.routine, "Area_Logic")
        self.assertEqual(fc.effect, "COMMISSIONING")
        report = {
            "ok": True,
            "build_failed": False,
            "generation_assertions": {"ok": True, "failures": []},
            "symbol_closure": check_symbol_closure(q.l5x_text).to_dict(),
            "studio_preflight": {"ok": True, "issues": []},
            "rung_quarantine": q.to_dict(),
            "runnability": {"COMMISSIONING_READY": "NO"},
        }
        self.assertEqual(
            classify_build_status(report, structural_ok=True, promoted=True),
            "PARTIAL",
        )
        manifest = build_issues_manifest(
            report, site="TESTSITE", l5x_generated=True, build_status="PARTIAL"
        )
        self.assertEqual(manifest["COMMISSIONING READY"], "NO")
        self.assertTrue(manifest["SAFETY"] or manifest["QUARANTINED LOGIC"])


class TestDTrueStructuralFailure(unittest.TestCase):
    """TEST D — malformed/unrecoverable → BLOCKED; no engineer-facing promote."""

    def test_d_empty_l5x_blocked(self) -> None:
        q = quarantine_l5x("")
        self.assertFalse(q.ok)
        self.assertTrue(q.blocked)
        self.assertTrue(q.structural_blockers)

    def test_d_no_controller_blocked(self) -> None:
        q = quarantine_l5x("<RSLogix5000Content></RSLogix5000Content>")
        self.assertFalse(q.ok)
        self.assertTrue(q.blocked)
        report = {
            "ok": False,
            "build_failed": True,
            "rung_quarantine": q.to_dict(),
            "symbol_closure": {"ok": False, "failures": [{"error": "no controller"}]},
        }
        self.assertEqual(
            classify_build_status(report, structural_ok=False, promoted=False),
            "BLOCKED",
        )


class TestEIssueButtonCount(unittest.TestCase):
    """TEST E — actionable issue count drives PLC ISSUES / COMPILE ERRORS (N)."""

    def test_e_six_actionable_issues_count(self) -> None:
        issues = []
        for i in range(6):
            issues.append(
                {
                    "issue_id": f"SF-{i+1:04d}",
                    "CATEGORY": "QUARANTINED LOGIC",
                    "SEVERITY": "UNDECLARED_OPERAND",
                    "PROGRAM": "P",
                    "ROUTINE": "R",
                    "RUNG NUMBER / RUNG INDEX": str(i),
                    "OBJECT / DEVICE": f"Tag{i}",
                    "OPERAND / TAG / ENDPOINT": f"Tag{i}.X",
                    "REASON": "planted",
                    "SOURCE / PROVENANCE": "test",
                    "SITE FORGE ACTION": "QUARANTINED",
                    "ENGINEER ACTION": "fix",
                    "EFFECT": "LOCAL",
                    "object/device": f"Tag{i}",
                    "what Site Forge did": "QUARANTINED",
                    "reason": "planted",
                    "engineer action": "fix",
                    "effect": "LOCAL",
                    "program": "P",
                    "routine": "R",
                    "rung": str(i),
                    "operand": f"Tag{i}.X",
                }
            )
        report = {
            "ok": True,
            "build_failed": False,
            "generation_assertions": {"ok": True, "failures": []},
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
            "studio_preflight": {"ok": True, "issues": []},
            "rung_quarantine": {
                "ok": True,
                "blocked": False,
                "issue_count": 6,
                "issues": issues,
                "quarantined_rung_count": 6,
                "fail_closed_count": 0,
                "structural_blockers": [],
            },
        }
        manifest = build_issues_manifest(
            report,
            site="TESTSITE",
            l5x_generated=True,
            l5x_promoted=True,
            build_status="PARTIAL",
            l5x_path=r"C:\exports\current\TESTSITE_2026_10_01.L5X",
        )
        # Each quarantine issue is mirrored into QUARANTINED LOGIC + PLC COMPILE.
        n = actionable_issue_count(manifest)
        self.assertGreaterEqual(n, 6)
        self.assertEqual(manifest["actionable_issue_count"], n)
        label = f"PLC ISSUES / COMPILE ERRORS ({n})"
        self.assertIn("PLC ISSUES / COMPILE ERRORS (", label)
        self.assertTrue(manifest["l5x_path"].endswith(".L5X"))


class TestFOutputPath(unittest.TestCase):
    """TEST F — manifest carries exact engineer-facing L5X path."""

    def test_f_l5x_path_in_manifest_and_txt(self) -> None:
        path = r"C:\dev\exports\current\TESTSITE_2026_10_01_1200.L5X"
        manifest = build_issues_manifest(
            {
                "ok": True,
                "build_failed": False,
                "generation_assertions": {"ok": True, "failures": []},
                "symbol_closure": {"ok": True, "failures": []},
                "studio_preflight": {"ok": True, "issues": []},
                "merges_withheld_review": ["P1-P2"],
            },
            site="TESTSITE",
            l5x_generated=True,
            l5x_promoted=True,
            l5x_path=path,
            build_status="PARTIAL",
        )
        self.assertEqual(manifest["l5x_path"], path)
        txt = render_build_issues_txt(manifest)
        self.assertIn(path, txt)
        self.assertIn("L5X path:", txt)


class TestGRoutineCompleteness(unittest.TestCase):
    """TEST G — unsupported/empty routine retained with valid placeholder."""

    def test_g_empty_rll_gets_placeholder(self) -> None:
        programs = _program(
            "TESTSITE_Sorter",
            _routine("Sorter_Track", ""),  # empty RLLContent
        )
        l5x = _minimal_controller(programs=programs)
        q = quarantine_l5x(l5x)
        self.assertTrue(q.ok)
        self.assertFalse(q.blocked)
        self.assertIn('Program Name="TESTSITE_Sorter"', q.l5x_text)
        self.assertIn('Routine Name="Sorter_Track"', q.l5x_text)
        self.assertIn("NOP();", q.l5x_text)
        self.assertIn("SITE FORGE ISSUE SF-", q.l5x_text)
        self.assertTrue(any(i.severity == "ROUTINE_INCOMPLETE" for i in q.issues))
        # No undeclared operands introduced by the placeholder.
        closure = check_symbol_closure(q.l5x_text)
        self.assertTrue(closure.ok)


class TestJsrSchedulerPreserved(unittest.TestCase):
    """JSR routine targets are not tags — must not be quarantined."""

    def test_jsr_call_structure_retained(self) -> None:
        programs = _program(
            "TESTSITE_Area_Slow",
            _routine("Main_Routine", _rung(0, "JSR(Area_Logic);") + _rung(1, "JSR(Conv_PI);"))
            + _routine(
                "Area_Logic",
                _rung(0, "XIC(AlwaysOn)OTE(P15_Conv.O.Run);")
                + _rung(1, "XIO(SomeUndefinedTag.Member)OTE(P15_Conv.O.Fault);"),
            )
            + _routine("Conv_PI", _rung(0, "XIC(AlwaysOn)NOP();")),
        )
        l5x = _minimal_controller(programs=programs)
        q = quarantine_l5x(l5x)
        self.assertTrue(q.ok)
        self.assertFalse(q.blocked)
        live = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", q.l5x_text, re.S)
        self.assertTrue(any("JSR(Area_Logic)" in t for t in live))
        self.assertTrue(any("JSR(Conv_PI)" in t for t in live))
        self.assertFalse(any("SomeUndefinedTag" in t for t in live))
        # Only the undefined-tag rung quarantined — not the JSR scheduler.
        self.assertEqual(q.quarantined_rung_count, 1)
        self.assertEqual(q.issues[0].operand, "SomeUndefinedTag.Member")


class TestSectionOrderContract(unittest.TestCase):
    def test_required_sections_present(self) -> None:
        for name in (
            "BLOCKERS",
            "PLC COMPILE / SYMBOL ISSUES",
            "QUARANTINED LOGIC",
            "WITHHELD FROM L5X",
            "SAFETY",
        ):
            self.assertIn(name, SECTION_ORDER)


class TestExampleIssuePunchList(unittest.TestCase):
    """Return-contract example: Program/Routine/Rung/Operand/Action fields."""

    def test_example_issue_fields(self) -> None:
        programs = _program(
            "MSCRENOPICK_Area_Slow",
            _routine(
                "Area_Logic",
                _rung(3, "XIO(Default_Safety.PI.Tripped)OTE(P15_Conv.O.Fault);"),
            ),
        )
        l5x = _minimal_controller(programs=programs, name="MSCRENOPICK")
        q = quarantine_l5x(l5x)
        self.assertTrue(q.issues)
        issue = q.issues[0]
        self.assertEqual(issue.program, "MSCRENOPICK_Area_Slow")
        self.assertEqual(issue.routine, "Area_Logic")
        self.assertEqual(issue.rung, "3")
        self.assertIn("Default_Safety", issue.operand)
        self.assertTrue(issue.reason)
        self.assertIn(issue.site_forge_action, {"QUARANTINED", "FAIL_CLOSED"})
        self.assertTrue(issue.engineer_action)
        manifest = build_issues_manifest(
            {
                "ok": True,
                "rung_quarantine": q.to_dict(),
                "symbol_closure": {"ok": True, "failures": []},
                "studio_preflight": {"ok": True, "issues": []},
                "generation_assertions": {"ok": True, "failures": []},
            },
            site="MSCRENOPICK",
            git_sha="be05edc7",
            tar_hash="abc123",
            run_fingerprint="runfp",
            build_id="build1",
            l5x_generated=True,
            build_status="PARTIAL",
        )
        txt = render_build_issues_txt(manifest)
        self.assertIn("MSCRENOPICK_Area_Slow", txt)
        self.assertIn("Area_Logic", txt)
        self.assertIn("Engineer action:", txt)
        self.assertIn("Site Forge action:", txt)


if __name__ == "__main__":
    unittest.main()
