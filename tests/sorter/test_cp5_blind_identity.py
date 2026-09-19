#!/usr/bin/env python3
"""Regression: Sorter rows must not collapse on Machine ownership column."""
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


import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import row_identity_key  # noqa: E402


class TestSorterIdentityKey(unittest.TestCase):
    def test_distinct_sorters_same_machine_keep_distinct_keys(self):
        rows = [
            {"Sorter Name": "504_BELT", "Machine": "ORNCCP5", "Encoder ioName": "ENC504"},
            {"Sorter Name": "506_SHIP_SORTER", "Machine": "ORNCCP5", "Encoder ioName": "ENC506"},
            {"Sorter Name": "508_SHIP_SORTER", "Machine": "ORNCCP5", "Encoder ioName": "ENC508"},
        ]
        keys = [row_identity_key(r) for r in rows]
        self.assertEqual(keys, ["504_BELT", "506_SHIP_SORTER", "508_SHIP_SORTER"])
        self.assertEqual(len(set(keys)), 3)

    def test_machine_alone_is_not_preferred_identity(self):
        row = {"Machine": "ORNCCP5", "Sorter Name": "510_SHIP_SORTER"}
        self.assertEqual(row_identity_key(row), "510_SHIP_SORTER")


if __name__ == "__main__":
    unittest.main()
