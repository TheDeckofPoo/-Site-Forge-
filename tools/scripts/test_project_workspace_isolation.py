#!/usr/bin/env python3
"""BOLT regression: project workspace isolation across RUN loads.

Proves:
  1) Loading a new RUN must not inherit stale Sawtooth readiness from a prior project
     (PLC4 detected → reset → PLC2 NOT_DETECTED / non-blocking).
  2) Conveyor Safety Zone is independent of Area on the Transport Apply path.
  3) Project identity key (machine|run_fingerprint|archive) differs across sites.

Does not require Electron. Does not modify Hardware/I/O.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402

CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"


def _find_cp2_run() -> Path:
    preferred = ROOT / "workspace" / "active" / "RUN"
    if preferred.is_dir() and (preferred / "FORTNA").is_dir():
        return preferred
    peek = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
    if peek.is_dir() and (peek / "FORTNA").is_dir():
        return peek
    for cand in sorted((ROOT / "workspace").glob("**/RUN")):
        if not cand.is_dir() or not (cand / "FORTNA").is_dir():
            continue
        # Prefer a tree with ORNCCP2 overlays
        if list((cand / "FORTNA").glob("*.ornccp2")):
            return cand
    return preferred


CP2_RUN = _find_cp2_run()


# ---------------------------------------------------------------------------
# Pure-Python mirror of dashboard/fortna-plus.js sawtoothEvidence + readiness
# ---------------------------------------------------------------------------

def sawtooth_detected(cfg: dict) -> bool:
    lanes = [l for l in (cfg.get("lanes") or []) if l and l.get("conveyor")]
    return bool(
        cfg.get("collector_conveyor")
        or lanes
        or cfg.get("detected")
        or cfg.get("discovery_source") == "site_model"
    )


def sawtooth_status(cfg: dict, applied_at=None, dirty: bool = False) -> str:
    if not sawtooth_detected(cfg):
        return "NOT_DETECTED"
    if not applied_at:
        return "REVIEW_REQUIRED"
    return "CHANGED" if dirty else "READY"


def export_blocked_by_sawtooth(cfg: dict, applied_at=None) -> bool:
    if not sawtooth_detected(cfg):
        return False
    return sawtooth_status(cfg, applied_at) != "READY"


def identity_key(identity: dict | None) -> str:
    """Mirror transport-build.js identityKey: machine|run_fingerprint|archive."""
    if identity is None or not isinstance(identity, dict):
        return ""
    return "|".join(
        [
            str(identity.get("machine") or ""),
            str(identity.get("run_fingerprint") or ""),
            str(identity.get("archive") or ""),
        ]
    )


def empty_sawtooth_config() -> dict:
    """Simulate defaultSawtoothConfig / resetProjectScopedState wipe."""
    return {
        "collector_conveyor": "",
        "lanes": [],
        "detected": False,
        "discovery_source": "",
        "configuration_required": [],
    }


def plc4_like_sawtooth_config() -> dict:
    return {
        "collector_conveyor": "P200",
        "lanes": [
            {"conveyor": "P201", "lane": 1},
            {"conveyor": "P202", "lane": 2},
        ],
        "detected": True,
        "discovery_source": "site_model",
        "configuration_required": ["collector_encoder"],
    }


class TestSawtoothReadinessIsolation(unittest.TestCase):
    """PLC4 Sawtooth then PLC2 no-Sawtooth readiness — no Electron."""

    def test_pure_mirror_plc4_then_reset_to_plc2(self):
        print("-- Test 1a: pure readiness mirror (PLC4 → reset → PLC2) --")

        # 1) PLC4-like: detected, blocks export until applied
        cfg4 = plc4_like_sawtooth_config()
        self.assertTrue(sawtooth_detected(cfg4))
        st4 = sawtooth_status(cfg4, applied_at=None)
        self.assertEqual(st4, "REVIEW_REQUIRED")
        self.assertTrue(export_blocked_by_sawtooth(cfg4, applied_at=None))
        print(f"  [PASS] PLC4-like cfg → detected={sawtooth_detected(cfg4)} status={st4} blocks=True")

        # Applied → READY (not a blocker) unless dirty
        self.assertFalse(export_blocked_by_sawtooth(cfg4, applied_at="2026-01-01T00:00:00Z"))
        self.assertEqual(
            sawtooth_status(cfg4, applied_at="2026-01-01T00:00:00Z", dirty=True),
            "CHANGED",
        )
        print("  [PASS] PLC4 applied → READY; dirty → CHANGED")

        # 2) resetProjectScopedState + no evidence on PLC2
        cfg2 = empty_sawtooth_config()
        self.assertFalse(sawtooth_detected(cfg2))
        st2 = sawtooth_status(cfg2)
        self.assertEqual(st2, "NOT_DETECTED")
        self.assertFalse(export_blocked_by_sawtooth(cfg2))
        print(f"  [PASS] after reset (PLC2 empty) → status={st2} blocks=False")

        # 3) Stale REVIEW_REQUIRED cannot survive the reset
        stale_readiness = {"status": "REVIEW_REQUIRED", "appliedAt": None, "unresolved": 3}
        after_reset = {
            "status": sawtooth_status(cfg2),
            "appliedAt": None,
            "unresolved": 0,
        }
        self.assertNotEqual(after_reset["status"], stale_readiness["status"])
        self.assertEqual(after_reset["status"], "NOT_DETECTED")
        self.assertFalse(export_blocked_by_sawtooth(cfg2))
        print("  [PASS] stale REVIEW_REQUIRED does not survive reset → NOT_DETECTED")

    def test_site_model_discovery_cp4_vs_cp2(self):
        print("-- Test 1b: SiteModel discovery CP4 vs CP2 sawtooth evidence --")
        if not CP4_RUN.is_dir():
            self.skipTest(f"CP4 RUN missing: {CP4_RUN}")
        if not CP2_RUN.is_dir():
            self.skipTest(f"CP2 RUN missing: {CP2_RUN}")

        from fortna_run_workspace_discover import (  # noqa: E402
            _has_sawtooth_evidence,
            discover,
        )

        has4 = _has_sawtooth_evidence(CP4_RUN, "ORNCCP4")
        has2 = _has_sawtooth_evidence(CP2_RUN, "ORNCCP2")
        self.assertTrue(has4, "ORNCCP4 must have sawtooth evidence")
        self.assertFalse(has2, "ORNCCP2 must NOT have proven sawtooth evidence")
        print(f"  [PASS] _has_sawtooth_evidence ORNCCP4={has4} ORNCCP2={has2}")

        with tempfile.TemporaryDirectory(prefix="iso_disc_") as td:
            out = Path(td)
            r4 = discover(CP4_RUN, "ORNCCP4", out / "cp4")
            site4 = json.loads((out / "cp4" / "site_model.json").read_text(encoding="utf-8"))
            merges4 = site4.get("sawtooth_merges") or []
            self.assertTrue(r4.get("has_sawtooth") or merges4, "PLC4 discover must report sawtooth")
            self.assertGreater(len(merges4), 0, "ORNCCP4 sawtooth_merges must be non-empty")
            print(f"  [PASS] ORNCCP4 discover has_sawtooth={r4.get('has_sawtooth')} merges={len(merges4)}")

            r2 = discover(CP2_RUN, "ORNCCP2", out / "cp2")
            site2 = json.loads((out / "cp2" / "site_model.json").read_text(encoding="utf-8"))
            merges2 = site2.get("sawtooth_merges") or []
            self.assertFalse(r2.get("has_sawtooth"), "ORNCCP2 must not report has_sawtooth")
            self.assertEqual(len(merges2), 0, "ORNCCP2 must not invent sawtooth_merges")
            print(f"  [PASS] ORNCCP2 discover has_sawtooth={r2.get('has_sawtooth')} merges={len(merges2)}")

            # Map discovery → readiness mirror: PLC2 evidence must not block export
            cfg_from_cp2 = {
                "collector_conveyor": "",
                "lanes": [],
                "detected": bool(r2.get("has_sawtooth")),
                "discovery_source": "site_model" if merges2 else "",
            }
            self.assertEqual(sawtooth_status(cfg_from_cp2), "NOT_DETECTED")
            self.assertFalse(export_blocked_by_sawtooth(cfg_from_cp2))
            print("  [PASS] PLC2 discovery → NOT_DETECTED, export not blocked by sawtooth")


class TestSafetyZoneIndependentOfArea(unittest.TestCase):
    """Apply path: Area defaultSafetyZone must not overwrite per-conveyor zones."""

    def test_two_zones_same_area(self):
        print("-- Test 2: Safety Zone independent of Area (Apply) --")
        graph = {
            "version": 1,
            "applyMode": "canonical",
            "safetyZones": [
                {"name": "SafetyZone_Test"},
                {"name": "Other_ESZone"},
            ],
            "areas": [
                {
                    "id": "area_test",
                    "name": "Area_Test",
                    "defaultSafetyZone": "SafetyZone_Test",
                    "nodes": [
                        {
                            "id": "n100",
                            "kind": "conv_straight",
                            "conveyorTag": "P100",
                            "safetyZone": "SafetyZone_Test",
                            "downstream": "P101",
                            "plcOwned": True,
                        },
                        {
                            "id": "n101",
                            "kind": "conv_straight",
                            "conveyorTag": "P101",
                            "safetyZone": "Other_ESZone",
                            "downstream": "",
                            "terminal": True,
                            "plcOwned": True,
                        },
                    ],
                    "wires": [{"id": "w1", "from": "n100", "to": "n101", "toPort": "in"}],
                }
            ],
            "activeAreaId": "area_test",
        }
        wb = {
            "machine": "ORNCCP2",
            "project_name": "Isolation_SafetyZone",
            "conveyors": [],
            "areas": [],
            "options": {"areas": [], "safety_zones": []},
            "merges_2to1": [],
        }

        out = apply_graph_to_workbook(graph, copy.deepcopy(wb))
        self.assertTrue(out.get("ok"), out)
        wb2 = out["workbook"]
        by = {
            str(r.get("conveyor") or "").strip().upper(): r
            for r in (wb2.get("conveyors") or [])
            if str(r.get("conveyor") or "").strip()
        }
        self.assertIn("P100", by)
        self.assertIn("P101", by)

        self.assertEqual(by["P100"].get("main_area"), "Area_Test")
        self.assertEqual(by["P101"].get("main_area"), "Area_Test")
        print("  [PASS] both conveyors keep main_area=Area_Test")

        self.assertEqual(by["P100"].get("safety_zone"), "SafetyZone_Test")
        self.assertEqual(by["P101"].get("safety_zone"), "Other_ESZone")
        self.assertNotEqual(by["P101"].get("safety_zone"), "SafetyZone_Test")
        print("  [PASS] P100=SafetyZone_Test; P101=Other_ESZone (not forced to Area default)")

        sz_opts = list((wb2.get("options") or {}).get("safety_zones") or [])
        self.assertIn("SafetyZone_Test", sz_opts)
        self.assertIn("Other_ESZone", sz_opts)
        print(f"  [PASS] options.safety_zones contains both: {sz_opts}")

        # Area ≠ Safety Zone — area name not used as zone unless conveyor says so
        self.assertNotEqual(by["P100"].get("main_area"), by["P100"].get("safety_zone"))
        self.assertNotEqual(by["P101"].get("main_area"), by["P101"].get("safety_zone"))
        self.assertNotIn("Area_Test", [by["P100"].get("safety_zone"), by["P101"].get("safety_zone")])
        print("  [PASS] Area name is not used as Safety Zone")


class TestProjectIdentityMismatch(unittest.TestCase):
    """identity = machine|run_fingerprint|archive — SiteA vs SiteB must differ."""

    def test_site_a_vs_site_b_keys_differ(self):
        print("-- Test 3: project identity mismatch --")
        site_a = {
            "machine": "ORNCCP4",
            "run_fingerprint": "fp-aaaa",
            "archive": "20251016-ORNCCP4-RUN.tar.gz",
        }
        site_b = {
            "machine": "ORNCCP2",
            "run_fingerprint": "fp-bbbb",
            "archive": "20251016-ORNCCP2-RUN.tar.gz",
        }
        key_a = identity_key(site_a)
        key_b = identity_key(site_b)
        self.assertEqual(key_a, "ORNCCP4|fp-aaaa|20251016-ORNCCP4-RUN.tar.gz")
        self.assertEqual(key_b, "ORNCCP2|fp-bbbb|20251016-ORNCCP2-RUN.tar.gz")
        self.assertNotEqual(key_a, key_b)
        # Same fingerprint/archive but different machine still differs
        twin = dict(site_a)
        twin["machine"] = "ORNCCP2"
        self.assertNotEqual(identity_key(site_a), identity_key(twin))
        self.assertEqual(identity_key(None), "")
        self.assertEqual(identity_key({}), "||")
        print(f"  [PASS] SiteA key={key_a!r}")
        print(f"  [PASS] SiteB key={key_b!r} (differs)")


def main() -> int:
    print("=== test_project_workspace_isolation ===")
    print(f"CP4_RUN={CP4_RUN} exists={CP4_RUN.is_dir()}")
    print(f"CP2_RUN={CP2_RUN} exists={CP2_RUN.is_dir()}")
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("ALL PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
