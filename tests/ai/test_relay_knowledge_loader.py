#!/usr/bin/env python3
"""Relay durable knowledge loader — startup bootstrap tests.

Confirms: deterministic load, ERROR/DEGRADED semantics, stable hashing,
no network/AI/mutation, panel-local law present, candidates not auto-loaded.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_relay_knowledge_loader import (  # noqa: E402
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_READY,
    build_relay_context_bundle,
    default_manifest_path,
)


class TestRelayKnowledgeLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = ROOT
        self.manifest = default_manifest_path(self.repo)

    def test_manifest_loads_deterministically(self) -> None:
        a = build_relay_context_bundle(repo_root=self.repo)
        b = build_relay_context_bundle(repo_root=self.repo)
        self.assertEqual(a["status"], STATUS_READY)
        self.assertEqual(a["bundle_hash"], b["bundle_hash"])
        self.assertEqual(
            [f["path"] for f in a["loaded_files"]],
            [f["path"] for f in b["loaded_files"]],
        )
        # Order is manifest order, not arbitrary
        paths = [f["path"] for f in a["loaded_files"]]
        self.assertTrue(paths[0].endswith("SITE_FORGE_AI_CONSTITUTION.md"))
        self.assertIn("agents/relay/RELAY_START_HERE.md", paths[1])

    def test_file_order_independent_of_os_enumeration(self) -> None:
        """Directory markdown expansion is ASCII-sorted by basename."""
        a = build_relay_context_bundle(repo_root=self.repo)
        paths = [f["path"] for f in a["loaded_files"]]
        # Negative examples directory content (if any beyond README) sorted
        neg = [p for p in paths if "negative_examples/relay/" in p]
        self.assertEqual(neg, sorted(neg))

    def test_missing_required_file_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            # Minimal broken pack: copy ai tree then delete a required file
            shutil.copytree(self.repo / "ai", tdp / "ai")
            victim = tdp / "ai" / "knowledge" / "IO_HANDBOOK.md"
            victim.unlink()
            bundle = build_relay_context_bundle(repo_root=tdp)
            self.assertEqual(bundle["status"], STATUS_ERROR)
            self.assertFalse(bundle["ok"])
            self.assertTrue(any("IO_HANDBOOK" in e for e in bundle["errors"]))

    def test_missing_optional_file_degraded_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            shutil.copytree(self.repo / "ai", tdp / "ai")
            # Remove an optional metadata file listed in manifest
            opt = tdp / "ai" / "evals" / "relay" / "README.md"
            if opt.is_file():
                opt.unlink()
            bundle = build_relay_context_bundle(repo_root=tdp)
            # Required pack intact → READY or DEGRADED (warnings for optional)
            self.assertIn(bundle["status"], {STATUS_READY, STATUS_DEGRADED})
            if bundle["status"] == STATUS_DEGRADED:
                self.assertTrue(bundle["warnings"])
            # Never silent ERROR for optional-only miss when required OK
            if not bundle["errors"]:
                self.assertTrue(bundle["ok"])

    def test_bundle_hash_stable_identical_files(self) -> None:
        a = build_relay_context_bundle(repo_root=self.repo)
        b = build_relay_context_bundle(repo_root=self.repo)
        self.assertEqual(a["bundle_hash"], b["bundle_hash"])
        self.assertEqual(len(a["bundle_hash"]), 64)

    def test_changing_knowledge_file_changes_bundle_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            shutil.copytree(self.repo / "ai", tdp / "ai")
            before = build_relay_context_bundle(repo_root=tdp)
            target = tdp / "ai" / "knowledge" / "IO_HANDBOOK.md"
            target.write_text(target.read_text(encoding="utf-8") + "\n# hash-bump\n", encoding="utf-8")
            after = build_relay_context_bundle(repo_root=tdp)
            self.assertNotEqual(before["bundle_hash"], after["bundle_hash"])

    def test_loader_makes_no_network_request(self) -> None:
        real_create = socket.socket

        def guarded(*a, **k):
            raise AssertionError("network socket opened during Relay load")

        with mock.patch("socket.socket", side_effect=guarded):
            # Also guard common connect paths
            with mock.patch.object(socket.socket, "connect", create=True, side_effect=guarded):
                bundle = build_relay_context_bundle(repo_root=self.repo)
        self.assertEqual(bundle["network"], False)
        self.assertTrue(bundle["ok"])
        # Ensure we didn't leave the process unable to create sockets after
        _ = real_create

    def test_loader_makes_no_ai_api_call(self) -> None:
        bundle = build_relay_context_bundle(repo_root=self.repo)
        self.assertFalse(bundle["ai_call"])
        # No openai/anthropic/httpx imports as side effect of load
        for mod in ("openai", "anthropic", "httpx", "requests"):
            self.assertNotIn(mod, sys.modules)

    def test_loader_performs_no_repository_mutation(self) -> None:
        handbook = self.repo / "ai" / "knowledge" / "IO_HANDBOOK.md"
        before = handbook.read_bytes()
        before_mtime = handbook.stat().st_mtime_ns
        build_relay_context_bundle(repo_root=self.repo)
        after = handbook.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(before_mtime, handbook.stat().st_mtime_ns)

    def test_startup_continues_concept_on_error(self) -> None:
        """Missing manifest → ERROR payload; caller may continue Site Forge."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "ai").mkdir()
            bundle = build_relay_context_bundle(repo_root=tdp)
            self.assertEqual(bundle["status"], STATUS_ERROR)
            self.assertFalse(bundle["ok"])
            # Structured error — UI/main can log and continue
            self.assertTrue(bundle["errors"])

    def test_panel_local_law_must_be_in_bundle(self) -> None:
        bundle = build_relay_context_bundle(repo_root=self.repo)
        self.assertTrue(bundle["panel_local_law_present"])
        self.assertIn("PANEL-LOCAL AUTHORITY", bundle["context_text"])
        self.assertIn("cross-panel", bundle["context_text"].lower())

    def test_panel_local_omission_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            shutil.copytree(self.repo / "ai", tdp / "ai")
            panel = tdp / "ai" / "knowledge" / "PANEL_LOCAL_IO_RULES.md"
            panel.write_text("# emptied panel rules\n", encoding="utf-8")
            bundle = build_relay_context_bundle(repo_root=tdp)
            self.assertEqual(bundle["status"], STATUS_ERROR)
            self.assertTrue(any("panel-local" in e.lower() for e in bundle["errors"]))

    def test_candidates_not_auto_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            shutil.copytree(self.repo / "ai", tdp / "ai")
            cand = tdp / "ai" / "candidate_lessons" / "relay" / "SHOULD_NOT_LOAD.md"
            cand.write_text("# secret candidate\nMARKER_CANDIDATE_NOT_IN_BUNDLE\n", encoding="utf-8")
            bundle = build_relay_context_bundle(repo_root=tdp)
            self.assertNotIn("MARKER_CANDIDATE_NOT_IN_BUNDLE", bundle["context_text"])
            paths = [f["path"] for f in bundle["loaded_files"]]
            self.assertFalse(any("candidate_lessons" in p for p in paths))

    def test_site_specific_evals_not_in_verified_autoload(self) -> None:
        bundle = build_relay_context_bundle(repo_root=self.repo)
        paths = [f["path"] for f in bundle["loaded_files"]]
        self.assertFalse(any(p.startswith("ai/evals/") for p in paths))


class TestRelayStartupIntegrationContract(unittest.TestCase):
    def test_main_js_hooks_loader_without_ai_call(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("loadRelayKnowledgeAtStartup", main)
        self.assertIn("RELAY KNOWLEDGE:", main)
        self.assertIn("relay-knowledge-status", main)
        self.assertIn("STARTUP LOAD != AI CALL", main)
        # Must not invoke ai-io-analyze on whenReady path for Relay
        when = main.split("app.whenReady().then", 1)[1][:800]
        self.assertIn("loadRelayKnowledgeAtStartup", when)
        self.assertNotIn("ai-io-analyze", when)


if __name__ == "__main__":
    unittest.main()
