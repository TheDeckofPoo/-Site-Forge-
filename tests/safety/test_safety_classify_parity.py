#!/usr/bin/env python3
"""ORI-043 — Python/JS Safety classifier parity against shared corpus."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_model import _classify_device  # noqa: E402

CORPUS = Path(__file__).resolve().parent / "safety_classify_vectors.json"
SAFETY_JS = ROOT / "dashboard" / "safety-build.js"


def _js_classify_mirror(name: str) -> str:
    """Mirror of dashboard classifyDevName — kept in lockstep via corpus."""
    u = str(name or "").strip().upper().replace("-", "_")
    if not u:
        return ""
    if u.startswith("INT_"):
        return ""
    if re.search(r"(?:^|_)MEM(?:_|$)", u) or "_NOT_OK" in u:
        return ""
    if "ESLS" in u:
        return "ESLS"
    if (
        re.match(r"^T_\d+ESR\d*(?:_?AUX)?$", u)
        or re.match(r"^CP\d+_ESR\d*(?:_?AUX)?$", u)
        or re.match(r"^\d+ESR\d*(?:_?AUX)?$", u)
        or re.match(r"^ESR\d+(?:_?AUX)?$", u)
        or re.match(r"^ESR\d*$", u)
    ):
        return "ESR"
    if (
        re.match(r"^T_\d+MCR\d+(?:_?AUX)?$", u)
        or re.match(r"^CP\d+_MCR\d+(?:_?AUX)?$", u)
        or re.match(r"^\d+MCR\d+(?:_?AUX)?$", u)
        or re.match(r"^MCR\d+(?:_?AUX)?$", u)
    ):
        return "MCR"
    if re.search(r"(?:^|_|T_)(?:CP\d+_)?MCR", u) or re.match(r"^\d+MCR", u):
        return ""
    if re.match(r"^CP\d+_CS\d*$", u) or u.endswith("_CS"):
        return "CS"
    if re.match(r"^ESPB\d", u) or re.search(r"(^|_)ESPB\d", u):
        return "ESTOP"
    if (
        re.match(r"^T_\d+ES\d*\w*$", u)
        or re.match(r"^CP\d+_ES\d*\w*$", u)
        or re.match(r"^ES\d[\w]*$", u)
        or re.match(r"^\d+ES\d*\w*$", u)
        or re.search(r"(^|_)ES\d", u)
        or re.match(r"^ES[_]?JES", u)
    ):
        return "ESTOP"
    return ""


class TestClassifyParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vectors = json.loads(CORPUS.read_text(encoding="utf-8"))["vectors"]

    def test_python_matches_corpus(self) -> None:
        for row in self.vectors:
            got = _classify_device(row["name"])
            self.assertEqual(
                got, row["expect"], f"Python {_classify_device.__name__}({row['name']!r})"
            )

    def test_js_mirror_matches_corpus(self) -> None:
        for row in self.vectors:
            got = _js_classify_mirror(row["name"])
            self.assertEqual(got, row["expect"], f"JS mirror({row['name']!r})")

    def test_python_js_agree(self) -> None:
        for row in self.vectors:
            py = _classify_device(row["name"])
            js = _js_classify_mirror(row["name"])
            self.assertEqual(py, js, f"parity {row['name']!r}: py={py!r} js={js!r}")

    def test_safety_js_has_hardened_patterns(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("_NOT_OK", src)
        self.assertIn("(?:_?AUX)?", src)
        self.assertNotIn("/(?:^|_)MCR\\d*/.test(u)", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
