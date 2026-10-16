"""Part N / P3: incomplete RUN must not present as successful empty discovery."""
from __future__ import annotations

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

    def test_thin_ship_named_run_fail_closed(self):
        """P3: thin MSCRENOSHIP-shaped RUN (FORTNA/, no Conveyor.asc) must fail closed."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_dir = td_path / "RUN"
            (run_dir / "FORTNA").mkdir(parents=True)
            (run_dir / "project.cfg").write_text(
                "MACHINENAME=MSCRENOSHIP\nPROJECTNAME=MSCRENO_MSCRENOSHIP\n",
                encoding="utf-8",
            )
            (run_dir / "identity.cfg").write_text("site=MSCRENO\n", encoding="utf-8")
            out = td_path / "out"
            result = discover(run_dir, "MSCRENOSHIP", out)
            self.assertIs(result.get("ok"), False)
            self.assertTrue(result.get("incomplete_run"))
            self.assertEqual(result.get("code"), "INCOMPLETE_RUN")
            # Must not look like a successful virgin empty site.
            counts = result.get("counts") or {}
            self.assertEqual(int(counts.get("equipment") or 0), 0)

    def test_bare_run_without_fortna_does_not_soft_succeed(self):
        """P3: bare RUN (project.cfg only, no FORTNA/) must not return ok:true."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_dir = td_path / "RUN"
            run_dir.mkdir(parents=True)
            (run_dir / "project.cfg").write_text(
                "MACHINENAME=MSCRENOSHIP\nPROJECTNAME=MSCRENO_MSCRENOSHIP\n",
                encoding="utf-8",
            )
            out = td_path / "out"
            try:
                result = discover(run_dir, "MSCRENOSHIP", out)
            except FileNotFoundError:
                return  # fail-closed via exception is acceptable
            self.assertIs(result.get("ok"), False, result)


if __name__ == "__main__":
    unittest.main()
