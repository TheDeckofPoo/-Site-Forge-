#!/usr/bin/env python3
"""CONFIGIO_CATALOG_WORD_BANK profile — virgin RUN Desc form + bank match.

Uses workspace/active/RUN (ORINDYAC6) when present. Does NOT read finished PLC.
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


import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_model import OWNER_ASSIGNED, OWNER_UNUSED_MAPPED, build_hardware_io_model  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    parse_configio_catalog_word_bank,
    PhysicalWordResolver,
)

ACTIVE = ROOT / "workspace" / "active" / "RUN"
VIRGIN_ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"
# Prefer restored virgin extract when active/ was cleared
_RUN = VIRGIN_ORINDY if (VIRGIN_ORINDY / "project.cfg").is_file() else ACTIVE
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


@unittest.skipUnless((_RUN / "project.cfg").is_file(), "virgin ORINDYAC6 RUN missing")
class TestVirginCatalogWordBankJoin(unittest.TestCase):
    def test_owners_resolve_without_finished_plc(self) -> None:
        model = build_hardware_io_model(_RUN, MACH)
        st = (model.get("stats") or {}).get("owner_states") or {}
        # Floor after FLEX bank conservation fix (AENT-2 words 610–617 restored).
        # Rich claim ledger locks 60 AENT-2 named claims separately — do not
        # inflate ASSIGNED by marking named RUN claims as SPARE.
        self.assertGreaterEqual(int(st.get(OWNER_ASSIGNED) or 0), 60)
        # Five class samples
        res = PhysicalWordResolver(_RUN, MACH)
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
        model = build_hardware_io_model(_RUN, MACH)
        st = (model.get("stats") or {}).get("owner_states") or {}
        self.assertGreaterEqual(int(st.get(OWNER_UNUSED_MAPPED) or 0), 1)
        # No requirement that PROVEN_SPARE > 0 without spare tokens


@unittest.skipUnless((_RUN / "project.cfg").is_file(), "virgin ORINDYAC6 RUN missing")
class TestCatalogWordBankEndpointFidelity(unittest.TestCase):
    """Bank match must win — never false name-match Data[2] for word 600."""

    def test_word_600_maps_to_data0_not_data2(self) -> None:
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit

        pm = build_physical_word_map(_RUN, MACH)
        e = (pm.get("words") or {}).get("600") or {}
        self.assertEqual(e.get("assign_how"), "configio_bank_match")
        hit = resolve_word_bit(pm, 600, 0)
        self.assertIsNotNone(hit)
        ch = str((hit or {}).get("channel") or "")
        self.assertIn(":I.Data[0].0", ch, msg=f"expected Data[0].0, got {ch}")
        self.assertNotIn("Data[2]", ch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
