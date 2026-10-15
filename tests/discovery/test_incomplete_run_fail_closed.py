"""Part N: incomplete RUN must not present as successful empty discovery."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_run_workspace_discover import discover, main  # noqa: E402


class IncompleteRunFailClosed(unittest.TestCase):
    def test_missing_conveyor_asc_sets_ok_false(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_dir = td_path / "RUN"
            fortna = run_dir / "FORTNA"
            fortna.mkdir(parents=True)
            (run_dir / "project.cfg").write_text(
                "MACHINENAME=TESTCTRL\nPROJECTNAME=Test_TESTCTRL\n",
                encoding="utf-8",
            )
            # FORTNA present, Conveyor.asc* absent → incomplete
            out = td_path / "out"
            result = discover(run_dir, "TESTCTRL", out)
            self.assertTrue(result.get("incomplete_run"))
            self.assertIs(result.get("ok"), False)
            self.assertEqual(result.get("code"), "INCOMPLETE_RUN")
            self.assertIn("incomplete", (result.get("error") or "").lower())

    def test_main_exits_nonzero_on_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_dir = td_path / "RUN"
            (run_dir / "FORTNA").mkdir(parents=True)
            (run_dir / "project.cfg").write_text(
                "MACHINENAME=TESTCTRL\nPROJECTNAME=Test_TESTCTRL\n",
                encoding="utf-8",
            )
            out = td_path / "out"
            code = main(["--run-dir", str(run_dir), "--out", str(out), "--machine", "TESTCTRL"])
            self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
