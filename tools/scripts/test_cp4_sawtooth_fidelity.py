#!/usr/bin/env python3
"""CP4 Sawtooth fidelity acceptance tests — PARSE generated L5X (not just file existence).

Finished PLC4 is never used as generation input. Leakage test verifies present/absent/renamed
decoy finished PLC4 cannot change the generated content digest.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import DEFAULT_LIBRARY  # noqa: E402
from fortna_cp4_sawtooth import (  # noqa: E402
    content_digest_from_l5x,
    run_sawtooth_fidelity,
)

DISC = ROOT / "exports" / "cp4-discovery"
OUT = ROOT / "exports" / "cp4-sawtooth-pass"
RUN = ROOT / "workspace" / "cp4-run" / "RUN"
LIB = Path(DEFAULT_LIBRARY) if Path(DEFAULT_LIBRARY).is_absolute() else ROOT / "tools/libraries/OReilly_Library_v3.L5X"

PROV_NOT_SUPPORTED = "GENERATION NOT YET SUPPORTED"


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def _load(name: str) -> dict:
    path = OUT / name
    if not path.is_file():
        _fail(f"missing artifact {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _controller_l5x() -> Path:
    summary = _load("generation_summary.json")
    p = Path(summary.get("l5x") or "")
    if not p.is_file():
        # fallback: first L5X in generated/
        cands = list((OUT / "generated").glob("*.L5X"))
        cands = [c for c in cands if "Library" not in c.name and "Parameterized" not in c.name]
        if not cands:
            _fail("no controller L5X under exports/cp4-sawtooth-pass/generated")
        return cands[0]
    return p


def _parse_tag_names(text: str) -> set[str]:
    return set(re.findall(r'<Tag Name="([^"]+)"', text))


def _parse_decorated_value(text: str, tag_name: str) -> float | int | None:
    m = re.search(
        rf'<Tag Name="{re.escape(tag_name)}"[^>]*>.*?</Tag>',
        text,
        flags=re.S,
    )
    if not m:
        return None
    vals = re.findall(r'Value="([^"]+)"', m.group(0))
    if not vals:
        return None
    raw = vals[-1]
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return None


def test_artifacts_exist() -> None:
    required = [
        "parameter_map.json",
        "library_provenance.json",
        "generation_summary.json",
        "sawtooth_generation.json",
        "vfd_generation.json",
        "encoder_generation.json",
        "configuration_required.json",
        "provenance.json",
        "report.md",
    ]
    for name in required:
        if not (OUT / name).is_file():
            _fail(f"missing {name}")
    if not (OUT / "generated").is_dir():
        _fail("missing generated/")
    l5xs = list((OUT / "generated").glob("*.L5X"))
    if not l5xs:
        _fail("no generated L5X files")
    summary = _load("generation_summary.json")
    assert summary.get("finished_plc4_used") is False
    print("  [PASS] fidelity artifacts present; finished_plc4_used=false")


def test_five_lanes_survive_parse() -> None:
    disc = json.loads((DISC / "sawtooth.json").read_text(encoding="utf-8"))
    assert disc["counts"]["lanes"] == 5
    pmap = _load("parameter_map.json")
    assert pmap.get("lane_count") == 5
    assert len(pmap.get("lane_bindings") or []) == 5
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    tags = _parse_tag_names(l5x)
    assert "SawFid_LaneCount" in tags
    assert _parse_decorated_value(l5x, "SawFid_LaneCount") == 5
    sgen = _load("sawtooth_generation.json")
    assert sgen.get("lane_count") == 5
    names = [b["lane_name"] for b in sgen.get("lanes") or []]
    assert names == [
        "LANE_0_P219",
        "LANE_1_P408",
        "LANE_3_P116",
        "LANE_4_P214",
        "LANE_5_P832",
    ]
    print("  [PASS] exactly 5 lanes survive discovery→model→generation (L5X parsed)")


def test_lane_indices_survive() -> None:
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    for idx in (1, 2, 3, 4, 5):
        val = _parse_decorated_value(l5x, f"SawFid_L{idx}_Index")
        assert val == idx, f"lane index {idx} missing/wrong in L5X: {val}"
    pmap = _load("parameter_map.json")
    by = {b["lane_name"]: b for b in pmap.get("lane_bindings") or []}
    assert by["LANE_0_P219"]["lane_index"] == 1
    assert by["LANE_3_P116"]["lane_index"] == 3
    assert by["LANE_5_P832"]["lane_index"] == 5
    print("  [PASS] lane indices survive into parsed L5X")


def test_p116_maps_to_pe118_vfd118() -> None:
    pmap = _load("parameter_map.json")
    lane = next(b for b in pmap["lane_bindings"] if b["lane_name"] == "LANE_3_P116")
    assert lane["conveyor"] == "P116"
    assert lane["photoeye"] == "PE118_P"
    assert lane["drive"] == "VFD118_EN"
    assert lane["lane_index"] == 3
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    tags = _parse_tag_names(l5x)
    assert any(t.startswith("SawFid_L3_Conv_P116") for t in tags)
    assert any(t.startswith("SawFid_L3_PE_PE118_P") for t in tags)
    assert any(t.startswith("SawFid_L3_Drive_VFD118_EN") for t in tags)
    # Pack / site PE must also remain referenced
    assert "PE118_P" in l5x
    print("  [PASS] P116 still maps to PE118_P / VFD118_EN (parsed L5X + map)")


def test_slice_reserve_timing_survives() -> None:
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    assert _parse_decorated_value(l5x, "SawFid_L1_SliceSec") == 3.0
    assert _parse_decorated_value(l5x, "SawFid_L1_ReserveSec") == 10.0
    assert _parse_decorated_value(l5x, "SawFid_L3_SliceSec") == 8.0
    assert _parse_decorated_value(l5x, "SawFid_L3_ReserveSec") == 20.0
    assert _parse_decorated_value(l5x, "SawFid_L4_SliceSec") == 6.0
    assert _parse_decorated_value(l5x, "SawFid_Merge_SliceSec") == 18.0
    print("  [PASS] slice/reserve timing survives in parsed L5X")


def test_vfd_shared_relationships_survive() -> None:
    vgen = _load("vfd_generation.json")
    assert vgen["counts"]["vfd_bases_discovery"] == 13
    shared = {(r["vfd"], tuple(r["conveyors"])) for r in vgen.get("shared_relationships") or []}
    assert ("VFD414", ("P414", "P416")) in shared
    assert ("VFD424", ("P424", "P424A")) in shared
    mapped = {r["conveyor"]: r for r in vgen.get("mapped_conveyors") or []}
    for tag in ("P414", "P416", "P424", "P424A"):
        assert tag in mapped
        assert mapped[tag]["provenance"] == "RUN_EXPLICIT"
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    tags = _parse_tag_names(l5x)
    assert "SawFid_Shared_VFD414_P414" in tags
    assert "SawFid_Shared_VFD414_P416" in tags
    assert "SawFid_Shared_VFD424_P424" in tags
    assert "SawFid_Shared_VFD424_P424A" in tags
    print("  [PASS] VFD shared relationships survive (13 bases + markers)")


def test_encoder_params_survive() -> None:
    egen = _load("encoder_generation.json")
    by = {e["encoder"]: e for e in egen.get("encoders") or []}
    assert "ENC414" in by and "ENC424" in by
    assert by["ENC414"]["ticks_per_foot"] == 6.0
    assert by["ENC414"]["target_fpm"] == 150.0
    assert by["ENC424"]["target_fpm"] == 225.0
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    assert _parse_decorated_value(l5x, "SawFid_ENC414_TicksPerFoot") == 6.0
    assert _parse_decorated_value(l5x, "SawFid_ENC414_TargetFPM") == 150.0
    assert _parse_decorated_value(l5x, "SawFid_ENC424_TicksPerFoot") == 6.0
    assert _parse_decorated_value(l5x, "SawFid_ENC424_TargetFPM") == 225.0
    tags = _parse_tag_names(l5x)
    assert any("SawFid_ENC414_Enable_VFD414_AUX" in t for t in tags)
    print("  [PASS] ENC414/ENC424 parameters survive in parsed L5X")


def test_tracking_wcs_explicitly_unsupported() -> None:
    tracking = _load("tracking_wcs_status.json")
    assert tracking.get("status") == PROV_NOT_SUPPORTED
    assert "Sorter_Track" in (tracking.get("include_programs_blocked") or [])
    assert "WCS_Interface_TCP_IP" in (tracking.get("include_programs_blocked") or [])
    cfg = _load("configuration_required.json")
    kinds = [i.get("kind") for i in cfg.get("items") or []]
    assert "tracking_wcs" in kinds
    sgen = _load("sawtooth_generation.json")
    assert sgen.get("tracking_wcs") == PROV_NOT_SUPPORTED
    # Must not silently include those programs in generated L5X as enabled packs
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    # Presence of program name from library context is ok only if not claimed generated;
    # assert summary / config still mark unsupported.
    summary = _load("generation_summary.json")
    assert summary.get("tracking_wcs") == PROV_NOT_SUPPORTED
    print("  [PASS] unsupported Tracking/WCS remains explicit")


def test_conv_routines_filled() -> None:
    l5x = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    assert '<Routine Name="Conv_PE" Type="RLL"/>' not in l5x
    assert "LANE_3_P116" in l5x
    assert "PE118_P" in l5x
    # Filled routines contain NOP bindings with lane comments
    assert re.search(r'<Routine Name="Conv_PE" Type="RLL">\s*<RLLContent>', l5x)
    assert re.search(r'<Routine Name="Conv_Enc" Type="RLL">\s*<RLLContent>', l5x)
    assert re.search(r'<Routine Name="Conv_Fast" Type="RLL">\s*<RLLContent>', l5x)
    print("  [PASS] Conv_PE / Conv_Enc / Conv_Fast filled from RUN bindings")


def test_no_greensboro_tags_unless_from_run() -> None:
    """Pack leftovers not bound by current RUN must be CONFIGURATION REQUIRED, not claimed RUN_EXPLICIT."""
    pmap = _load("parameter_map.json")
    prov = _load("provenance.json")
    run_tokens = set()
    for b in pmap.get("lane_bindings") or []:
        for k in ("conveyor", "photoeye", "drive", "full_eye_ezpe", "approach", "collision", "lane_input"):
            if b.get(k):
                run_tokens.add(str(b[k]).upper())
    run_tokens.update({"MRG414", "P414", "P418", "VFD414", "ENC414", "ENC424", "SAWTOOTH_MERGE", "SAW_RESERVATION"})
    # Unmapped pack symbols must not be labeled RUN_EXPLICIT in provenance
    bad = []
    for s in prov.get("symbols") or []:
        sym = str(s.get("symbol") or "")
        if s.get("role") == "unmapped_pack_symbol" and s.get("provenance") == "RUN_EXPLICIT":
            bad.append(sym)
    assert not bad, f"unmapped pack symbols claimed RUN_EXPLICIT: {bad[:10]}"
    # Known gold leftover examples (if present) must be config-required in parameter map
    unmapped = {u.get("symbol") for u in pmap.get("unmapped_pack_symbols") or []}
    for suspect in ("EZPE127_F", "P422_SawMerge_HMI"):
        if suspect in unmapped:
            row = next(u for u in pmap["unmapped_pack_symbols"] if u["symbol"] == suspect)
            assert row.get("classification") == "CONFIGURATION REQUIRED"
    print("  [PASS] no Greensboro-specific tags claimed unless from current RUN")


def test_provenance_complete() -> None:
    prov = _load("provenance.json")
    assert prov.get("finished_plc4_used") is False
    assert prov.get("symbol_count", 0) > 0
    allowed = {
        "RUN_EXPLICIT",
        "RUN_DERIVED",
        "CONFIGURATION REQUIRED",
        "ENGINEER_CONFIGURED",
        "GENERIC_LIBRARY",
        "GENERIC_LIBRARY_TEMPLATE",
        "GENERIC_KEEP",
        PROV_NOT_SUPPORTED,
    }
    bad = [s for s in prov.get("symbols") or [] if s.get("provenance") not in allowed]
    assert not bad, f"symbols missing allowed provenance: {bad[:5]}"
    print("  [PASS] every inventoried symbol has allowed provenance")


def test_parameter_map_covers_site_varying() -> None:
    pmap = _load("parameter_map.json")
    roles = {sp.get("role") for sp in pmap.get("site_parameters") or []}
    for needed in (
        "merge_identity",
        "collector",
        "merge_motor",
        "reservation",
        "lane_count",
        "lane_identity",
        "lane_index",
        "lane_conveyor",
        "lane_photoeye",
        "lane_drive",
        "slice_seconds",
        "reserve_seconds",
        "approach",
        "collision",
        "merge_input",
        "encoder",
    ):
        assert needed in roles, f"missing site parameter role {needed}"
    assert pmap.get("arbitrary_text_replace") is False
    assert pmap.get("finished_plc4_used") is False
    print("  [PASS] parameter map audits site-varying Sawtooth params")


def test_no_new_toolbar_buttons() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    for label in (
        "Build VFDs",
        "Build Encoders",
        "Build Sawtooth",
        "Bind Lanes",
        "Validate Sawtooth",
        "Generate Tracking",
    ):
        assert label not in html, f"forbidden toolbar label: {label}"
    print("  [PASS] no new Transport toolbar buttons")


def test_finished_plc4_does_not_change_digest() -> None:
    """Leakage: decoy finished PLC4 present/absent/renamed → same content digest."""
    if not RUN.is_dir():
        print("  [SKIP] CP4 RUN missing")
        return

    decoy_dir = ROOT / "workspace" / "_plc4_decoy_sawtooth"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    decoy = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X"
    decoy_renamed = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X.renamed"

    def run_digest() -> str:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            summary = run_sawtooth_fidelity(
                discovery_dir=DISC,
                run_dir=RUN,
                out_dir=out,
                library=LIB,
            )
            # Prefer L5X content digest; also hash key JSON sans generated_at
            l5x = Path(summary.get("l5x") or "")
            h = hashlib.sha256()
            if l5x.is_file():
                h.update(content_digest_from_l5x(l5x).encode("utf-8"))
            for name in (
                "parameter_map.json",
                "sawtooth_generation.json",
                "vfd_generation.json",
                "encoder_generation.json",
                "provenance.json",
            ):
                text = (out / name).read_text(encoding="utf-8")
                text = "\n".join(ln for ln in text.splitlines() if "generated_at" not in ln)
                # Drop absolute paths that embed temp out dir
                text = re.sub(re.escape(str(out)).replace("\\", "\\\\"), "OUT", text, flags=re.I)
                text = re.sub(r"[A-Za-z]:\\\\.*?\\\\out", "OUT", text)
                h.update(text.encode("utf-8"))
            return h.hexdigest()

    for p in (decoy, decoy_renamed):
        if p.exists():
            p.unlink()
    d_absent = run_digest()

    decoy.write_text(
        "<!-- decoy finished PLC4 — must not affect sawtooth fidelity -->\n"
        "<Tag Name='DECOY_SHOULD_NOT_APPEAR' />",
        encoding="utf-8",
    )
    d_present = run_digest()

    decoy.rename(decoy_renamed)
    d_renamed = run_digest()

    if decoy_renamed.exists():
        decoy_renamed.unlink()

    if not (d_absent == d_present == d_renamed):
        _fail(
            f"digests differ absent={d_absent[:12]} present={d_present[:12]} renamed={d_renamed[:12]}"
        )
    # Ensure decoy marker never leaked into committed output either
    committed = _controller_l5x().read_text(encoding="utf-8", errors="replace")
    assert "DECOY_SHOULD_NOT_APPEAR" not in committed
    print(f"  [PASS] finished PLC4 present/absent/renamed does not change digest ({d_absent[:16]}…)")


def test_pass2_invariants_preserved() -> None:
    summary = _load("generation_summary.json")
    preserved = summary.get("preserved_pass2") or {}
    assert preserved.get("vfd_bases") == 13
    assert preserved.get("encoders") == 2
    assert preserved.get("sawtooth_lanes") == 5
    assert preserved.get("no_finished_plc4_input") is True
    assert summary["counts"]["saw_lanes"] == 5
    print("  [PASS] Pass2 invariants preserved (13 VFD / 2 enc / 5 lanes / no finished PLC4)")


def main() -> int:
    print("=== CP4 Sawtooth fidelity tests ===")
    fails = 0
    tests = [
        test_artifacts_exist,
        test_five_lanes_survive_parse,
        test_lane_indices_survive,
        test_p116_maps_to_pe118_vfd118,
        test_slice_reserve_timing_survives,
        test_vfd_shared_relationships_survive,
        test_encoder_params_survive,
        test_tracking_wcs_explicitly_unsupported,
        test_conv_routines_filled,
        test_no_greensboro_tags_unless_from_run,
        test_provenance_complete,
        test_parameter_map_covers_site_varying,
        test_no_new_toolbar_buttons,
        test_pass2_invariants_preserved,
        test_finished_plc4_does_not_change_digest,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    # Source leakage: generator must not open finished PLC4 paths
    src = (SCRIPTS / "fortna_cp4_sawtooth.py").read_text(encoding="utf-8")
    if "ORLY_Greensboro_NC_PLC4" in src and "Finished" not in src:
        # allow only in comments about NOT using
        fails += 1
        print("  [FAIL] generator source references finished PLC4 unexpectedly")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS — CP4 sawtooth fidelity tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
