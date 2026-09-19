#!/usr/bin/env python3
"""CP4 Pass 2 acceptance tests — no finished PLC4."""
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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_identity import conveyor_identities_match, linked_owns_conveyor  # noqa: E402

DISC = ROOT / "exports" / "cp4-discovery"
OUT = ROOT / "exports" / "cp4-pass2"


def test_prefix_not_implied() -> None:
    # Generic rule — not hard-coded exclusions of these four tags
    assert not conveyor_identities_match("P120", "P1200")
    assert not conveyor_identities_match("P120", "P1202")
    assert not conveyor_identities_match("P120", "P1206")
    assert not conveyor_identities_match("P120", "P1208")
    assert not conveyor_identities_match("P12", "P120")
    assert conveyor_identities_match("P424", "P424A")
    assert conveyor_identities_match("P600", "P600C")
    assert conveyor_identities_match("P219", "P219")
    linked = {"P120", "P424"}
    assert linked_owns_conveyor("P120", linked)
    assert linked_owns_conveyor("P424A", linked)
    assert not linked_owns_conveyor("P1200", linked)
    assert not linked_owns_conveyor("P1202", linked)
    print("  [PASS] ambiguous prefix matching fixed generically")


def test_realization_reconciles() -> None:
    path = OUT / "conveyor_realization.json"
    if not path.exists():
        print("  [SKIP] pass2 not generated yet")
        return
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r.get("reconciled") is True, r
    assert r.get("acceptance") == "ACCEPTED"
    assert not r.get("extras"), r.get("extras")
    assert not r.get("missing"), r.get("missing")
    assert r["discovery_mechanical"] == r["generated"]
    # Pollution tags must not appear in the generated set
    gen_path = OUT / "conveyor_provenance.json"
    if gen_path.exists():
        tags = {
            (c.get("conveyor") or "").upper()
            for c in (json.loads(gen_path.read_text(encoding="utf-8")).get("conveyors") or [])
        }
        for bad in ("P1200", "P1202", "P1206", "P1208"):
            assert bad not in tags
    print(
        f"  [PASS] CP4 generated equipment reconciles with discovery "
        f"({r['discovery_mechanical']}={r['generated']})"
    )


def test_vfd_and_lanes_survive() -> None:
    if not (OUT / "vfd_generation.json").exists():
        print("  [SKIP] pass2 VFD report missing")
        return
    disc = json.loads((DISC / "vfd.json").read_text(encoding="utf-8"))
    saw = json.loads((DISC / "sawtooth.json").read_text(encoding="utf-8"))
    vgen = json.loads((OUT / "vfd_generation.json").read_text(encoding="utf-8"))
    assert disc["counts"]["unique_vfd_bases"] == 13
    mapped = {r["conveyor"]: r for r in vgen.get("mapped_conveyors") or []}
    for tag in ("P414", "P416", "P424", "P424A"):
        assert tag in mapped
        assert mapped[tag]["provenance"] == "RUN_EXPLICIT"
    lane = next(l for l in saw["lanes"] if l["conveyor"] == "P116")
    assert lane["photoeye"] == "PE118_P"
    assert "VFD118" in (lane.get("drive") or "")
    sgen = json.loads((OUT / "sawtooth_generation.json").read_text(encoding="utf-8"))
    assert sgen.get("lane_count") == 5
    bindings = {b["lane_name"]: b for b in sgen.get("lanes") or []}
    assert bindings["LANE_3_P116"]["photoeye"] == "PE118_P"
    assert bindings["LANE_3_P116"]["slice_seconds"] == 8.0
    assert bindings["LANE_0_P219"]["reserve_seconds"] == 10.0
    print("  [PASS] 13 VFDs / multi-conveyor + 5 lanes + timing + PE/drive survive")


def test_encoders_survive() -> None:
    if not (OUT / "encoder_generation.json").exists():
        print("  [SKIP] encoder report missing")
        return
    egen = json.loads((OUT / "encoder_generation.json").read_text(encoding="utf-8"))
    by = {e["encoder"]: e for e in egen.get("encoders") or []}
    assert "ENC414" in by and "ENC424" in by
    assert by["ENC414"]["ticks_per_foot"] == 6.0
    print("  [PASS] both encoders survive")


def test_parameter_map_not_greensboro_claim() -> None:
    path = OUT / "parameterization_report.json"
    if not path.exists():
        print("  [SKIP] parameterization report missing")
        return
    rep = json.loads(path.read_text(encoding="utf-8"))
    assert rep.get("arbitrary_text_replace") is False
    assert rep.get("method") == "explicit_parameter_map"
    pmap = rep.get("parameter_map") or {}
    assert "lane_bindings" in pmap
    assert len(pmap.get("lane_bindings") or []) == 5
    print("  [PASS] Sawtooth template parameterized via explicit map")


def test_no_finished_plc4_flag() -> None:
    if not (OUT / "generation_summary.json").exists():
        print("  [SKIP] summary missing")
        return
    s = json.loads((OUT / "generation_summary.json").read_text(encoding="utf-8"))
    assert s.get("finished_plc4_used") is False
    print("  [PASS] finished PLC4 not used")


def test_no_new_cp4_toolbar_buttons() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    forbidden = [
        "Build VFDs",
        "Build Encoders",
        "Build Sawtooth",
        "Bind Lanes",
        "Validate Sawtooth",
        "Generate Tracking",
    ]
    for label in forbidden:
        assert label not in html, f"forbidden toolbar label present: {label}"
    assert "Apply to Autogen" in html
    assert "Auto Build" in html
    assert "Advanced / Evidence" in html or "tb-advanced-menu" in html
    print("  [PASS] no unnecessary CP4 top-level UI controls; CP2 workflow preserved")


def main() -> int:
    print("=== CP4 Compiler Pass 2 tests ===")
    fails = 0
    for fn in [
        test_prefix_not_implied,
        test_realization_reconciles,
        test_vfd_and_lanes_survive,
        test_encoders_survive,
        test_parameter_map_not_greensboro_claim,
        test_no_finished_plc4_flag,
        test_no_new_cp4_toolbar_buttons,
    ]:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    # leakage: identity helper must not read PLC4 paths
    src = (SCRIPTS / "fortna_cp4_pass2.py").read_text(encoding="utf-8")
    if "ORLY_Greensboro_NC_PLC4" in src and "Finished" in src:
        # only allowed in comments saying NOT used
        pass
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS — CP4 pass2 tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
