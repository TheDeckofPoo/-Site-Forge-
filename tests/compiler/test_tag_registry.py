#!/usr/bin/env python3
"""Controller tag ownership registry — dedupe + identity conflict."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_es_compiler import studio_safety_tag  # noqa: E402
from fortna_tag_registry import (  # noqa: E402
    ControllerTagRegistry,
    TagIdentityConflict,
    canonical_safety_logix_tag,
)


class TestCanonicalSafetyLogixTag(unittest.TestCase):
    def test_digit_leading_to_t_name(self) -> None:
        self.assertEqual(canonical_safety_logix_tag("2ES"), "T_2ES")
        self.assertEqual(canonical_safety_logix_tag("T_2ES"), "T_2ES")
        self.assertEqual(canonical_safety_logix_tag("2MCR1_AUX"), "T_2MCR1_AUX")
        self.assertEqual(canonical_safety_logix_tag("CP2_ES"), "CP2_ES")
        self.assertEqual(canonical_safety_logix_tag("ES400"), "ES400")

    def test_studio_safety_tag_alias_once(self) -> None:
        self.assertEqual(studio_safety_tag("2ES"), "T_2ES")
        self.assertEqual(studio_safety_tag("T_2ES"), "T_2ES")
        self.assertEqual(studio_safety_tag("4ES"), "T_4ES")
        self.assertEqual(studio_safety_tag("CP2_ES"), "CP2_ES")


class TestTagRegistry(unittest.TestCase):
    def test_dedupes_same_identity(self) -> None:
        reg = ControllerTagRegistry()
        self.assertTrue(
            reg.register_tag("T_2ES", owner="2ES", datatype="ES_UDT", subsystem="io_map")
        )
        self.assertFalse(
            reg.register_tag(
                "T_2ES",
                owner="2ES",
                datatype="ES_UDT",
                subsystem="es_compiler",
                provenance="alias",
            )
        )
        self.assertEqual(len(reg.names()), 1)

    def test_atomic_to_udt_upgrade_same_owner(self) -> None:
        reg = ControllerTagRegistry()
        self.assertTrue(
            reg.register_tag("T_2ES", owner="2ES", datatype="BOOL", subsystem="io_map")
        )
        self.assertTrue(
            reg.register_tag(
                "T_2ES", owner="2ES", datatype="ES_UDT", subsystem="es_compiler"
            )
        )
        self.assertEqual(reg.get("T_2ES").datatype, "ES_UDT")

    def test_conflict_blocks_incompatible_datatype(self) -> None:
        reg = ControllerTagRegistry()
        reg.register_tag("T_2ES", owner="BEACON_2ES", datatype="BOOL", subsystem="io_map")
        with self.assertRaises(TagIdentityConflict) as ctx:
            reg.register_tag(
                "T_2ES", owner="2ES", datatype="ES_UDT", subsystem="es_compiler"
            )
        self.assertIn("TAG_IDENTITY_CONFLICT", str(ctx.exception))
        self.assertTrue(reg.conflicts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
