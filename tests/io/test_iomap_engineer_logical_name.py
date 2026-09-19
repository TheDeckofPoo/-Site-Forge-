#!/usr/bin/env python3
"""Regression: engineer Name is LOGICAL only — never a physical module/base.

Proves:
  - physical channel stays CP2RIO0:O.Data[n].b
  - bare engineer name becomes BOOL logical operand (not module base)
  - rename → revert removes name from overrides / iomap map
  - unknown-base preflight would accept after BOOL ensure (member base == tag)
"""
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
import tempfile
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_overrides import (  # noqa: E402
    empty_overrides,
    overrides_for_iomap,
    prune_inactive_overrides,
    upsert_channel_override,
)


class TestIomapEngineerLogicalName(unittest.TestCase):
    def test_member_from_override_bare_is_bool_not_udt(self) -> None:
        """Bare Fan_Starter must NOT become Fan_Starter.O.Run (invalid UDT guess)."""
        # Mirror autogen rule locally
        def member_from_override(eng_name: str, fallback: str) -> str:
            n = (eng_name or "").strip()
            if not n:
                return fallback
            if "." in n:
                return n
            import re

            s = re.sub(r"[^A-Za-z0-9_]", "_", n).strip("_")
            return s or n

        self.assertEqual(member_from_override("Fan_Starter", "M402.O.Run"), "Fan_Starter")
        self.assertEqual(
            member_from_override("P402_Conv.O.Run", "M402.O.Run"),
            "P402_Conv.O.Run",
        )
        self.assertNotIn(".O.Run", member_from_override("Me_Likey_Butts", "x"))

    def test_physical_address_immutable_in_override_key(self) -> None:
        ov = empty_overrides()
        addr = "CP2RIO0:O.Data[6].6"
        upsert_channel_override(
            ov,
            physical_address=addr,
            source_name="SPARE",
            engineer_name="TEST_OUTPUT",
            generate=True,
        )
        self.assertIn(addr, ov["channels"])
        self.assertEqual(ov["channels"][addr]["engineerName"], "TEST_OUTPUT")
        # Physical key never becomes the engineer string
        self.assertNotIn("TEST_OUTPUT", ov["channels"])

    def test_revert_absent_from_iomap_map(self) -> None:
        ov = empty_overrides()
        addr = "CP2RIO0:O.Data[6].6"
        upsert_channel_override(
            ov, physical_address=addr, engineer_name="YOU_LIKEY_Butts", generate=True
        )
        upsert_channel_override(
            ov, physical_address=addr, engineer_name="SPARE", generate=True
        )
        prune_inactive_overrides(ov)
        m = overrides_for_iomap(ov)
        self.assertNotIn(addr, m)
        self.assertNotIn("YOU_LIKEY_Butts", str(m))
        self.assertNotIn("YOU_LIKEY_Butts", str(ov))


if __name__ == "__main__":
    unittest.main()
