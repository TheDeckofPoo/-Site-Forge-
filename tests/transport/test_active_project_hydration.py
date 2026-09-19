#!/usr/bin/env python3
"""Active Project hydration contract — one RUN, all editors."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FP = ROOT / "dashboard" / "fortna-plus.js"
TB = ROOT / "dashboard" / "transport-build.js"
IDX = ROOT / "dashboard" / "index.html"
MAIN = ROOT / "desktop" / "main.js"


class TestActiveProjectHydration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fp = FP.read_text(encoding="utf-8")
        cls.tb = TB.read_text(encoding="utf-8")
        cls.html = IDX.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_hydrate_active_project_exists(self) -> None:
        self.assertIn("async function hydrateActiveProject", self.fp)
        self.assertIn("async function ensureTransportHydrated", self.fp)
        self.assertIn("async function ensureSafetyHydrated", self.fp)

    def test_init_uses_hydrate_contract(self) -> None:
        idx = self.fp.find("async function init()")
        self.assertGreater(idx, 0)
        chunk = self.fp[idx : idx + 2500]
        self.assertIn("hydrateActiveProject", chunk)
        self.assertIn("application startup", chunk)

    def test_import_uses_same_hydrate_contract(self) -> None:
        idx = self.fp.find("async function importRunPackage")
        self.assertGreater(idx, 0)
        # Look at post-import section
        chunk = self.fp[idx : idx + 12000]
        self.assertIn("hydrateActiveProject", chunk)
        self.assertIn("forceTransport: true", chunk)
        # Must not keep a separate one-off transportAutoBuild call path only
        self.assertIn("Transport canvas cleared for new RUN", chunk)

    def test_transport_tab_safety_net(self) -> None:
        idx = self.fp.find("function activateTab")
        chunk = self.fp[idx : idx + 1800]
        self.assertIn("ensureTransportHydrated", chunk)
        self.assertIn("transport tab", chunk)
        self.assertIn("ensureSafetyHydrated", chunk)

    def test_active_run_toolbar_present(self) -> None:
        self.assertIn('id="tb-active-run"', self.html)
        self.assertIn('id="tb-rebuild-active-run"', self.html)
        self.assertIn("Rebuild from Active RUN", self.html)

    def test_empty_state_distinguishes_no_project(self) -> None:
        self.assertIn("NO ACTIVE PROJECT", self.html)
        self.assertIn("data-tb-empty-title", self.html)
        self.assertIn("tb-empty-retry", self.html)
        self.assertIn("function updateTransportEmptyState", self.fp)
        self.assertIn("TRANSPORT BUILD FAILED", self.fp)

    def test_boot_waits_for_transport_api(self) -> None:
        self.assertIn("async function bootSiteForge", self.fp)
        self.assertIn("transportAutoBuildFromRun", self.fp)

    def test_demo_smoke_hook_present(self) -> None:
        self.assertIn("SITEFORGE_DEMO_SMOKE", self.main)
        self.assertIn("runMscrenoDemoSmoke", self.main)
        self.assertIn("MSCRENO_DEMO_READINESS", self.main)

    def test_rebuild_button_forces_hydrate(self) -> None:
        self.assertIn("engineer rebuild", self.tb)
        self.assertIn("ensureTransportHydrated", self.tb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
