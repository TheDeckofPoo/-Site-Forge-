#!/usr/bin/env python3
"""Nested RUN\\RUN evidence root guard — synthetic regression.

Never switch the bound machine/controller root merely because a nested RUN exists.
Competing candidate roots → REVIEW_REQUIRED / INTEGRITY.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_run_evidence_root import (  # noqa: E402
    bind_evidence_root,
    normalize_bound_run_dir,
)
from fortna_plc2_merge_discovery import _norm_run_dir  # noqa: E402


def _write_cfg(path: Path, machine: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"MACHINENAME = {machine}\n", encoding="utf-8")


class TestNestedRunRunRootGuard(unittest.TestCase):
    def test_parent_run_kept_when_nested_child_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "active" / "RUN"
            _write_cfg(root / "project.cfg", "PARENTPLC")
            (root / "FORTNA").mkdir(parents=True)
            nested = root / "RUN"
            _write_cfg(nested / "project.cfg", "NESTEDPLC")
            (nested / "FORTNA").mkdir(parents=True)

            bound = bind_evidence_root(root, machine="PARENTPLC")
            self.assertTrue(bound.get("ok"), bound)
            self.assertEqual(Path(bound["bound_root"]).resolve(), root.resolve())
            self.assertIn("nested_run_present_ignored", bound.get("integrity") or [])
            # Competing cfg content → REVIEW
            self.assertEqual(bound.get("status"), "REVIEW_REQUIRED")
            self.assertTrue(
                any("competing" in x for x in (bound.get("integrity") or [])),
                bound.get("integrity"),
            )

    def test_normalize_does_not_chase_nested_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "RUN"
            _write_cfg(root / "project.cfg", "SYNTHPLC")
            (root / "FORTNA").mkdir(parents=True)
            nested = root / "RUN"
            _write_cfg(nested / "project.cfg", "OTHER")
            (nested / "FORTNA").mkdir(parents=True)

            got = normalize_bound_run_dir(root, machine="SYNTHPLC")
            self.assertEqual(got.resolve(), root.resolve())
            got2 = _norm_run_dir(root)
            self.assertEqual(got2.resolve(), root.resolve())

    def test_missing_parent_cfg_may_use_child_only_with_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td) / "package"
            outer.mkdir(parents=True)
            child = outer / "RUN"
            _write_cfg(child / "project.cfg", "SYNTHPLC")
            (child / "FORTNA").mkdir(parents=True)

            no_fallback = bind_evidence_root(outer, allow_nested_fallback=False)
            self.assertFalse(no_fallback.get("ok"), no_fallback)

            with_fallback = bind_evidence_root(outer, allow_nested_fallback=True)
            self.assertTrue(with_fallback.get("ok"), with_fallback)
            self.assertEqual(
                Path(with_fallback["bound_root"]).resolve(), child.resolve()
            )
            self.assertEqual(with_fallback.get("status"), "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
