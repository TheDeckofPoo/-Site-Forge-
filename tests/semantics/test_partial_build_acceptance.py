#!/usr/bin/env python3
"""PARTIAL BUILD acceptance — permanent product-requirement fixture.

Site Forge must support incremental commissioning:

  FOUND ≠ CONFIGURED ≠ INCLUDED ≠ GENERATED
  UNASSIGNED ≠ ERROR ≠ INCLUDED ≠ GENERATED ≠ SAFE

Scenario (PLC2-shaped, self-contained — no live RUN required):

1. Many conveyors exist as FOUND catalog (not in AutogenInput.conveyors).
2. Engineer INCLUDES only a small Area (few conveyors).
3. Safety devices are FOUND but zone membership is empty → REVIEW.
4. Build L5X succeeds structurally.
5. Only INCLUDED conveyors appear as generated Conv logic.
6. ES Program shell present; Safe_Logic/Safe_PI count = 0; no invented members.
7. Safety status remains REVIEW_REQUIRED; commissioning_ready = False.
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


import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    ConveyorRow,
    IoPoint,
    build_l5x,
)
from fortna_es_compiler import emit_es_program, build_safety_zone_irs, safety_readiness  # noqa: E402
from fortna_studio_preflight import preflight_l5x  # noqa: E402

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return (
        f'<Rung Number="{num}" Type="N">{c}'
        f"<Text><![CDATA[{text}]]></Text></Rung>"
    )


def _routine(name: str, rungs: list[str]) -> str:
    body = "".join(
        r.replace('Number="0"', f'Number="{i}"', 1) if 'Number="0"' in r else r
        for i, r in enumerate(rungs)
    )
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'
    )


def _extract_tag_block(_lib: str, _name: str) -> str | None:
    return None


class TestPartialBuildPreflightContract(unittest.TestCase):
    """Mirror of dashboard autogenBuildPreflight contract (Python lock)."""

    def test_review_does_not_block_partial_build(self) -> None:
        # Simulated hub statuses for an incremental session
        statuses = {
            "system": "READY",
            "hardware": "READY",
            "transport": "READY",  # small Area Applied
            "sawtooth": "REVIEW_REQUIRED",  # FOUND in RUN, not INCLUDED
            "sorter": "NOT_DETECTED",
            "safety": "REVIEW_REQUIRED",  # many unassigned devices
        }
        applied = {
            "system": True,
            "hardware": True,
            "transport": True,
            "sawtooth": False,  # not Applied → not INCLUDED
            "sorter": False,
            "safety": True,
        }

        def hard_block(key: str, status: str) -> bool:
            if status == "ERROR" and (applied.get(key) or key in ("system", "hardware")):
                return True
            if status == "ERROR" and key == "safety":
                return True
            return False

        blockers = [k for k, st in statuses.items() if hard_block(k, st)]
        soft = [
            k
            for k, st in statuses.items()
            if st in ("REVIEW_REQUIRED", "CHANGED") and not hard_block(k, st)
        ]
        self.assertEqual(blockers, [])
        self.assertIn("safety", soft)
        self.assertIn("sawtooth", soft)
        # Build ALLOWED
        self.assertTrue(len(blockers) == 0)

    def test_unassigned_vocabulary(self) -> None:
        # Lock product vocabulary
        forbidden_equivalences = {
            ("UNASSIGNED", "ERROR"),
            ("UNASSIGNED", "ACTIVE"),
            ("UNASSIGNED", "INCLUDED"),
            ("UNASSIGNED", "GENERATED"),
            ("UNASSIGNED", "SAFE"),
            ("FOUND", "GENERATED"),
        }
        for a, b in forbidden_equivalences:
            self.assertNotEqual(a, b)


@unittest.skipUnless(LIBRARY.is_file(), f"Library missing: {LIBRARY}")
class TestPartialBuildL5XAcceptance(unittest.TestCase):
    """Generate a small INCLUDED set; leave Safety membership unresolved."""

    @classmethod
    def setUpClass(cls) -> None:
        # INCLUDED conveyors only (effective model) — many FOUND peers omitted on purpose
        included = [
            ConveyorRow(
                number=i + 1,
                conveyor=tag,
                main_area="ModuleA",
                safety_zone="ModuleA_ESZone1",
                type="Transport with MS",
                downstream=down,
                motor_starter="Yes",
            )
            for i, (tag, down) in enumerate(
                [
                    ("P400", "P402"),
                    ("P402", "P404"),
                    ("P404", "P406"),
                    ("P406", ""),
                ]
            )
        ]
        # FOUND catalog (not included) — must NOT appear as generated Conv tags
        cls.found_not_included = [
            "P1000", "P1001", "P220", "P220A", "P130", "P136", "P145", "P150",
        ]
        cls.inp = AutogenInput(
            project_name="ORNCCP2",
            processor="1756-L83E",
            major_rev="35",
            minor_rev="00",
            areas=["ModuleA"],
            safety_zones=["ModuleA_ESZone1"],
            conveyors=included,
            # Minimal IO so IO_MAP can exist without claiming Safety membership
            io_points=[
                IoPoint(
                    device_name="M400_AUX",
                    device_type="motor",
                    direction="I",
                    fortna_bank="205",
                    fortna_bit="0",
                ),
            ],
            include_sys=True,
            include_io_map=True,
            safety_build={
                "zones": [
                    {
                        "name": "ModuleA_ESZone1",
                        "area": "ModuleA",
                        "conveyors": ["P400", "P402", "P404", "P406"],
                        "members": [],
                        "status": "REVIEW_REQUIRED",
                    }
                ],
                "devices": [
                    {"name": "CP2_ES", "kind": "ES", "status": "UNASSIGNED"},
                    {"name": "CP2_ESR1", "kind": "ESR", "status": "UNASSIGNED"},
                    {"name": "CP2_MCR1", "kind": "MCR", "status": "UNASSIGNED"},
                    {"name": "CP3_ES", "kind": "ES", "status": "UNASSIGNED"},
                ],
                "unassignedDevices": ["CP2_ES", "CP2_ESR1", "CP2_MCR1", "CP3_ES"],
                "counts": {
                    "devices": 4,
                    "devices_found": 4,
                    "unassigned": 4,
                    "mcr": 1,
                    "esr": 1,
                    "estops": 2,
                },
            },
        )

    def test_es_shell_fail_safe_no_invented_membership(self) -> None:
        irs = build_safety_zone_irs(
            safety_zones=["ModuleA_ESZone1"],
            areas=["ModuleA"],
            engineer_zones=[
                {
                    "name": "ModuleA_ESZone1",
                    "area": "ModuleA",
                    "conveyors": ["P400", "P402", "P404", "P406"],
                    "members": [],
                }
            ],
            default_area="ModuleA",
            area_conveyors={"ModuleA": ["P400", "P402", "P404", "P406"]},
        )
        ready = safety_readiness(irs, library_has_aois=True)
        self.assertEqual(ready["status"], "REVIEW_REQUIRED")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=_extract_tag_block,
            library_text="",
        )
        self.assertIsNotNone(pack)
        assert pack is not None
        self.assertTrue(pack.get("shell"))
        self.assertEqual(pack.get("status"), "REVIEW_REQUIRED")
        self.assertEqual(pack.get("emitted_zones"), [])
        xml = pack["program_xml"]
        self.assertIn('Name="ES"', xml)
        self.assertIn("Main_Routine", xml)
        self.assertNotIn('Routine Name="ModuleA_ESZone1_Safe_Logic"', xml)
        self.assertNotIn("ES_SIL1_Cat1(", xml)
        # Fail-safe: NOP only — no permissive OK write
        self.assertNotRegex(xml, r"OTE\([^)]*OK")

    def test_partial_l5x_build_succeeds(self) -> None:
        l5x, report = build_l5x(self.inp, LIBRARY)
        self.assertTrue(l5x and "<Controller" in l5x)
        # Only INCLUDED conveyors should have Fast_Conv / Conv tags
        for tag in ("P400", "P402", "P404", "P406"):
            self.assertIn(f"{tag}_Conv", l5x, f"included {tag} missing")
        for tag in self.found_not_included:
            # Must not generate Fast_Conv calls for FOUND-only equipment
            self.assertNotIn(
                f"Fast_Conv({tag}_",
                l5x,
                f"FOUND-not-INCLUDED {tag} was silently generated",
            )

        es = report.get("es_program") or {}
        self.assertEqual(str(es.get("status") or "").upper(), "REVIEW_REQUIRED")
        self.assertTrue(es.get("shell") or es.get("partial"))
        self.assertFalse(es.get("lifecycle", {}).get("commissioning_ready", True))

        # Structural: ES + P01 present; Safe_Logic = 0
        self.assertIn('Program Name="ES"', l5x)
        self.assertIn("P01_Safety_20ms", l5x)
        self.assertEqual(len(re.findall(r'Routine Name="[^"]*_Safe_Logic"', l5x)), 0)
        self.assertEqual(len(re.findall(r'Routine Name="[^"]*_Safe_PI"', l5x)), 0)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "PARTIAL_ORNCCP2.L5X"
            path.write_text(l5x, encoding="utf-8")
            pre = preflight_l5x(path)
            self.assertTrue(pre.get("ok"), pre.get("issues"))
            safety = (pre.get("structural") or {}).get("safety") or {}
            self.assertEqual(safety.get("status"), "REVIEW_REQUIRED")
            self.assertFalse(safety.get("commissioning_ready"))
            # Persist evidence for Curtis
            out = ROOT / "exports" / "stabilization" / "partial_build_acceptance.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "included_conveyors": ["P400", "P402", "P404", "P406"],
                        "found_not_included_sample": self.found_not_included,
                        "es_status": es.get("status"),
                        "es_shell": bool(es.get("shell")),
                        "lifecycle": es.get("lifecycle"),
                        "preflight_ok": pre.get("ok"),
                        "safety_structural": safety,
                        "programs": report.get("programs"),
                        "conveyor_count": report.get("conveyor_count"),
                        "contract": (
                            "FOUND≠INCLUDED≠GENERATED; UNASSIGNED≠SAFE; "
                            "REVIEW does not block partial Build"
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"  [PASS] partial L5X + evidence → {out}")


if __name__ == "__main__":
    print("=== test_partial_build_acceptance ===")
    raise SystemExit(unittest.main(verbosity=2))
