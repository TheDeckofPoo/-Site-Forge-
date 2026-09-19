#!/usr/bin/env python3
"""P542_Sorter_At_Speed ownership — Gate A/B/C regression."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import re
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_build import SORTER_TRACK_PACK, _load_program_export, build_configured_sorter_track  # noqa: E402
from fortna_sorter_discovery import build_canonical_sorter_model  # noqa: E402
from fortna_sorter_pack_compiler import compile_sorter_track_pack  # noqa: E402
from fortna_plc_symbol_registry import (  # noqa: E402
    PlcSymbolRegistry,
    is_controller_owned_shared_tag,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"


class TestAtSpeedOwnership(unittest.TestCase):
    def test_shared_role_detection(self) -> None:
        self.assertTrue(is_controller_owned_shared_tag("P542_Sorter_At_Speed"))
        self.assertTrue(is_controller_owned_shared_tag("P504_Sorter_At_Speed"))
        self.assertFalse(is_controller_owned_shared_tag("P542_Conv"))

    def test_load_does_not_merge_program_tags_into_controller_list(self) -> None:
        pack = _load_program_export(SORTER_TRACK_PACK)
        self.assertIsNotNone(pack)
        ctrl = {re.search(r'Tag Name="([^"]+)"', t).group(1) for t in pack["tags"]}
        # Context-owned encoder at-speed tags remain controller
        self.assertIn("P504_Sorter_At_Speed", ctrl)
        # Program-local P542 must NOT be in controller list before promote
        self.assertNotIn("P542_Sorter_At_Speed", ctrl)
        locals_ = {
            re.search(r'Tag Name="([^"]+)"', t).group(1)
            for t in (pack.get("program_local_tags") or [])
        }
        self.assertIn("P542_Sorter_At_Speed", locals_)

    @unittest.skipUnless(CP5_RUN.is_dir() and SORTER_TRACK_PACK.is_file(), "fixtures")
    def test_compile_promotes_and_strips_program_decl(self) -> None:
        model = build_canonical_sorter_model(CP5_RUN, "ORNCCP5")
        result = compile_sorter_track_pack(sorter_model=model, library_text="")
        self.assertTrue(result["emitted"])
        xml = result["program_xml"]
        # Program Tags must not declare P542_Sorter_At_Speed
        prog_tags = re.search(r"<Program[^>]*>\s*<Tags>(.*?)</Tags>", xml, re.S)
        body = prog_tags.group(1) if prog_tags else ""
        self.assertNotIn('Name="P542_Sorter_At_Speed"', body)
        # Controller tag list from compile must include promoted name
        ctrl_names = {
            re.search(r'Tag Name="([^"]+)"', t).group(1)
            for t in (result.get("tags") or [])
            if re.search(r'Tag Name="([^"]+)"', t)
        }
        self.assertIn("P542_Sorter_At_Speed", ctrl_names)
        promoted = (result.get("report") or {}).get("promoted_shared_controller_tags") or []
        self.assertIn("P542_Sorter_At_Speed", promoted)

    def test_registry_incompatible_dtype_fatal(self) -> None:
        reg = PlcSymbolRegistry()
        r1 = reg.register(
            name="Foo_Sorter_At_Speed",
            scope="controller",
            datatype="BOOL",
            owner="Sorter_Track",
            semantic_role="sorter_at_speed",
        )
        self.assertEqual(r1["action"], "declare")
        r2 = reg.register(
            name="Foo_Sorter_At_Speed",
            scope="controller",
            datatype="DINT",
            owner="Transport",
            semantic_role="other",
        )
        self.assertEqual(r2["action"], "fatal_collision")
        self.assertTrue(reg.report()["fatal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
