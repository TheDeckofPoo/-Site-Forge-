#!/usr/bin/env python3
"""Hard tests for PLC2 Configio-primary physical word resolver."""
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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_autogen import load_from_run  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
    parse_configio_desc,
    resolve_word_bit,
)

RUN = ROOT / "workspace" / "active" / "RUN"
RESOLVER_SRC = SCRIPTS / "fortna_physical_word_resolver.py"


class TestPlc2ConfigioCompiler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RUN / "project.cfg").is_file() and (RUN.parent / "RUN" / "project.cfg").is_file():
            pass
        cls.run_dir = RUN if (RUN / "project.cfg").is_file() else ROOT / "workspace" / "active"
        if (cls.run_dir / "RUN" / "project.cfg").is_file():
            cls.run_dir = cls.run_dir / "RUN"
        assert (cls.run_dir / "project.cfg").is_file(), f"missing RUN at {cls.run_dir}"
        cls.pm = build_physical_word_map(cls.run_dir, "ORNCCP2")
        cls.resolver = PhysicalWordResolver(cls.run_dir, "ORNCCP2")

    def test_word_201_bit0_resolves_with_provenance(self):
        hit = resolve_word_bit(self.pm, 201, 0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.get("channel"), "CP2RIO0:I.Data[1].0")
        self.assertTrue(hit.get("provenance"))
        self.assertEqual(hit.get("resolve_how"), "configio_physical")
        self.assertIn("Configio.asc", hit["provenance"].get("source_tables") or [])

    def test_word_307_bit0_resolves_p400_aux_path(self):
        hit = resolve_word_bit(self.pm, 307, 0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.get("channel"), "CP3RIO0:I.Data[7].0")
        self.assertEqual(hit.get("panel"), "CP3")
        self.assertEqual(hit.get("direction"), "I")

    def test_fortna_physical_logical_survive(self):
        """2PBSTART / M400_AUX / a PE / a motor output survive Fortna→physical→logical."""
        _, rows = read_asc(self.run_dir / "FORTNA" / "Conveyor.asc")
        by_name = {}
        for r in rows:
            n = (r.get("IO_Name") or "").strip()
            if not n:
                continue
            try:
                w = int(float(r.get("IO_Address_Word") or 0))
            except Exception:
                continue
            by_name[n.upper()] = (w, (r.get("IO_Address_Bit") or "").strip(), r)

        # 2PBSTART
        w, b, _ = by_name["2PBSTART"]
        hit = self.resolver.resolve(w, b)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("channel"), "CP2RIO0:I.Data[1].0")
        self.assertTrue(str(hit.get("channel") or "").startswith("CP2RIO0:I."))

        # M400_AUX
        w, b, _ = by_name["M400_AUX"]
        hit = self.resolver.resolve(w, b)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("channel"), "CP3RIO0:I.Data[7].0")

        # A PE on an owned word
        pe = next(
            (
                n
                for n, (ww, bb, rr) in by_name.items()
                if n.startswith("PE")
                and ww in {int(x) for x in (self.pm.get("words") or {})}
            ),
            None,
        )
        self.assertIsNotNone(pe, "expected a PE on a configio-owned word")
        w, b, _ = by_name[pe]
        hit = self.resolver.resolve(w, b)
        self.assertIsNotNone(hit, f"PE {pe} word {w} bit {b} unresolved")
        self.assertIn(":I.Data[", hit.get("channel") or "")

        # Motor output M124
        w, b, _ = by_name["M124"]
        hit = self.resolver.resolve(w, b)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("channel"), "CP2RIO0:O.Data[2].0")

    def test_no_hardcoded_201_to_cp2rio0(self):
        src = RESOLVER_SRC.read_text(encoding="utf-8")
        # Forbid hard-coded dict / literal mapping 201 → CP2RIO0
        banned = [
            r"201\s*:\s*[\"']CP2RIO0[\"']",
            r"[\"']201[\"']\s*:\s*[\"']CP2RIO0[\"']",
            r"\{[^}]*201[^}]*CP2RIO0[^}]*\}",
        ]
        for pat in banned:
            self.assertIsNone(
                re.search(pat, src),
                f"hard-coded 201→CP2RIO0 pattern found: {pat}",
            )
        # CP2RIO0 may appear in docs/comments/tests of scheme, but not as a word map literal
        self.assertNotIn("201→CP2RIO0", src.replace(" ", ""))
        self.assertNotIn('201: "CP2RIO0"', src)
        self.assertNotIn("201: 'CP2RIO0'", src)

    def test_load_from_run_owns_word_201(self):
        inp = load_from_run(self.run_dir)
        self.assertIn("201", inp.io_word_map or {})
        info = (inp.io_word_map or {})["201"]
        self.assertEqual(info.get("rio_name"), "CP2RIO0")
        self.assertEqual(info.get("resolve_how"), "configio_physical")
        rios = [t.get("rio_name") for t in (inp.eip_topology or [])]
        self.assertIn("CP2RIO0", rios)
        self.assertIn("CP3RIO0", rios)
        self.assertTrue(
            all(not str(r).startswith("T_1794") for r in rios),
            f"expected Configio panel RIO names, got {rios}",
        )

    def test_parse_greensboro_desc(self):
        p = parse_configio_desc("CP2-1794-IA16-3")
        self.assertEqual(p["panel"], "CP2")
        self.assertEqual(p["catalog"], "1794-IA16")
        self.assertEqual(p["index"], "3")
        p2 = parse_configio_desc("CP31794-IA16-31")
        self.assertEqual(p2["panel"], "CP3")


if __name__ == "__main__":
    unittest.main()
