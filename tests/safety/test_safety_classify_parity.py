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

    def test_actual_js_classifier_via_node(self) -> None:
        """ORI-043: must execute the real JS classifier — not a Python mirror."""
        script = Path(__file__).resolve().parent / "test_safety_classify_parity.js"
        r = subprocess.run(
            ["node", str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS", r.stdout)

    def test_safety_js_has_hardened_patterns(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("_NOT_OK", src)
        self.assertIn("_R\\d+", src)
        self.assertNotIn("/(?:^|_)MCR\\d*/.test(u)", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
