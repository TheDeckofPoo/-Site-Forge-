#!/usr/bin/env python3
"""MSCATL_CP1 IB32/OB32P mid-span Direct*Size bank join (shadow + optional prod).

Configio Desc IB32DATA-N / OB32PDATA-N is not Rockwell catalog. Exact
bank==InputBank/OutputBank misses mid-span banks inside DirectSize.
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

import fortna_rta_32pt_token_bank_span as rta32  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_hardware_family import channel_capacity_for_catalog  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_eipmodules_rows,
)
from fortna_rta_32pt_token_bank_span import (  # noqa: E402
    ASSIGN_HOW,
    parse_32pt_token_desc,
    shadow_resolve_run,
    try_rta_32pt_token_direct_bank_span_match,
)

CP1 = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP1" / "RUN"
CP3 = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"


class TestCapacity32pt(unittest.TestCase):
    def test_ib32_ob32p_capacity(self) -> None:
        self.assertEqual(channel_capacity_for_catalog("1794-IB32"), 32)
        self.assertEqual(channel_capacity_for_catalog("IB32"), 32)
        self.assertEqual(channel_capacity_for_catalog("1794-OB32P"), 32)
        self.assertEqual(channel_capacity_for_catalog("OB32P"), 32)
        # 16-pt unchanged
        self.assertEqual(channel_capacity_for_catalog("1794-IB16"), 16)


class TestTokenParse(unittest.TestCase):
    def test_parse_ib32_ob32p(self) -> None:
        p = parse_32pt_token_desc("IB32DATA-61")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p["tok"], "IB32")
        self.assertEqual(p["catalog"], "1794-IB32")
        self.assertEqual(p["direction"], "I")
        self.assertEqual(p["role"], "DATA")

        p2 = parse_32pt_token_desc("OB32PDATA-87")
        self.assertIsNotNone(p2)
        assert p2 is not None
        self.assertEqual(p2["tok"], "OB32P")
        self.assertEqual(p2["catalog"], "1794-OB32P")
        self.assertEqual(p2["direction"], "O")

        self.assertIsNotNone(parse_32pt_token_desc("IB32STATUS-141"))
        self.assertIsNone(parse_32pt_token_desc("1794-IB32-5"))
        self.assertIsNone(parse_32pt_token_desc("IB16DATA-1"))


@unittest.skipUnless((CP1 / "FORTNA").is_dir(), "MSCATL_CP1 RUN peek missing")
class TestCp1Ib32MidspanShadow(unittest.TestCase):
    def test_eipmodules_loads_direct_sizes(self) -> None:
        rows = _load_eipmodules_rows(CP1, "MSCATL_CP1")
        ib = [r for r in rows if "IB32" in (r.get("type") or "").upper()]
        self.assertGreater(len(ib), 0)
        self.assertEqual(int(ib[0].get("direct_input_size") or 0), 8)
        ob = [r for r in rows if "OB32P" in (r.get("type") or "").upper()]
        self.assertGreater(len(ob), 0)
        self.assertEqual(int(ob[0].get("direct_output_size") or 0), 4)

    def test_shadow_resolve_run_large_gain(self) -> None:
        # Shadow does not require ENABLE_IN_PHYSICAL_WORD_RESOLVER
        prev = rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER
        try:
            rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER = False
            report = shadow_resolve_run(CP1, "MSCATL_CP1")
        finally:
            rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER = prev
        self.assertEqual(report["assign_how"], ASSIGN_HOW)
        self.assertGreater(int(report["token_unresolved"]), 0)
        self.assertGreaterEqual(
            int(report["would_bind_count"]),
            40,
            f"expected large mid-span gain, got {report['would_bind_count']}",
        )
        # No site-name special case in rule id / assign_how
        self.assertNotIn("mscatl", ASSIGN_HOW.lower())
        self.assertNotIn("cp1", ASSIGN_HOW.lower())

    def test_unique_span_hit_ib32data_61(self) -> None:
        pwr = PhysicalWordResolver(CP1, "MSCATL_CP1")
        adapters = (pwr.topology or {}).get("adapters") or []
        hit = try_rta_32pt_token_direct_bank_span_match("IB32DATA-61", 36, adapters)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.get("assign_how"), ASSIGN_HOW)
        self.assertIn("IB32", str(hit.get("type") or "").upper())
        self.assertEqual(int(hit.get("span_base_bank") or -1), 32)
        self.assertEqual(int(hit.get("span_size") or 0), 8)

    def test_enabled_resolver_assigns_ib32_midspan(self) -> None:
        prev = rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER
        try:
            rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER = True
            pwr = PhysicalWordResolver(CP1, "MSCATL_CP1")
            words = (pwr.physical_map or {}).get("words") or {}
            # Word 411 = IB32DATA-61/62 banks 36/37 (mid-span of IB32 @32)
            w411 = words.get("411") or words.get(411)
            self.assertIsNotNone(w411, "IB32DATA mid-span word 411 should ASSIGN when enabled")
            assert w411 is not None
            self.assertEqual(w411.get("assign_how"), ASSIGN_HOW)
            # Word 416 = OB32PDATA-87/88 banks 26/27 (mid-span of OB32P @24)
            w416 = words.get("416") or words.get(416)
            self.assertIsNotNone(w416, "OB32PDATA mid-span word 416 should ASSIGN when enabled")
            assert w416 is not None
            self.assertEqual(w416.get("assign_how"), ASSIGN_HOW)
            hows = {
                str(v.get("assign_how") or "")
                for v in words.values()
                if isinstance(v, dict)
            }
            self.assertIn(ASSIGN_HOW, hows)
        finally:
            rta32.ENABLE_IN_PHYSICAL_WORD_RESOLVER = prev

    def test_no_site_name_special_case_in_helper_source(self) -> None:
        src = Path(rta32.__file__).read_text(encoding="utf-8")
        self.assertNotIn("MSCATL", src)
        self.assertNotIn("mscatl", src)


@unittest.skipUnless((CP3 / "FORTNA").is_dir(), "MSCATL_CP3 RUN peek missing")
class TestCp3SmokeUnchanged(unittest.TestCase):
    def test_cp3_still_256_assigned(self) -> None:
        ev = build_evidence_bundle(CP3, "MSCATL_CP3", project="MSCATL_CP3")
        raw = ev.get("raw_claims") or []
        disp = Counter(c.get("deterministic_disposition") for c in raw)
        self.assertEqual(int(disp.get("ASSIGNED") or 0), 256)
        self.assertEqual(len(raw), 256)


if __name__ == "__main__":
    unittest.main()
