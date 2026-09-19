#!/usr/bin/env python3
"""Regression: CP3RIO2 Release SSV evidence chain (RUN-driven, not finished-hardcoded).

Asserts the generic path:
  Conveyor.asc SSVEZPE* (word/bit)
    → PhysicalWordResolver → CP3RIO2:O.Data[0].N
    → resolve_ssv_endpoint → {section}_Conv.O.Release

For this machine's RUN: bits 0..3 map P150_P1 / P150_P2 / P242 / P320;
bits 4+ have no SSV on word 320 and remain placeholders in IO_MAP generation.
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
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_conveyor_section_model import (  # noqa: E402
    discover_sections,
    resolve_ssv_endpoint,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
    resolve_word_bit,
)

RUN = ROOT / "workspace" / "active" / "RUN"

# Generic SSV → Release expectations driven by RUN Conveyor.asc word 320 bits.
# Keys are RUN IO_Name values discovered from this machine's tables — not finished PLC.
EXPECTED_SSV_RELEASE = {
    "SSVEZPE150_P1": ("P150_P1_Conv.O.Release", 0),
    "SSVEZPE150_P2": ("P150_P2_Conv.O.Release", 1),
    "SSVEZPE242_P": ("P242_Conv.O.Release", 2),
    "SSVEZPE320_P": ("P320_Conv.O.Release", 3),
}


def _norm_run_dir() -> Path:
    run_dir = RUN
    if not (run_dir / "project.cfg").is_file() and (ROOT / "workspace" / "active" / "project.cfg").is_file():
        run_dir = ROOT / "workspace" / "active"
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    return run_dir


class TestCp3Rio2ReleaseSsv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_dir = _norm_run_dir()
        assert (cls.run_dir / "project.cfg").is_file(), f"missing RUN at {cls.run_dir}"
        meta = (cls.run_dir / "project.cfg").read_text(encoding="utf-8", errors="replace")
        # Machine from RUN project.cfg — not hard-coded as compiler Greensboro rule
        m = None
        for line in meta.splitlines():
            if line.strip().upper().startswith("MACHINENAME"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    m = parts[1].strip().strip('"').strip("'")
                    break
        cls.machine = m or "ORNCCP2"
        cls.pm = build_physical_word_map(cls.run_dir, cls.machine)
        cls.resolver = PhysicalWordResolver(cls.run_dir, cls.machine)
        discovered = discover_sections(cls.run_dir, cls.machine)
        cls.sections = set((discovered.get("sections") or {}).keys())
        _h, rows = read_asc(cls.run_dir / "FORTNA" / "Conveyor.asc")
        cls.ssv_rows = {}
        for r in rows:
            name = (r.get("IO_Name") or "").strip()
            if name in EXPECTED_SSV_RELEASE:
                cls.ssv_rows[name] = r

    def test_run_has_ssv_rows_on_word_320(self):
        for name, (_endpoint, bit) in EXPECTED_SSV_RELEASE.items():
            self.assertIn(name, self.ssv_rows, f"RUN missing {name}")
            row = self.ssv_rows[name]
            word = int(float(row.get("IO_Address_Word") or 0))
            self.assertEqual(word, 320, f"{name} expected Fortna word 320")
            bit_raw = str(row.get("IO_Address_Bit") or "").strip()
            self.assertEqual(int(float(bit_raw)), bit, f"{name} bit")

    def test_physical_resolver_maps_word_320_to_cp3rio2(self):
        for bit in range(4):
            hit = resolve_word_bit(self.pm, 320, bit)
            self.assertIsNotNone(hit, f"word 320 bit {bit} unresolved")
            assert hit is not None
            self.assertEqual(hit.get("channel"), f"CP3RIO2:O.Data[0].{bit}")
            self.assertEqual(hit.get("rio_name"), "CP3RIO2")
            self.assertEqual(hit.get("direction"), "O")
            # Same via instance resolver
            hit2 = self.resolver.resolve(320, bit)
            self.assertIsNotNone(hit2)
            self.assertEqual(hit2.get("channel"), f"CP3RIO2:O.Data[0].{bit}")

    def test_resolve_ssv_endpoint_to_release(self):
        self.assertTrue(self.sections, "discover_sections returned no sections")
        for name, (endpoint, _bit) in EXPECTED_SSV_RELEASE.items():
            got = resolve_ssv_endpoint(name, self.sections)
            self.assertEqual(
                got,
                endpoint,
                f"{name} → expected {endpoint} via section model, got {got}",
            )

    def test_evidence_chain_bits_0_to_3(self):
        """Full chain: RUN SSV → channel CP3RIO2:O.Data[0].N ← section_Conv.O.Release."""
        chain = []
        for name, (endpoint, bit) in EXPECTED_SSV_RELEASE.items():
            row = self.ssv_rows[name]
            word = int(float(row.get("IO_Address_Word") or 0))
            hit = self.resolver.resolve(word, bit)
            self.assertIsNotNone(hit)
            assert hit is not None
            channel = hit.get("channel")
            release = resolve_ssv_endpoint(name, self.sections)
            self.assertEqual(channel, f"CP3RIO2:O.Data[0].{bit}")
            self.assertEqual(release, endpoint)
            chain.append({"ssv": name, "channel": channel, "endpoint": release})
        # Explicit assertions matching the requested mapping surface
        by_ch = {c["channel"]: c["endpoint"] for c in chain}
        self.assertEqual(by_ch["CP3RIO2:O.Data[0].0"], "P150_P1_Conv.O.Release")
        self.assertEqual(by_ch["CP3RIO2:O.Data[0].1"], "P150_P2_Conv.O.Release")
        self.assertEqual(by_ch["CP3RIO2:O.Data[0].2"], "P242_Conv.O.Release")
        self.assertEqual(by_ch["CP3RIO2:O.Data[0].3"], "P320_Conv.O.Release")

    def test_bits_4_plus_have_no_ssv_on_word_320(self):
        """Bits 4+ on word 320 are not occupied by SSV rows → IO_MAP placeholders."""
        occupied = set()
        _h, rows = read_asc(self.run_dir / "FORTNA" / "Conveyor.asc")
        for r in rows:
            try:
                word = int(float(r.get("IO_Address_Word") or -1))
            except (TypeError, ValueError):
                continue
            if word != 320:
                continue
            bit_raw = str(r.get("IO_Address_Bit") or "").strip()
            if not bit_raw:
                continue
            occupied.add(int(float(bit_raw)))
        for bit in range(4, 16):
            self.assertNotIn(bit, occupied, f"word 320 bit {bit} unexpectedly occupied")
        # Physical channel still resolves (module exists); logical SSV endpoint does not
        hit = resolve_word_bit(self.pm, 320, 4)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("channel"), "CP3RIO2:O.Data[0].4")

    def test_optional_iomap_snippet_matches_evidence(self):
        """If a current L5X exists, CP3RIO2:O.Data[0].0..3 match RUN evidence endpoints."""
        from fortna_io_regression_baselines import _parse_iomap_mappings
        from fortna_plc2_io_channel_matrix import resolve_current_l5x
        from fortna_plc2_io_truth import _is_placeholder_tag

        try:
            l5x = resolve_current_l5x()
        except FileNotFoundError:
            self.skipTest("no current ORNCCP2 L5X available")
        text = l5x.read_text(encoding="utf-8", errors="replace")
        maps = {
            m.get("channel"): m.get("tag")
            for m in _parse_iomap_mappings(text, limit=5000)
            if (m.get("channel") or "").startswith("CP3RIO2:O.Data[0].")
        }
        expected = {
            f"CP3RIO2:O.Data[0].{bit}": endpoint
            for endpoint, bit in (
                ("P150_P1_Conv.O.Release", 0),
                ("P150_P2_Conv.O.Release", 1),
                ("P242_Conv.O.Release", 2),
                ("P320_Conv.O.Release", 3),
            )
        }
        for ch, endpoint in expected.items():
            self.assertEqual(
                maps.get(ch),
                endpoint,
                f"{l5x.name}: {ch} expected {endpoint}, got {maps.get(ch)}",
            )
        for bit in range(4, 16):
            ch = f"CP3RIO2:O.Data[0].{bit}"
            if ch not in maps:
                continue
            self.assertTrue(
                _is_placeholder_tag(maps[ch] or ""),
                f"{ch} should be placeholder, got {maps[ch]}",
            )


if __name__ == "__main__":
    unittest.main()
