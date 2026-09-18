#!/usr/bin/env python3
"""CONFIGIO_CATALOG_WORD_BANK profile — virgin RUN Desc form + bank match.

Uses workspace/active/RUN (ORINDYAC6) when present. Does NOT read finished PLC.
"""
from __future__ import annotations

import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_model import OWNER_ASSIGNED, OWNER_UNUSED_MAPPED, build_hardware_io_model  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    parse_configio_catalog_word_bank,
    PhysicalWordResolver,
)

ACTIVE = ROOT / "workspace" / "active" / "RUN"
MACH = "ORINDYAC6"


class TestCatalogWordBankParse(unittest.TestCase):
    def test_parse_ia16(self) -> None:
        p = parse_configio_catalog_word_bank("1794-IA16-600-4")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p["form"], "catalog_word_bank")
        self.assertEqual(p["catalog"], "1794-IA16")
        self.assertEqual(p["fortna_word"], 600)
        self.assertEqual(p["eip_bank"], 4)
        self.assertFalse(p["is_aent_head"])

    def test_parse_aent_head(self) -> None:
        p = parse_configio_catalog_word_bank("1794-AENT-51-0")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertTrue(p["is_aent_head"])
        self.assertEqual(p["form"], "catalog_aent_node_bank")


@unittest.skipUnless((ACTIVE / "project.cfg").is_file(), "virgin active RUN missing")
class TestVirginCatalogWordBankJoin(unittest.TestCase):
    def test_owners_resolve_without_finished_plc(self) -> None:
        model = build_hardware_io_model(ACTIVE, MACH)
        st = (model.get("stats") or {}).get("owner_states") or {}
        self.assertGreaterEqual(int(st.get(OWNER_ASSIGNED) or 0), 100)
        # Five class samples
        res = PhysicalWordResolver(ACTIVE, MACH)
        for name, w, b in (
            ("PE600_J", "605", "0"),
            ("VFD600_AUX", "632", "0"),
            ("SSVEZPE540_P", "621", "0"),
            ("6PBSTART", "600", "0"),
            ("6MCR1AUX", "600", "2"),
        ):
            hit = res.resolve(w, b)
            self.assertIsNotNone(hit, name)
            ch_addr = (hit or {}).get("channel")
            found = None
            for ad in model.get("adapters") or []:
                for mod in ad.get("modules") or []:
                    for ch in mod.get("channels") or []:
                        if (ch.get("physical_address") or "") == ch_addr:
                            found = ch
                            break
            self.assertIsNotNone(found, name)
            assert found is not None
            self.assertEqual(found.get("owner_state"), OWNER_ASSIGNED, name)
            self.assertEqual(found.get("engineering_owner"), name)

    def test_unused_mapped_not_proven_spare(self) -> None:
        model = build_hardware_io_model(ACTIVE, MACH)
        st = (model.get("stats") or {}).get("owner_states") or {}
        self.assertGreaterEqual(int(st.get(OWNER_UNUSED_MAPPED) or 0), 1)
        # No requirement that PROVEN_SPARE > 0 without spare tokens


if __name__ == "__main__":
    unittest.main(verbosity=2)
