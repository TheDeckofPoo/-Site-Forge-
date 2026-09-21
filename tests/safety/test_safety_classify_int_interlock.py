#!/usr/bin/env python3
"""INT-* interlock names must not classify as ESR/MCR/ESTOP from substring alone."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import _io_map_es_member  # noqa: E402
from fortna_safety_model import _classify_device  # noqa: E402

SB = _SF_REPO / "dashboard" / "safety-build.js"


def _js_classify(name: str) -> str:
    """Mirror safety-build.js classifyDevName (keep tests honest if JS drifts)."""
    u = str(name or "").strip().upper().replace("-", "_")
    if not u:
        return ""
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


class TestSafetyClassifyIntInterlock(unittest.TestCase):
    def test_int_interlock_not_esr(self) -> None:
        self.assertEqual(_classify_device("INT-2ES2-1ESR1"), "")
        self.assertEqual(_classify_device("INT_2ES2_1ESR1"), "")
        self.assertEqual(_js_classify("INT-2ES2-1ESR1"), "")
        self.assertEqual(_js_classify("INT_2ES2_1ESR1"), "")

    def test_real_esr_mcr_estop(self) -> None:
        self.assertEqual(_classify_device("2ESR1"), "ESR")
        self.assertEqual(_classify_device("T_2ESR1"), "ESR")
        self.assertEqual(_classify_device("CP2_ESR1"), "ESR")
        self.assertEqual(_classify_device("2MCR1_AUX"), "MCR")
        self.assertEqual(_classify_device("2ES"), "ESTOP")
        self.assertEqual(_js_classify("2ESR1"), "ESR")
        self.assertEqual(_js_classify("T_2ESR1"), "ESR")
        self.assertEqual(_js_classify("2MCR1_AUX"), "MCR")

    def test_js_source_rejects_int(self) -> None:
        src = SB.read_text(encoding="utf-8")
        self.assertIn("startsWith('INT_')", src)
        self.assertIn("^T_\\d+ESR\\d*", src)

    def test_autogen_int_no_es_ok(self) -> None:
        self.assertEqual(_io_map_es_member("INT-2ES2-1ESR1"), "")
        self.assertEqual(_io_map_es_member("INT_2ES2_1ESR1"), "")
        self.assertTrue(_io_map_es_member("2ESR1").endswith(".I.ES_OK"))
        self.assertTrue(_io_map_es_member("2MCR1_AUX").endswith(".I.ES_OK"))
        # Digit-leading → canonical T_NAME (not CP*_ invent)
        self.assertEqual(_io_map_es_member("2ESR1"), "T_2ESR1.I.ES_OK")
        self.assertEqual(_io_map_es_member("2MCR1_AUX"), "T_2MCR1_AUX.I.ES_OK")
        self.assertEqual(_io_map_es_member("2ES"), "T_2ES.I.ES_OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
