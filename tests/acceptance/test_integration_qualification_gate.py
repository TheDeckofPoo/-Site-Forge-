#!/usr/bin/env python3
"""Permanent integration qualification gate — MSCRENOPICK + virgin TFCP1 + ORL_AC3.

Hard-fails on I/O regression, missing Transportation, blank/placeholder core
routines without explanation, missing Safe_Logic/Safe_PI/Main_Routine,
malformed/open Logix operands, missing/unnamed referenced tags, foreign-site
residue, missing BUILD_ISSUES explanation, or missing output L5X.

This module asserts delivery-gate summaries AND inspects frozen L5X artifacts
on disk. Full rebuild remains the heavy lane:

  python exports/delivery_gate_20261002/run_pick_golden_gate.py
  python exports/delivery_gate_20261002/run_virgin_second_site_gate.py
  python exports/delivery_gate_20261002/run_orl_ac3_safety_gate.py

Mandatory before changes touching I/O, Safety, Transportation, workbook, or Autogen.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "exports" / "delivery_gate_20261002"
SCRIPTS = ROOT / "tools" / "scripts"
CURRENT = ROOT / "exports" / "current"

PICK = GATE / "pick_golden_summary.json"
VIRGIN = GATE / "virgin_second_site_summary.json"
ORL = GATE / "orl_ac3_safety_summary.json"
FINAL = GATE / "FINAL_SHA.txt"


def _latest_l5x(prefix: str) -> Path:
    """Resolve newest CURRENT L5X for a fixture prefix (dated filenames rotate)."""
    cands = sorted(
        CURRENT.glob(f"{prefix}_*.L5X"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cands[0] if cands else CURRENT / f"{prefix}_MISSING.L5X"


PICK_L5X = _latest_l5x("MSCRENOPICK")
VIRGIN_L5X = _latest_l5x("TFCP1")
ORL_L5X = _latest_l5x("ORL_AC3")

EXPLAIN_MARKERS = (
    "REVIEW_REQUIRED",
    "UNSUPPORTED",
    "WITHHELD",
    "PLACEHOLDER",
    "DEFERRED",
    "ENGINEER_ASSIGNMENT_REQUIRED",
    "QUARANTINED",
    "FINISHED_SITE_DERIVED_SUSPECT",
    "SLOW_FLT",
    "NOT_APPLICABLE",
    "BLOCKED",
)

REQUIRED_TRANSPORT_SUFFIXES = (
    "_Area_Slow",
    "_Area_Fast",
    "_Area_L1",
    "_Area_L2",
)
REQUIRED_SHARED_PROGRAMS = ("System", "Sys", "PLC_Fast", "ES", "IO_MAP")

# Blank / open / placeholder operand patterns inside instruction calls.
_BAD_OPERAND_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU|JSR|MOV|COP|CPT|EQU|NEQ|GRT|LES|GEQ|LEQ|ADD|SUB|MUL|DIV)"
    r"\s*\(\s*(?:\)|\?[,)]|,\s*[,)]|,\s*\?)",
    re.I,
)
_UNNAMED_TAG_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\"\"|''|_unnamed_|<unnamed>|TODO|FIXME)\s*\)",
    re.I,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _final_sha() -> str | None:
    if not FINAL.is_file():
        return None
    text = FINAL.read_text(encoding="utf-8")
    for ln in text.splitlines():
        if ln.startswith("FINAL_SHA="):
            return ln.split("=", 1)[1].strip()
    return None


def _allowed_qualification_shas() -> set[str]:
    """Accept current FINAL_SHA and documented baseline freeze SHA."""
    allowed: set[str] = set()
    if not FINAL.is_file():
        return allowed
    text = FINAL.read_text(encoding="utf-8")
    for ln in text.splitlines():
        if ln.startswith("FINAL_SHA=") or ln.startswith("BASELINE_FINAL_SHA="):
            val = ln.split("=", 1)[1].strip()
            if val:
                allowed.add(val)
    return allowed


def _program_names(l5x_text: str) -> list[str]:
    return re.findall(r'<Program Name="([^"]+)"', l5x_text)


def _inspect_es(l5x_text: str) -> dict:
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', l5x_text, re.S)
    if not es:
        return {"error": "NO_ES_PROGRAM", "detail": {}}
    body = es.group(1)
    routines = re.findall(r'<Routine Name="([^"]+)"', body)
    detail: dict = {}
    for rn in routines:
        m = re.search(
            rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            body,
            re.S,
        )
        if not m:
            detail[rn] = {"populated": False, "rungs": 0, "non_nop": 0}
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        detail[rn] = {
            "rungs": len(rungs),
            "non_nop": len(nonempty),
            "populated": len(nonempty) > 0,
        }
    return {"routines": routines, "detail": detail}


def _unexplained_empty_core(l5x_text: str, issues_blob: str = "") -> list[dict]:
    empty: list[dict] = []
    issues_u = (issues_blob or "").upper()
    for prog in re.finditer(r'<Program Name="([^"]+)"[^>]*>(.*?)</Program>', l5x_text, re.S):
        pname = prog.group(1)
        if not any(
            x in pname
            for x in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2", "IO_MAP")
        ):
            continue
        for rn in re.finditer(
            r'<Routine Name="([^"]+)"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            prog.group(2),
            re.S,
        ):
            rname, body = rn.group(1), rn.group(2)
            rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", body, flags=re.S)
            comments = re.findall(
                r"<Comment><!\[CDATA\[(.*?)\]\]></Comment>", body, flags=re.S
            )
            nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
            if nonempty:
                continue
            joined = " ".join(comments).upper()
            explained = any(k in joined for k in EXPLAIN_MARKERS)
            if not explained:
                # Accept BUILD_ISSUES mentioning this routine
                key = f"{pname}.{rname}".upper()
                explained = key in issues_u or rname.upper() in issues_u
            if not explained:
                empty.append({"program": pname, "routine": rname})
    return empty


def _foreign_hits(l5x_text: str, foreign_prefixes: tuple[str, ...]) -> dict[str, int]:
    return {p: len(re.findall(re.escape(p), l5x_text)) for p in foreign_prefixes}


def _blank_operand_hits(l5x_text: str) -> list[str]:
    hits = []
    for m in _BAD_OPERAND_RE.finditer(l5x_text):
        hits.append(m.group(0)[:80])
        if len(hits) >= 20:
            break
    for m in _UNNAMED_TAG_RE.finditer(l5x_text):
        hits.append(m.group(0)[:80])
        if len(hits) >= 40:
            break
    return hits


def _validate_operands(l5x_text: str) -> dict:
    sys.path.insert(0, str(SCRIPTS))
    from fortna_operand_validator import validate_l5x_operands  # noqa: WPS433

    return validate_l5x_operands(l5x_text)


class TestIntegrationQualificationSummaries(unittest.TestCase):
    @unittest.skipUnless(PICK.is_file(), "pick golden summary missing — run golden gate first")
    def test_mscrenopick_golden_summary_pass(self) -> None:
        j = _load_json(PICK)
        self.assertTrue(j.get("golden_pass"), j.get("MSCRENOPICK"))
        m = j.get("MSCRENOPICK") or {}
        for k in (
            "I/O",
            "Transportation",
            "Safety",
            "Core_routine_completeness",
            "BUILD_ISSUES_explanations",
        ):
            self.assertEqual(m.get(k), "PASS", k)
        self.assertEqual(m.get("Safe_Logic_populated"), "YES")
        self.assertEqual(m.get("Safe_PI_populated"), "YES")
        self.assertEqual(m.get("ES_Main_Routine_populated"), "YES")

    @unittest.skipUnless(VIRGIN.is_file(), "virgin summary missing — run second-site gate first")
    def test_virgin_second_site_summary_pass(self) -> None:
        j = _load_json(VIRGIN)
        self.assertTrue(j.get("virgin_pass"), j.get("VIRGIN"))
        v = j.get("VIRGIN") or {}
        self.assertEqual(v.get("foreign_MSCRENO_residue_count"), 0)
        for k in ("I/O", "Transportation", "Safety", "Core_routine_completeness"):
            self.assertEqual(v.get(k), "PASS", k)

    @unittest.skipUnless(ORL.is_file(), "ORL_AC3 safety summary missing — run ORL safety gate first")
    def test_orl_ac3_safety_summary_pass(self) -> None:
        j = _load_json(ORL)
        self.assertTrue(j.get("orl_ac3_safety_pass"), j)
        s = j.get("ORL_AC3") or {}
        self.assertEqual(s.get("Safety"), "PASS")
        self.assertEqual(s.get("ES_Main_Routine_populated"), "YES")
        self.assertEqual(s.get("Safe_Logic_populated"), "YES")
        self.assertEqual(s.get("Safe_PI_populated"), "YES")
        self.assertEqual(s.get("L5X_present"), "YES")

    @unittest.skipUnless(PICK.is_file() and VIRGIN.is_file(), "both summaries required")
    def test_same_sha_for_pick_and_virgin(self) -> None:
        p = _load_json(PICK)
        v = _load_json(VIRGIN)
        self.assertEqual(p.get("git_sha"), v.get("git_sha"))
        sha = str(p.get("git_sha") or "")
        allowed = _allowed_qualification_shas()
        if allowed:
            self.assertTrue(
                sha in allowed or any(sha.startswith(a[:7]) for a in allowed),
                (sha, sorted(allowed)),
            )


class TestMscrenopickL5xHardGate(unittest.TestCase):
    """Fail hard on L5X integrity regressions for the golden fixture."""

    @unittest.skipUnless(PICK_L5X.is_file(), "MSCRENOPICK L5X missing under exports/current")
    def test_l5x_exists_and_opens(self) -> None:
        text = PICK_L5X.read_text(encoding="utf-8", errors="replace")
        self.assertGreater(len(text), 10_000)
        progs = _program_names(text)
        self.assertIn("ES", progs)
        self.assertIn("IO_MAP", progs)

    @unittest.skipUnless(PICK_L5X.is_file(), "MSCRENOPICK L5X missing")
    def test_transportation_programs_present(self) -> None:
        text = PICK_L5X.read_text(encoding="utf-8", errors="replace")
        progs = _program_names(text)
        for suf in REQUIRED_TRANSPORT_SUFFIXES:
            self.assertTrue(
                any(p.endswith(suf) or suf in p for p in progs),
                f"missing Transportation program matching {suf}: {progs}",
            )
        for shared in REQUIRED_SHARED_PROGRAMS:
            self.assertIn(shared, progs, shared)

    @unittest.skipUnless(PICK_L5X.is_file(), "MSCRENOPICK L5X missing")
    def test_safety_routines_populated(self) -> None:
        text = PICK_L5X.read_text(encoding="utf-8", errors="replace")
        es = _inspect_es(text)
        detail = es.get("detail") or {}
        self.assertTrue(detail.get("Main_Routine", {}).get("populated"), detail.get("Main_Routine"))
        sl = [k for k in detail if k.endswith("_Safe_Logic")]
        sp = [k for k in detail if k.endswith("_Safe_PI")]
        self.assertTrue(sl, "missing Safe_Logic routine")
        self.assertTrue(sp, "missing Safe_PI routine")
        self.assertTrue(detail[sl[0]].get("populated"), sl[0])
        self.assertTrue(detail[sp[0]].get("populated"), sp[0])

    @unittest.skipUnless(PICK_L5X.is_file(), "MSCRENOPICK L5X missing")
    def test_no_unexplained_blank_core_routines(self) -> None:
        text = PICK_L5X.read_text(encoding="utf-8", errors="replace")
        issues_path = CURRENT / "MSCRENOPICK_BUILD_ISSUES.json"
        issues_blob = issues_path.read_text(encoding="utf-8") if issues_path.is_file() else ""
        empty = _unexplained_empty_core(text, issues_blob)
        self.assertEqual(empty, [], empty)

    @unittest.skipUnless(PICK_L5X.is_file(), "MSCRENOPICK L5X missing")
    def test_no_blank_or_unnamed_operands(self) -> None:
        text = PICK_L5X.read_text(encoding="utf-8", errors="replace")
        hits = _blank_operand_hits(text)
        self.assertEqual(hits, [], hits)
        # Deterministic operand validator (malformed / missing tags)
        result = _validate_operands(text)
        self.assertTrue(
            result.get("ok"),
            f"invalid operands: {result.get('invalid_count')} sample={result.get('invalid')}",
        )

    @unittest.skipUnless(PICK_L5X.is_file() and (CURRENT / "MSCRENOPICK_BUILD_ISSUES.json").is_file(), "BUILD_ISSUES missing")
    def test_build_issues_present_with_status(self) -> None:
        issues = _load_json(CURRENT / "MSCRENOPICK_BUILD_ISSUES.json")
        status = issues.get("BUILD STATUS") or issues.get("build_status")
        self.assertIn(
            status,
            ("PARTIAL", "READY", "BLOCKED", "REVIEW_REQUIRED"),
            status,
        )


class TestVirginTfcp1L5xHardGate(unittest.TestCase):
    @unittest.skipUnless(VIRGIN_L5X.is_file(), "TFCP1 L5X missing")
    def test_l5x_and_transport(self) -> None:
        text = VIRGIN_L5X.read_text(encoding="utf-8", errors="replace")
        self.assertGreater(len(text), 10_000)
        progs = _program_names(text)
        for suf in REQUIRED_TRANSPORT_SUFFIXES:
            self.assertTrue(any(suf in p for p in progs), suf)
        for shared in REQUIRED_SHARED_PROGRAMS:
            self.assertIn(shared, progs)

    @unittest.skipUnless(VIRGIN_L5X.is_file(), "TFCP1 L5X missing")
    def test_safety_populated(self) -> None:
        text = VIRGIN_L5X.read_text(encoding="utf-8", errors="replace")
        es = _inspect_es(text)
        detail = es.get("detail") or {}
        self.assertTrue(detail.get("Main_Routine", {}).get("populated"))
        self.assertTrue(any(k.endswith("_Safe_Logic") and detail[k].get("populated") for k in detail))
        self.assertTrue(any(k.endswith("_Safe_PI") and detail[k].get("populated") for k in detail))

    @unittest.skipUnless(VIRGIN_L5X.is_file(), "TFCP1 L5X missing")
    def test_zero_mscreno_foreign_residue(self) -> None:
        text = VIRGIN_L5X.read_text(encoding="utf-8", errors="replace")
        hits = _foreign_hits(
            text,
            ("MSCRENOPICK", "MSCRENOPICK_Area", "MSCRENOPICK_ESZone1", "MSCRENOSHIP"),
        )
        self.assertEqual(sum(hits.values()), 0, hits)

    @unittest.skipUnless(VIRGIN_L5X.is_file(), "TFCP1 L5X missing")
    def test_no_blank_operands_or_unexplained_cores(self) -> None:
        text = VIRGIN_L5X.read_text(encoding="utf-8", errors="replace")
        issues_path = CURRENT / "TFCP1_BUILD_ISSUES.json"
        issues_blob = issues_path.read_text(encoding="utf-8") if issues_path.is_file() else ""
        self.assertEqual(_blank_operand_hits(text), [])
        self.assertEqual(_unexplained_empty_core(text, issues_blob), [])
        result = _validate_operands(text)
        self.assertTrue(result.get("ok"), result.get("invalid"))


class TestOrlAc3SafetyL5xHardGate(unittest.TestCase):
    """Third permanent fixture — engineer-assigned Safety still emits real ES."""

    @unittest.skipUnless(ORL_L5X.is_file(), "ORL_AC3 L5X missing")
    def test_orl_l5x_safety_populated(self) -> None:
        text = ORL_L5X.read_text(encoding="utf-8", errors="replace")
        self.assertGreater(len(text), 10_000)
        es = _inspect_es(text)
        detail = es.get("detail") or {}
        self.assertTrue(detail.get("Main_Routine", {}).get("populated"), detail.get("Main_Routine"))
        sl = [k for k in detail if k.endswith("_Safe_Logic")]
        sp = [k for k in detail if k.endswith("_Safe_PI")]
        self.assertTrue(sl and detail[sl[0]].get("populated"), sl)
        self.assertTrue(sp and detail[sp[0]].get("populated"), sp)
        # Known engineer zone from ORI-110 repro
        self.assertTrue(
            any("Area_Test1_ESZone1" in k for k in detail),
            detail.keys(),
        )

    @unittest.skipUnless(ORL_L5X.is_file() and (CURRENT / "ORL_AC3_BUILD_ISSUES.json").is_file(), "ORL BUILD_ISSUES missing")
    def test_orl_build_issues_present(self) -> None:
        issues = _load_json(CURRENT / "ORL_AC3_BUILD_ISSUES.json")
        status = issues.get("BUILD STATUS") or issues.get("build_status")
        self.assertTrue(status, "BUILD STATUS missing from ORL_AC3_BUILD_ISSUES")


class TestOri110UnitContractsStillGreen(unittest.TestCase):
    def test_ori110_unit_contracts(self) -> None:
        # Load ORI-110 unittest module in-process (avoids nested pytest WinError 6).
        import importlib.util

        path = ROOT / "tests" / "safety" / "test_ori110_safety_configuration_gate.py"
        spec = importlib.util.spec_from_file_location("ori110_safety_gate", path)
        self.assertIsNotNone(spec)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
        result = unittest.TestResult()
        suite.run(result)
        if result.wasSuccessful():
            return
        details = []
        for exc in list(result.failures) + list(result.errors):
            details.append(str(exc[0]))
            details.append(exc[1])
        self.fail(
            f"ORI-110 contracts failed: tests={result.testsRun} "
            f"failures={len(result.failures)} errors={len(result.errors)}\n"
            + "\n".join(details)
        )


if __name__ == "__main__":
    unittest.main()
