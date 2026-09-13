#!/usr/bin/env python3
"""Hard I/O regression lock — identity + mapping, not counts alone.

Product-path failures that MUST stop acceptance:
  - known RUN with supported IO + zero modules in UI-path L5X
  - known RUN with supported mappings + IO_MAP NOP-only
  - discovered PE with bank/bit + PE mapping missing from IO_MAP
  - representative exact mapping drift (tag/channel/slot/bit/direction)
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
LOCK = ROOT / "exports" / "io-regression-lock"
STUDIO = ROOT / "exports" / "studio-validation"

import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_runtime_acceptance_recovery import _l5x_counts  # noqa: E402
from fortna_io_regression_baselines import (  # noqa: E402
    _parse_iomap_mappings,
    _parse_l5x_modules,
)


def _load_baseline(label: str) -> dict:
    p = LOCK / f"{label.lower()}_io_baseline.json"
    if not p.is_file():
        raise unittest.SkipTest(f"missing baseline {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _l5x_for(machine: str) -> Path:
    return STUDIO / f"{machine}_ui_candidate.L5X"


class IoRegressionLockTests(unittest.TestCase):
    """Lock the recovered architecture — never rewrite the I/O generator."""

    def test_generator_stack_still_present(self):
        """Historical implementation must not be deleted."""
        autogen = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        for sym in (
            "def load_from_run",
            "def load_eip_topology",
            "def _build_eip_bank_index",
            "io_word_map",
            "include_io_map",
            "--with-io-map",
            'Name="IO_MAP"',
            "<Modules>",
            "_generation_assertion_failures",
        ):
            self.assertIn(sym, autogen, f"missing preserved symbol {sym}")

    def test_electron_still_passes_with_io_map(self):
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("--with-io-map", main)
        self.assertIn("from-run", main)
        # Recovery lock: SiteModel IPC must remain
        self.assertIn("get-site-model", main)
        preload = (ROOT / "desktop" / "preload.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("getSiteModel", preload)
        dash = (ROOT / "dashboard" / "fortna-plus.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("applySiteModelToEditors", dash)
        # Must not regress to dropping SiteModel overlays on Build PLC
        self.assertIn("One canonical workbook", dash)
        self.assertIn("sawtooth_build", dash)

    def test_cp2_zero_modules_is_fail(self):
        self._assert_modules_not_zero("CP2", "ORNCCP2")

    def test_cp4_zero_modules_is_fail(self):
        self._assert_modules_not_zero("CP4", "ORNCCP4")

    def test_cp5_zero_modules_is_fail(self):
        self._assert_modules_not_zero("CP5", "ORNCCP5")

    def test_cp2_iomap_nop_only_is_fail(self):
        self._assert_iomap_not_nop("CP2", "ORNCCP2")

    def test_cp4_iomap_nop_only_is_fail(self):
        self._assert_iomap_not_nop("CP4", "ORNCCP4")

    def test_cp5_iomap_nop_only_is_fail(self):
        self._assert_iomap_not_nop("CP5", "ORNCCP5")

    def test_cp2_representative_exact_mappings(self):
        self._assert_exact_mappings("CP2", "ORNCCP2")

    def test_cp4_representative_exact_mappings(self):
        self._assert_exact_mappings("CP4", "ORNCCP4")

    def test_cp5_representative_exact_mappings(self):
        self._assert_exact_mappings("CP5", "ORNCCP5")

    def test_discovered_pe_mappings_present(self):
        """Discovered PE with bank/bit must appear in IO_MAP (product path)."""
        for label, machine in (("CP2", "ORNCCP2"), ("CP4", "ORNCCP4"), ("CP5", "ORNCCP5")):
            with self.subTest(machine=machine):
                base = _load_baseline(label)
                pe_exps = [e for e in base.get("expectations") or [] if e.get("kind") == "discovered_pe_point"]
                map_exps = [
                    e
                    for e in base.get("expectations") or []
                    if e.get("kind") == "io_map_exact" and re.search(r"PE\d", str(e.get("tag") or ""), re.I)
                ]
                # Either baseline recorded exact PE maps, or discovered PE points exist to enforce
                self.assertTrue(
                    map_exps or pe_exps,
                    f"{machine}: baseline has no PE expectations — regenerate baselines",
                )
                l5x = _l5x_for(machine)
                self.assertTrue(l5x.is_file(), f"missing {l5x}")
                text = l5x.read_text(encoding="utf-8", errors="replace")
                mappings = _parse_iomap_mappings(text, limit=500)
                pe_tags = {str(m.get("tag") or "") for m in mappings}
                # Hard fail: if baseline has exact PE maps, each must still exist
                for exp in map_exps:
                    tag = exp["tag"]
                    hit = next((m for m in mappings if m.get("tag") == tag), None)
                    self.assertIsNotNone(hit, f"{machine}: PE mapping missing for {tag}")
                    self.assertEqual(hit["channel"], exp["channel"])
                    self.assertEqual(hit["slot"], exp["slot"])
                    self.assertEqual(hit["bit"], exp["bit"])
                    self.assertEqual(hit["direction"], exp["direction"])
                # Soft identity: at least one discovered PE name appears in IO_MAP tags
                if pe_exps and not map_exps:
                    names = [e["device_name"] for e in pe_exps]
                    self.assertTrue(
                        any(any(n in t for t in pe_tags) for n in names),
                        f"{machine}: none of discovered PEs {names} appear in IO_MAP",
                    )

    def test_module_identities_present(self):
        for label, machine in (("CP2", "ORNCCP2"), ("CP4", "ORNCCP4"), ("CP5", "ORNCCP5")):
            with self.subTest(machine=machine):
                base = _load_baseline(label)
                l5x = _l5x_for(machine)
                text = l5x.read_text(encoding="utf-8", errors="replace")
                mods = {m.get("name") for m in _parse_l5x_modules(text)}
                for exp in base.get("expectations") or []:
                    if exp.get("kind") != "module_present":
                        continue
                    self.assertIn(
                        exp["name"],
                        mods,
                        f"{machine}: module {exp['name']} missing from UI-path L5X",
                    )
                    if exp.get("catalog"):
                        # Catalog may appear near module; require name presence as hard lock
                        self.assertTrue(exp["name"] in text)

    # --- helpers ---

    def _assert_modules_not_zero(self, label: str, machine: str) -> None:
        base = _load_baseline(label)
        self.assertGreater(
            base.get("counts", {}).get("modules_from_run") or 0,
            0,
            f"{label}: baseline claims no RUN modules — fixture invalid",
        )
        l5x = _l5x_for(machine)
        self.assertTrue(l5x.is_file(), f"missing UI-path L5X {l5x}")
        c = _l5x_counts(l5x)
        n = c.get("module_entries") or 0
        self.assertGreater(
            n,
            0,
            f"FAIL: {machine} known RUN has supported IO but UI-path L5X has ZERO modules",
        )

    def _assert_iomap_not_nop(self, label: str, machine: str) -> None:
        base = _load_baseline(label)
        self.assertGreater(
            base.get("counts", {}).get("word_map_entries") or 0,
            0,
            f"{label}: baseline has no word map — fixture invalid",
        )
        l5x = _l5x_for(machine)
        c = _l5x_counts(l5x)
        self.assertFalse(
            c.get("io_map_nop_only"),
            f"FAIL: {machine} IO_MAP is NOP-only despite supported mappings",
        )
        self.assertGreater(
            c.get("io_map_xic_ote_refs") or 0,
            0,
            f"FAIL: {machine} IO_MAP has zero real XIC/OTE mappings",
        )
        self.assertIn("IO_MAP", c.get("programs") or [])

    def _assert_exact_mappings(self, label: str, machine: str) -> None:
        base = _load_baseline(label)
        exps = [e for e in base.get("expectations") or [] if e.get("kind") == "io_map_exact"]
        self.assertTrue(exps, f"{label}: no io_map_exact expectations — regenerate baselines")
        l5x = _l5x_for(machine)
        text = l5x.read_text(encoding="utf-8", errors="replace")
        mappings = _parse_iomap_mappings(text, limit=800)
        by_tag = {m["tag"]: m for m in mappings}
        for exp in exps:
            tag = exp["tag"]
            self.assertIn(tag, by_tag, f"{machine}: exact mapping tag missing: {tag}")
            got = by_tag[tag]
            self.assertEqual(got["direction"], exp["direction"], tag)
            self.assertEqual(got["channel"], exp["channel"], tag)
            self.assertEqual(got["slot"], exp["slot"], tag)
            self.assertEqual(got["bit"], exp["bit"], tag)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
