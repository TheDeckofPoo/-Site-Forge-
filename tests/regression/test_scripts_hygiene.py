#!/usr/bin/env python3
"""Repository hygiene: keep tools/scripts free of junk and misplaced tests."""
from __future__ import annotations

import unittest
from pathlib import Path

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


class TestScriptsHygiene(unittest.TestCase):
    def test_no_tmp_or_emergency_in_scripts(self) -> None:
        bad = []
        for p in SCRIPTS.glob("*.py"):
            name = p.name
            if name.startswith("_tmp_") or name.startswith("_emergency_"):
                bad.append(name)
        self.assertEqual(
            bad,
            [],
            "Do not commit _tmp_* / _emergency_* under tools/scripts/; "
            "use tools/diagnostics/ or leave untracked scratch outside git",
        )

    def test_no_new_test_modules_in_scripts(self) -> None:
        bad = sorted(p.name for p in SCRIPTS.glob("test_*.py"))
        self.assertEqual(
            bad,
            [],
            "Permanent tests belong under tests/<area>/, not tools/scripts/",
        )

    def test_diagnostics_dir_exists(self) -> None:
        self.assertTrue((ROOT / "tools" / "diagnostics").is_dir())

    def test_production_entrypoints_still_in_scripts(self) -> None:
        required = [
            "fortna_autogen.py",
            "fortna_safety_model.py",
            "fortna_transport_graph.py",
            "fortna_hardware_io_model.py",
            "fortna_run_workspace_discover.py",
            "apply_recipe.py",
            "index_docs.py",
        ]
        missing = [n for n in required if not (SCRIPTS / n).is_file()]
        self.assertEqual(missing, [], f"production entrypoints missing: {missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
