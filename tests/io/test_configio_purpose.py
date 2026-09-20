#!/usr/bin/env python3
"""Configio purpose classification — exclude internal memory from physical I/O queue."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from siteforge_learning.classify_configio_purpose import (  # noqa: E402
    PURPOSE_ADAPTER_NETWORK,
    PURPOSE_INTERNAL_MEMORY,
    PURPOSE_PHYSICAL_IO,
    classify_configio_purpose,
)
from siteforge_learning.classify_configio_dialect import classify_configio_dialect  # noqa: E402
from siteforge_learning.corpus_models import FORM_PANEL_CATALOG_NUMERIC_ALPHA  # noqa: E402
from fortna_hardware_conflict import (  # noqa: E402
    ALIAS_CATALOG_MISMATCH,
    HARDWARE_TYPE_SOURCE_CONFLICT,
    classify_catalog_disagreement,
)


class TestPurpose(unittest.TestCase):
    def test_memory_patterns(self) -> None:
        for desc in ("MEMWD1", "MEMORY-1", "Memory_Word_570", "MEM-WD4", "CP1_MEM"):
            r = classify_configio_purpose({"desc": desc})
            self.assertEqual(r["purpose"], PURPOSE_INTERNAL_MEMORY, desc)
            self.assertFalse(r["keep_in_physical_io_queue"])

    def test_powerflex_network(self) -> None:
        r = classify_configio_purpose({"desc": "PowerFlex70-117", "bank": 0})
        self.assertEqual(r["purpose"], PURPOSE_ADAPTER_NETWORK)

    def test_physical_kept(self) -> None:
        r = classify_configio_purpose(
            {
                "desc": "1794-IA16-5",
                "interface": "RTA",
                "bank": 4,
                "octal_word": 700,
                "lohi": "Low",
                "in_out": "0000000011111111",
            }
        )
        self.assertEqual(r["purpose"], PURPOSE_PHYSICAL_IO)
        self.assertTrue(r["keep_in_physical_io_queue"])

    def test_blank_desc_with_physical_fields_exception(self) -> None:
        r = classify_configio_purpose(
            {
                "desc": "N/A",
                "interface": "RTA",
                "bank": 12,
                "octal_word": 710,
                "lohi": "Low",
                "in_out": "1111111100000000",
            }
        )
        self.assertEqual(r["purpose"], PURPOSE_PHYSICAL_IO)
        self.assertTrue(r["exception_nonphysical_desc_but_physical_fields"])


class TestPanelCatalogAlpha(unittest.TestCase):
    def test_form(self) -> None:
        h = classify_configio_dialect("CP8-1794-IA16-1A")
        self.assertEqual(h.configio_form, FORM_PANEL_CATALOG_NUMERIC_ALPHA)
        self.assertEqual(h.evidence.get("numeric_token"), "1")
        self.assertEqual(h.evidence.get("alpha_suffix"), "A")


class TestHardwareConflict(unittest.TestCase):
    def test_alias_vs_source_conflict(self) -> None:
        a = classify_catalog_disagreement(
            human_name_or_desc="CP8-1794-IA16-6A",
            eipmodules_type="1794-IB16",
            eipcfg_type="1794-IB16",
        )
        self.assertEqual(a["classification"], ALIAS_CATALOG_MISMATCH)
        c = classify_catalog_disagreement(
            human_name_or_desc="x",
            eipmodules_type="1794-IA16",
            eipcfg_type="1794-IB16",
        )
        self.assertEqual(c["classification"], HARDWARE_TYPE_SOURCE_CONFLICT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
