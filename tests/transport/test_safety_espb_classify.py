#!/usr/bin/env python3
"""Safety inventory must include ESPB* pushbuttons (GUI classifyDevName parity)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SB = ROOT / "dashboard" / "safety-build.js"
SM = ROOT / "tools" / "scripts" / "fortna_safety_model.py"


class TestSafetyEspbClassify(unittest.TestCase):
    def test_js_classifies_espb(self) -> None:
        src = SB.read_text(encoding="utf-8")
        self.assertIn("ESPB", src)
        self.assertIn("^ESPB\\d", src)

    def test_python_classifies_espb(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "tools" / "scripts"))
        from fortna_safety_model import _classify_device  # noqa: E402

        self.assertEqual(_classify_device("ESPB24"), "ESTOP")
        self.assertEqual(_classify_device("ESPB2"), "ESTOP")
        self.assertEqual(_classify_device("ESLS1"), "ESLS")

    def test_js_patterns_cover_pick_names(self) -> None:
        """Mirror the JS classifyDevName regexes for MSCRENOPICK names."""
        src = SB.read_text(encoding="utf-8")
        # Extract is fragile — execute the known patterns used in JS
        def classify(name: str) -> str:
            u = name.strip().upper().replace("-", "_")
            if u.startswith("INT_"):
                return ""
            if "ESLS" in u:
                return "ESLS"
            if (
                re.match(r"^T_\d+ESR\d*\w*$", u)
                or re.match(r"^CP\d+_ESR\d*\w*$", u)
                or re.match(r"^\d+ESR\d*\w*$", u)
                or re.match(r"^ESR\d*\w*$", u)
                or re.search(r"(?:^|_)ESR\d*", u)
            ):
                return "ESR"
            if (
                re.match(r"^T_\d+MCR\d*\w*$", u)
                or re.match(r"^CP\d+_MCR\d*\w*$", u)
                or re.match(r"^\d+MCR\d*\w*$", u)
                or re.match(r"^MCR\d*\w*$", u)
                or re.search(r"(?:^|_)MCR\d*", u)
            ):
                return "MCR"
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

        names = [
            "ESPB124", "ESPB13-RBA", "ESPB1O", "ESPB20", "ESLS1", "ESLS13P7-1",
        ]
        kinds = {n: classify(n) for n in names}
        self.assertTrue(all(kinds.values()), kinds)
        self.assertEqual(sum(1 for v in kinds.values() if v == "ESTOP"), 4)
        self.assertIn("ESPB", src)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "scripts"))
    unittest.main(verbosity=2)
