#!/usr/bin/env python3
"""Twin gaps session isolation + compact JSON emit (parser root-cause guard)."""
from __future__ import annotations

# --- siteforge test path bootstrap ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# --- end bootstrap ---

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fortna_prism_twin as twin  # noqa: E402


class TwinGapsSessionIsolation(unittest.TestCase):
    def test_gap_identity_ok_rejects_foreign_machine(self):
        data = {"machine": "MSCATL", "gaps": [{"id": "g1"}]}
        self.assertFalse(
            twin._gap_identity_ok(data, machine="MSCRENOSHIP", archive_sha="")
        )
        self.assertTrue(
            twin._gap_identity_ok(data, machine="MSCATL", archive_sha="")
        )

    def test_load_gaps_skips_foreign_machine_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp)
            foreign = {
                "machine": "MSCATL",
                "gaps": [{"id": "old", "message": "from MSCATL"}],
                "gap_count": 1,
            }
            (export / "twin_gaps.json").write_text(
                json.dumps(foreign), encoding="utf-8"
            )
            with mock.patch.object(twin, "_latest_export_gaps", return_value=None):
                with mock.patch.object(twin, "_active_site", return_value="TestSite"):
                    with mock.patch.object(
                        twin, "_site_dir", return_value=export / "prism"
                    ):
                        out = twin.load_gaps(
                            export_dir=str(export),
                            machine="MSCRENOSHIP",
                            archive_sha="abc",
                        )
            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("gaps"), [])
            self.assertTrue(any(
                s.get("reason") == "identity_mismatch" for s in (out.get("skipped") or [])
            ))

    def test_load_gaps_accepts_matching_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp)
            payload = {
                "machine": "MSCRENOSHIP",
                "run_fingerprint": "abc",
                "gaps": [{"id": "g1", "message": "current"}],
                "gap_count": 1,
            }
            (export / "twin_gaps.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with mock.patch.object(twin, "_latest_export_gaps", return_value=None):
                with mock.patch.object(twin, "_active_site", return_value="TestSite"):
                    with mock.patch.object(
                        twin, "_site_dir", return_value=export / "prism"
                    ):
                        out = twin.load_gaps(
                            export_dir=str(export),
                            machine="MSCRENOSHIP",
                            archive_sha="abc",
                        )
            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("gap_count"), 1)
            self.assertEqual(out["gaps"][0]["id"], "g1")

    def test_cli_emits_single_line_json(self):
        """Root cause guard: indent=2 + last-line parse → Unexpected token }."""
        import subprocess

        r = subprocess.run(
            [
                _SFSys.executable,
                str(_SF_SCRIPTS / "fortna_prism_twin.py"),
                "load-gaps",
                "--machine",
                "NOSUCH",
                "--archive-sha",
                "none",
            ],
            cwd=str(_SF_REPO),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        out = (r.stdout or "").strip()
        self.assertTrue(out, msg=f"stderr={r.stderr!r}")
        # Must be one JSON object (no pretty-print newlines)
        self.assertNotIn("\n", out, msg="twin CLI must emit compact single-line JSON")
        parsed = json.loads(out)
        self.assertIn("ok", parsed)
        # Last-line parse of pretty JSON historically failed; compact must round-trip
        self.assertEqual(json.loads(out.splitlines()[-1]), parsed)


class EngineerAreaPersistence(unittest.TestCase):
    def test_area_1lksadfj_not_sanitized_by_graph_apply(self):
        """Intentional engineer area on MSCRENOSHIP must survive Apply naming path."""
        from fortna_transport_graph import apply_graph_to_workbook  # noqa: WPS433

        wb = {
            "version": 1,
            "kind": "fortna_autogen_workbook",
            "machine": "MSCRENOSHIP",
            "project_name": "Reno_MSCRENOSHIP",
            "conveyors": [
                {
                    "number": 1,
                    "include": True,
                    "conveyor": "P10",
                    "main_area": "MSCRENOSHIP_Area",
                    "safety_zone": "MSCRENOSHIP_ESZone1",
                    "type": "Transport with MS",
                    "source": "run",
                }
            ],
            "areas": [
                {
                    "name": "MSCRENOSHIP_Area",
                    "safety_zone": "MSCRENOSHIP_ESZone1",
                    "conveyor_count": 1,
                }
            ],
            "options": {
                "areas": ["MSCRENOSHIP_Area"],
                "safety_zones": ["MSCRENOSHIP_ESZone1"],
            },
        }
        graph = {
            "version": 1,
            "areas": [
                {
                    "id": "area_eng",
                    "name": "Area_1lksadfj",
                    "nodes": [
                        {
                            "id": "n1",
                            "kind": "conv_straight",
                            "label": "P10",
                            "conveyorTag": "P10",
                            "downstream": "",
                            "x": 10,
                            "y": 10,
                            "devices": [],
                        }
                    ],
                    "wires": [],
                }
            ],
        }
        result = apply_graph_to_workbook(graph, wb)
        self.assertTrue(result.get("ok"), msg=str(result.get("summary") or result))
        out = result.get("workbook") or {}
        names = [
            str(a.get("name") or "")
            for a in (out.get("areas") or [])
            if isinstance(a, dict)
        ]
        opt = [str(x) for x in (out.get("options") or {}).get("areas") or []]
        applied = [str(x) for x in (result.get("areas_applied") or [])]
        self.assertIn(
            "Area_1lksadfj",
            names + opt + applied,
            msg=f"engineer area purged unexpectedly: areas={names} options={opt} applied={applied}",
        )
        mains = [
            str(r.get("main_area") or "")
            for r in (out.get("conveyors") or [])
            if isinstance(r, dict)
        ]
        self.assertIn("Area_1lksadfj", mains)


if __name__ == "__main__":
    unittest.main()
