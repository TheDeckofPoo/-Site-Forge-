#!/usr/bin/env python3
"""Ensure answer-sheet validation cannot become compiler input."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

GENERATION_MODULES = [
    "fortna_autogen.py",
    "fortna_sitemodel_to_autogen.py",
    "fortna_cp5_blind_build.py",
    "fortna_run_workspace_discover.py",
    "fortna_knowledge_enrich.py",
]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


class TestValidationFirewall(unittest.TestCase):
    def test_generation_modules_do_not_import_answer_sheet_compare(self):
        for name in GENERATION_MODULES:
            path = SCRIPTS / name
            if not path.is_file():
                continue
            imports = _imports(path)
            self.assertNotIn(
                "fortna_answer_sheet_compare",
                imports,
                msg=f"{name} must not import answer-sheet validation",
            )

    def test_gap_closure_may_import_validation_but_not_reverse(self):
        # gap closure is allowed to call compare for reports
        gap = SCRIPTS / "fortna_cp5_gap_closure.py"
        if gap.is_file():
            src = gap.read_text(encoding="utf-8")
            self.assertIn("fortna_answer_sheet_compare", src)
        # answer sheet must not import generation bridge for side effects beyond reading paths
        ans = SCRIPTS / "fortna_answer_sheet_compare.py"
        imports = _imports(ans)
        self.assertNotIn("fortna_sitemodel_to_autogen", imports)
        self.assertNotIn("fortna_autogen", imports)


if __name__ == "__main__":
    unittest.main()
