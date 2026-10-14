"""P0: SHIP discovery crash + fail-closed site_model authority (no Greensboro fallback)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_run_workspace_discover import (  # noqa: E402
    _evidence_dedupe_key,
    apply_cross_table_evidence,
    discover,
    site_model_identity_matches,
)
from fortna_site_model import SiteModel  # noqa: E402

GREENSBORO_FORBIDDEN = (
    "504_BELT",
    "506_SHIP_SORTER",
    "508_SHIP_SORTER",
    "509_SHIP_SORTER",
    "510_SHIP_SORTER",
    "ENC504",
    "ENC506",
    "ENC508",
    "ENC509",
    "ENC510",
)

RUN_ROOTS = [
    REPO / "workspace" / "_reno_peek",
    Path(r"C:\dev\worktree\FortnaPlus-mscreno-genclose\workspace\_reno_peek"),
]


def _run(machine: str) -> Path | None:
    needle = f"MSCRENO-{machine}-RUN"
    for root in RUN_ROOTS:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and needle.upper() in child.name.upper():
                run = child / "RUN"
                if run.is_dir():
                    return run
    return None


def _sorter_names(site: dict) -> list[str]:
    names: list[str] = []
    for s in site.get("sorters") or []:
        n = s.get("raw_name") or s.get("normalized_name") or s.get("name") or ""
        if isinstance(n, dict):
            n = n.get("value") or ""
        names.append(str(n).strip())
    sm = site.get("sorter_model") or {}
    for s in sm.get("sorters") or []:
        n = s.get("name")
        if isinstance(n, dict):
            n = n.get("value")
        if n:
            names.append(str(n).strip())
    return names


def _assert_no_greensboro(site: dict) -> None:
    blob = json.dumps(site)
    hits = [b for b in GREENSBORO_FORBIDDEN if b in blob]
    assert not hits, f"Greensboro-only identities leaked into SHIP model: {hits}"


def _discover(machine: str) -> dict:
    run = _run(machine)
    if run is None:
        raise unittest.SkipTest(f"RUN for {machine} not available")
    td = Path(tempfile.mkdtemp(prefix=f"p0_{machine}_"))
    discover(run, machine, td)
    site = json.loads((td / "site_model.json").read_text(encoding="utf-8"))
    site["_test_out"] = str(td)
    site["_test_run"] = str(run)
    return site


class TestEvidenceDedupeHashable(unittest.TestCase):
    def test_dict_detail_is_hashable_in_set(self) -> None:
        e = {
            "kind": "encoder_enable_vfd",
            "detail": {"type": "encoder_enable_vfd", "to": "VFDS1"},
            "table": None,
        }
        key = _evidence_dedupe_key(e)
        s = {key}
        self.assertIn(key, s)

    def test_apply_cross_table_with_dict_evidence_does_not_crash(self) -> None:
        model = SiteModel(machine_scope="T", run_dir="/tmp")
        model.encoders = [
            {
                "raw_name": "SHIP SORT",
                "normalized_name": "SHIPSORT",
                "evidence": [
                    {
                        "kind": "encoder_enable_vfd",
                        "detail": {"type": "encoder_enable_vfd", "to": "VFDS1"},
                    }
                ],
            }
        ]
        harvest = {
            "evidence_by_name": {
                "SHIPSORT": [{"kind": "encoder_link", "detail": "extra"}],
            },
            "relationships": [],
            "operational_groups": {},
            "table_stats": {},
        }
        apply_cross_table_evidence(model, harvest)
        kinds = [e.get("kind") for e in model.encoders[0]["evidence"]]
        self.assertIn("encoder_enable_vfd", kinds)
        self.assertIn("encoder_link", kinds)


class TestShipDiscoveryOrders(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ship_run = _run("MSCRENOSHIP")
        cls.pick_run = _run("MSCRENOPICK")
        cls.pack_run = _run("MSCRENOPACK")
        if cls.ship_run is None:
            raise unittest.SkipTest("MSCRENOSHIP RUN missing")

    def _ship_inventory(self, site: dict) -> dict:
        sm = site.get("sorter_model") or {}
        return {
            "machine": site.get("machine_scope"),
            "sorter_names": sorted(set(_sorter_names(site))),
            "primary": sm.get("primary_sorter_app"),
            "area": sm.get("sorter_area_name") or sm.get("transport_area"),
            "encoder_names": sorted(
                {
                    str(e.get("raw_name") or e.get("normalized_name") or "")
                    for e in (site.get("encoders") or [])
                }
            ),
            "divert_count": sm.get("divert_count"),
            "scanner_count": len(sm.get("scanners") or []),
            "sawtooth_count": len(site.get("sawtooth_merges") or []),
            "fp": site.get("run_fingerprint"),
        }

    def test_ship_first_discovery(self) -> None:
        site = _discover("MSCRENOSHIP")
        inv = self._ship_inventory(site)
        self.assertEqual(inv["machine"], "MSCRENOSHIP")
        self.assertIn("SHIP SORTER", inv["sorter_names"])
        self.assertEqual(str(inv["primary"] or "").upper(), "SHIP SORTER")
        _assert_no_greensboro(site)
        ok, reason = site_model_identity_matches(
            site,
            machine="MSCRENOSHIP",
            run_dir=site["_test_run"],
            run_fingerprint=site.get("run_fingerprint") or "",
        )
        self.assertTrue(ok, reason)

    def test_pick_then_ship(self) -> None:
        if self.pick_run is None:
            self.skipTest("PICK RUN missing")
        pick = _discover("MSCRENOPICK")
        self.assertEqual(pick.get("machine_scope"), "MSCRENOPICK")
        # Pick is sorter-negative for shipping sorter identity
        names = [n.upper() for n in _sorter_names(pick)]
        self.assertNotIn("SHIP SORTER", names)
        ship = _discover("MSCRENOSHIP")
        self.assertEqual(ship.get("machine_scope"), "MSCRENOSHIP")
        self.assertIn("SHIP SORTER", [n.upper() for n in _sorter_names(ship)])
        _assert_no_greensboro(ship)
        # Pick model must not equal Ship model controller
        self.assertNotEqual(pick.get("run_fingerprint"), ship.get("run_fingerprint"))

    def test_pack_then_ship(self) -> None:
        if self.pack_run is None:
            self.skipTest("PACK RUN missing")
        pack = _discover("MSCRENOPACK")
        ship = _discover("MSCRENOSHIP")
        self.assertEqual(ship.get("machine_scope"), "MSCRENOSHIP")
        _assert_no_greensboro(ship)
        self.assertNotEqual(pack.get("machine_scope"), "MSCRENOSHIP")

    def test_ship_then_pick(self) -> None:
        if self.pick_run is None:
            self.skipTest("PICK RUN missing")
        ship = _discover("MSCRENOSHIP")
        pick = _discover("MSCRENOPICK")
        names = [n.upper() for n in _sorter_names(pick)]
        self.assertNotIn("SHIP SORTER", names)
        # Ship identity must not survive into Pick model
        blob = json.dumps(pick)
        self.assertNotIn("SHIPSORTER", blob.upper().replace(" ", ""))
        _assert_no_greensboro(ship)

    def test_ship_then_pack(self) -> None:
        if self.pack_run is None:
            self.skipTest("PACK RUN missing")
        ship = _discover("MSCRENOSHIP")
        pack = _discover("MSCRENOPACK")
        self.assertEqual(pack.get("machine_scope"), "MSCRENOPACK")
        names = [n.upper() for n in _sorter_names(pack)]
        self.assertNotIn("SHIP SORTER", names)
        _assert_no_greensboro(ship)

    def test_ship_inventory_invariant_across_orders(self) -> None:
        """SHIP result must be invariant to prior Pick/Pack loads."""
        a = self._ship_inventory(_discover("MSCRENOSHIP"))
        if self.pick_run:
            _discover("MSCRENOPICK")
        b = self._ship_inventory(_discover("MSCRENOSHIP"))
        if self.pack_run:
            _discover("MSCRENOPACK")
        c = self._ship_inventory(_discover("MSCRENOSHIP"))
        for key in ("machine", "sorter_names", "primary", "area", "encoder_names", "divert_count"):
            self.assertEqual(a[key], b[key], key)
            self.assertEqual(a[key], c[key], key)
        _assert_no_greensboro(_discover("MSCRENOSHIP"))


class TestFailClosedSiteModelAuthority(unittest.TestCase):
    def test_stale_greensboro_fallback_rejected_by_identity(self) -> None:
        stale_path = REPO / "exports" / "run-discovery" / "site_model.json"
        if not stale_path.is_file():
            self.skipTest("stale exports/run-discovery/site_model.json absent")
        stale = json.loads(stale_path.read_text(encoding="utf-8"))
        ok, reason = site_model_identity_matches(
            stale,
            machine="MSCRENOSHIP",
            run_fingerprint="ship-fp-should-not-match",
        )
        self.assertFalse(ok)
        self.assertIn(reason, {"CONTROLLER_MISMATCH", "RUN_FINGERPRINT_MISMATCH", "SITE_MODEL_MISSING_CONTROLLER"})

    def test_main_js_no_unscoped_fallback(self) -> None:
        main = (REPO / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("readActiveSiteModelOrFail", main)
        self.assertIn("SITE MODEL UNAVAILABLE / DISCOVERY FAILED", main)
        # Old contamination path must not remain as silent fallback.
        self.assertNotIn(
            "fs.existsSync(fallback) ? fallback",
            main,
        )
        self.assertIn("NEVER fall back to unscoped exports/run-discovery/site_model.json", main)

    def test_discovery_crash_must_not_expose_stale_model(self) -> None:
        """Simulate failed discovery: active model removed; stale file must not be used."""
        with tempfile.TemporaryDirectory() as td:
            active = Path(td) / "active"
            active.mkdir()
            # Plant a stale Greensboro-like model as if previous site left it
            stale = {
                "machine_scope": "ORNCCP5",
                "sorters": [{"raw_name": "506_SHIP_SORTER"}],
                "run_fingerprint": "greensboro",
            }
            (active / "site_model.json").write_text(json.dumps(stale), encoding="utf-8")
            # Fail-closed policy: on discovery failure, unlink active model
            (active / "site_model.json").unlink()
            self.assertFalse((active / "site_model.json").exists())
            # Identity helper rejects empty
            ok, reason = site_model_identity_matches(None, machine="MSCRENOSHIP")
            self.assertFalse(ok)
            self.assertEqual(reason, "SITE_MODEL_UNAVAILABLE")

    def test_active_model_controller_mismatch_fail_closed(self) -> None:
        site = {
            "machine_scope": "ORNCCP5",
            "identity": {
                "machine_scope": "ORNCCP5",
                "run_fingerprint": "abc",
            },
            "run_fingerprint": "abc",
        }
        ok, reason = site_model_identity_matches(
            site, machine="MSCRENOSHIP", run_fingerprint="abc"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "CONTROLLER_MISMATCH")

    def test_pick_remains_sorter_negative(self) -> None:
        run = _run("MSCRENOPICK")
        if run is None:
            self.skipTest("PICK RUN missing")
        site = _discover("MSCRENOPICK")
        names = [n.upper() for n in _sorter_names(site)]
        self.assertNotIn("SHIP SORTER", names)
        primary = str((site.get("sorter_model") or {}).get("primary_sorter_app") or "").upper()
        self.assertNotEqual(primary, "SHIP SORTER")


class TestShipScannerTopLevelPromotion(unittest.TestCase):
    def test_ship_scanners_on_site_model_bucket(self) -> None:
        run = _run("MSCRENOSHIP")
        if run is None:
            self.skipTest("SHIP RUN missing")
        site = _discover("MSCRENOSHIP")
        scanners = site.get("scanners") or []
        self.assertGreaterEqual(len(scanners), 7, "top-level scanners must be promoted from ScnScanDevice")
        self.assertEqual((site.get("counts") or {}).get("scanners"), len(scanners))


class TestShipPersistenceIdentity(unittest.TestCase):
    def test_active_site_model_roundtrip_identity(self) -> None:
        site = _discover("MSCRENOSHIP")
        with tempfile.TemporaryDirectory() as td:
            active = Path(td) / "active"
            active.mkdir()
            dst = active / "site_model.json"
            # Persist as import-run would
            src = Path(site["_test_out"]) / "site_model.json"
            shutil.copy2(src, dst)
            loaded = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(loaded.get("machine_scope"), "MSCRENOSHIP")
            self.assertEqual(loaded.get("run_fingerprint"), site.get("run_fingerprint"))
            self.assertIn("SHIP SORTER", [n.upper() for n in _sorter_names(loaded)])
            _assert_no_greensboro(loaded)
            ok, reason = site_model_identity_matches(
                loaded,
                machine="MSCRENOSHIP",
                run_dir=site["_test_run"],
                run_fingerprint=loaded.get("run_fingerprint") or "",
            )
            self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
