#!/usr/bin/env python3
"""Browse Archive / Load RUN wiring contracts (renderer + preload + main)."""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestBrowseArchiveWiring(unittest.TestCase):
    def test_fortna_plus_syntax(self) -> None:
        r = subprocess.run(
            ["node", "--check", str(ROOT / "dashboard" / "fortna-plus.js")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr or r.stdout)

    def test_renderer_browse_helpers(self) -> None:
        js = (ROOT / "dashboard" / "fortna-plus.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("async function browseAndImportRunArchive", js)
        self.assertIn("btn-io-browse-run", js)
        self.assertIn("btn-browse-archive", js)
        self.assertIn("selectArchive", js)
        self.assertIn("Unable to open RUN archive picker", js)
        self.assertIn("isRunArchivePath", js)
        # Syntax is enforced by test_fortna_plus_syntax (node --check).

    def test_preload_exposes_select_archive(self) -> None:
        pre = (ROOT / "desktop" / "preload.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("selectArchive:", pre)
        self.assertIn("importRun:", pre)
        self.assertIn("getPathForFile:", pre)

    def test_main_select_archive_handler(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ipcMain.handle('select-archive'", main)
        self.assertIn("showOpenDialog", main)
        self.assertIn("All Files", main)
        self.assertIn("Unable to open RUN archive picker", main)
        self.assertIn(".tar.gz", main)

    def test_html_buttons_exist(self) -> None:
        html = (ROOT / "dashboard" / "index.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('id="btn-io-browse-run"', html)
        self.assertIn('id="btn-browse-archive"', html)
        self.assertIn('id="io-run-dropzone"', html)

    def test_launcher_ascii_provenance(self) -> None:
        ps1 = (ROOT / "desktop" / "Launch-Electron.ps1").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("PROVENANCE:", ps1)
        self.assertIn(" -> ", ps1)
        self.assertNotIn("→", ps1)


if __name__ == "__main__":
    unittest.main()
