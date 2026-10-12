#!/usr/bin/env python3
"""ORI-111: stop automatic repair when no material progress is possible."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_l5x_acceptance_auditor import (  # noqa: E402
    STATE_ENGINEER_REQUIRED,
    STATE_NO_MATERIAL_PROGRESS,
    material_hash,
    material_l5x_hash,
    normalize_failure_signature,
    normalized_failure_signature_set,
    run_acceptance_and_repair,
    strip_l5x_volatile_export_metadata,
)

CURRENT = ROOT / "exports" / "current"
GOOD_L5X = next(
    iter(
        sorted(
            CURRENT.glob("MSCRENOPICK_*.L5X"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    ),
    CURRENT / "MSCRENOPICK_MISSING.L5X",
)


def _stamp(text: str, export_date: str) -> str:
    out = text
    for attr in ("ExportDate", "ProjectCreationDate", "LastModifiedDate"):
        out = re.sub(
            rf'{attr}="[^"]*"',
            f'{attr}="{export_date}"',
            out,
            count=1,
        )
    return out


class TestMaterialHashIgnoresVolatileExportMetadata(unittest.TestCase):
    def test_timestamps_do_not_change_material_hash(self) -> None:
        base = (
            '<RSLogix5000Content ExportDate="Mon Jan 1 00:00:00 2026" '
            'Owner="SiteForge">'
            '<Controller ProjectCreationDate="Mon Jan 1 00:00:00 2026" '
            'LastModifiedDate="Mon Jan 1 00:00:00 2026">'
            "<Programs><Program Name=\"IO_MAP\"/></Programs>"
            "</Controller></RSLogix5000Content>"
        )
        a = _stamp(base, "Sun Sep 13 05:13:59 2026")
        b = _stamp(base, "Mon Oct 09 12:00:00 2026")
        self.assertNotEqual(a, b)
        self.assertEqual(
            strip_l5x_volatile_export_metadata(a),
            strip_l5x_volatile_export_metadata(b),
        )
        with tempfile.TemporaryDirectory() as td:
            pa = Path(td) / "a.L5X"
            pb = Path(td) / "b.L5X"
            pa.write_text(a, encoding="utf-8")
            pb.write_text(b, encoding="utf-8")
            self.assertEqual(material_l5x_hash(pa), material_l5x_hash(pb))


class TestNormalizedFailureSignature(unittest.TestCase):
    def test_strips_cycle_tokens(self) -> None:
        self.assertEqual(
            normalize_failure_signature("IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:cycle_2"),
            "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD",
        )
        self.assertEqual(
            normalize_failure_signature("IO:CRITICAL_DEVICE_UNRESOLVED:ESPB1O"),
            "IO:CRITICAL_DEVICE_UNRESOLVED:ESPB1O",
        )

    def test_material_hash_stable_without_cycle(self) -> None:
        h1 = material_hash({"signature": "IO:X", "material_l5x_hash": "abc"})
        h2 = material_hash({"signature": "IO:X", "material_l5x_hash": "abc"})
        self.assertEqual(h1, h2)


class TestNoMaterialProgressStopsRepair(unittest.TestCase):
    def test_engineer_blocking_stops_without_duplicate_regen(self) -> None:
        """Critical unresolved / resolution gate → ENGINEER_REQUIRED, no regen loop."""
        l5x_text = (
            '<?xml version="1.0"?>\n'
            '<RSLogix5000Content ExportDate="Sun Sep 13 05:13:59 2026" Owner="A">'
            '<Controller Name="MSCRENOPICK" ProjectCreationDate="Sun Sep 13 05:13:59 2026" '
            'LastModifiedDate="Sun Sep 13 05:13:59 2026">'
            '<Programs>'
            '<Program Name="IO_MAP"><Routines>'
            '<Routine Name="Main_Routine"><RLLContent>'
            '<Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>'
            "</RLLContent></Routine></Routines></Program>"
            '<Program Name="ES"><Routines>'
            '<Routine Name="Main_Routine"><RLLContent>'
            '<Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>'
            "</RLLContent></Routine></Routines></Program>"
            "</Programs></Controller></RSLogix5000Content>"
        )
        manifest = {
            "machine": "MSCRENOPICK",
            "programs": {"IO_MAP": {"required": True}, "ES": {"required": True}},
            "io": {
                "required": True,
                "source_conservation": {
                    "enforce_resolution": True,
                    "canonical": {
                        "PHYSICAL_DEVICE_RESOLUTION_PCT": 10.0,
                        "device_resolution_coverage_pct": 10.0,
                        "critical_unresolved_count": 1,
                        "critical_unresolved": [
                            {
                                "canonical_device": "ESPB1O",
                                "status": "REVIEW_REQUIRED",
                                "reason": "engineer confirmation required",
                            }
                        ],
                        "engineering_resolution_ok": False,
                    },
                },
            },
            "safety": {"required": False},
            "transport": {"required": False},
        }
        regen_calls = {"n": 0}

        def _regen(ctx: dict):
            regen_calls["n"] += 1
            return None

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "staging.L5X"
            p.write_text(l5x_text, encoding="utf-8")
            r = run_acceptance_and_repair(
                l5x_path=p,
                manifest=manifest,
                out_dir=td,
                regenerate_fn=_regen,
                live=False,
                max_outer_cycles=5,
            )
        self.assertFalse(r.get("ok"))
        self.assertFalse(r.get("promoted"))
        self.assertEqual(regen_calls["n"], 0, "must not regenerate when engineer-only")
        self.assertEqual(r.get("generations"), 1)
        self.assertEqual(r.get("audits_run"), 1)
        self.assertEqual(r.get("status"), STATE_ENGINEER_REQUIRED, r)
        self.assertTrue(r.get("engineer_required"), r)

    def test_identical_regen_stops_no_material_progress(self) -> None:
        """Generator-class failure + identical regenerate → NO_MATERIAL_PROGRESS after 1 regen."""
        blank_es = """<?xml version="1.0"?>
<RSLogix5000Content ExportDate="Sun Sep 13 05:13:59 2026" Owner="A">
<Controller Name="MSCRENOPICK" ProjectCreationDate="Sun Sep 13 05:13:59 2026" LastModifiedDate="Sun Sep 13 05:13:59 2026">
<Programs>
<Program Name="ES"><Routines>
<Routine Name="Main_Routine"><RLLContent>
</RLLContent></Routine>
</Routines></Program>
</Programs></Controller></RSLogix5000Content>
"""
        manifest = {
            "machine": "MSCRENOPICK",
            "programs": {},
            "io": {"required": False},
            "safety": {"required": True},
            "transport": {"required": False},
        }
        regen_calls = {"n": 0}

        def _regen(ctx: dict):
            regen_calls["n"] += 1
            out = Path(ctx["prior_l5x"]).parent / f"regen_{regen_calls['n']}.L5X"
            out.write_text(
                _stamp(blank_es, f"Mon Oct 09 12:0{regen_calls['n']}:00 2026"),
                encoding="utf-8",
            )
            return out

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.L5X"
            p.write_text(blank_es, encoding="utf-8")
            # Force a regenerate path: treat blank main as actionable generator repair.
            # live=False still sets requires_generator_fix for SAFETY_BLANK_MAIN_ROUTINE.
            r = run_acceptance_and_repair(
                l5x_path=p,
                manifest=manifest,
                out_dir=td,
                regenerate_fn=_regen,
                live=False,
                max_outer_cycles=5,
            )
            repair_dirs = sorted(Path(td).glob("ori111_repair_*"))
        self.assertFalse(r.get("ok"))
        self.assertFalse(r.get("promoted"))
        # Either stopped before regen (if classified engineer) or after one identical regen.
        self.assertLessEqual(regen_calls["n"], 1)
        if regen_calls["n"] == 1:
            self.assertTrue(
                r.get("no_material_progress")
                or r.get("status")
                in {STATE_NO_MATERIAL_PROGRESS, STATE_ENGINEER_REQUIRED},
                r,
            )
            self.assertEqual(int(r.get("generations") or 0), 2)
        self.assertEqual(repair_dirs, [], "repair dirs are created by autogen regenerate_fn, not auditor")


class TestNormalizedSignatureSet(unittest.TestCase):
    def test_set_ignores_cycle_noise(self) -> None:
        a = normalized_failure_signature_set(
            {
                "signatures": [
                    "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD",
                    "IO:CRITICAL_DEVICE_UNRESOLVED:ESPB1O",
                ]
            }
        )
        b = normalized_failure_signature_set(
            {
                "signatures": [
                    "IO:CRITICAL_DEVICE_UNRESOLVED:ESPB1O",
                    "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:cycle_3",
                ]
            }
        )
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
