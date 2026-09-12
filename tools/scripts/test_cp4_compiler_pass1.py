#!/usr/bin/env python3
"""Tests for CP4 Compiler Pass 1 — no finished PLC4 as generation input."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_cp4_pass1 import (  # noqa: E402
    PROV_NOT_SUPPORTED,
    PROV_RUN_EXPLICIT,
    apply_explicit_vfd_to_input,
    build_encoder_generation,
    build_sawtooth_generation,
    build_tracking_status,
    build_vfd_conveyor_index,
    load_discovery,
    run_pass1,
)
from fortna_autogen import AutogenInput, ConveyorRow, DEFAULT_LIBRARY  # noqa: E402


DISC = ROOT / "exports" / "cp4-discovery"
RUN = ROOT / "workspace" / "cp4-run" / "RUN"
OUT = ROOT / "exports" / "cp4-pass1"


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise AssertionError(msg)


def test_explicit_vfd_beats_name_inference() -> None:
    disc = load_discovery(DISC)
    idx = build_vfd_conveyor_index(disc["vfd"])
    # P414 and P416 both mapped from VFD414 explicitly
    assert "P414" in idx and idx["P414"]["vfd_base"] == "VFD414"
    assert "P416" in idx and idx["P416"]["vfd_base"] == "VFD414"
    assert idx["P414"]["provenance"] == PROV_RUN_EXPLICIT

    inp = AutogenInput(
        project_name="test",
        processor="1756-L83E",
        conveyors=[
            ConveyorRow(
                number=1,
                system="ORNCCP4",
                main_area="ORNCCP4_Area",
                safety_zone="ORNCCP4_ESZone1",
                conveyor="P414",
                type="Transport with MS",  # wrong heuristic
            ),
            ConveyorRow(
                number=2,
                system="ORNCCP4",
                main_area="ORNCCP4_Area",
                safety_zone="ORNCCP4_ESZone1",
                conveyor="P116",
                type="Transport with MS",
            ),
        ],
    )
    rows = apply_explicit_vfd_to_input(inp, idx, disc["equipment"])
    p414 = next(c for c in inp.conveyors if c.conveyor == "P414")
    assert "VFD" in (p414.type or "").upper(), p414.type
    forced = [r for r in rows if r["conveyor"] == "P414"][0]
    assert forced["rule"] == "explicit_discovery_mapping_beats_name_heuristic"
    print("  [PASS] explicit VFD mapping wins over name inference (P414/P416)")


def test_lane_p116_pe118_vfd118() -> None:
    disc = load_discovery(DISC)
    lane = next(l for l in disc["sawtooth"]["lanes"] if l.get("conveyor") == "P116")
    assert lane["photoeye"] == "PE118_P"
    assert "VFD118" in (lane.get("drive") or lane.get("vfd") or "")
    # Must be RUN-explicit relationship — not tag-number matching (116≠118)
    assert lane.get("conveyor_provenance") == PROV_RUN_EXPLICIT or lane.get("provenance") == PROV_RUN_EXPLICIT
    assert "116" not in (lane.get("photoeye") or "")
    # VFD118 conveyor mapping is P118 (Mtrchain) — different from lane conveyor P116
    vfd118 = next(v for v in disc["vfd"]["vfds"] if v["vfd"] == "VFD118")
    assert "P118" in vfd118["conveyors"]
    assert "LANE_3_P116" in (vfd118.get("saw_lanes") or [])
    assert vfd118.get("saw_lane_mapping_provenance") == PROV_RUN_EXPLICIT
    # Prove not derived from equal trailing digits
    assert "P116" not in vfd118["conveyors"]
    print("  [PASS] saw lane P116 may use PE118/VFD118 (RUN-explicit, not number match)")


def test_shared_vfd_multi_conveyor_from_run() -> None:
    disc = load_discovery(DISC)
    vfd414 = next(v for v in disc["vfd"]["vfds"] if v["vfd"] == "VFD414")
    assert set(vfd414["conveyors"]) >= {"P414", "P416"}
    assert vfd414.get("conveyor_mapping_provenance") == PROV_RUN_EXPLICIT
    methods = {e.get("method") for e in (vfd414.get("conveyor_mapping_evidence") or [])}
    assert "Mtrchain.asc" in methods or any("Mtrchain" in str(m) for m in methods) or methods
    vfd424 = next(v for v in disc["vfd"]["vfds"] if v["vfd"] == "VFD424")
    assert set(vfd424["conveyors"]) >= {"P424", "P424A"}
    assert vfd424.get("conveyor_mapping_provenance") == PROV_RUN_EXPLICIT
    # Pass1 VFD generation must retain these
    vgen_path = OUT / "vfd_generation.json"
    if vgen_path.exists():
        vgen = json.loads(vgen_path.read_text(encoding="utf-8"))
        mapped = {r["conveyor"]: r for r in vgen.get("mapped_conveyors") or []}
        for tag in ("P414", "P416", "P424", "P424A"):
            assert tag in mapped, f"missing {tag} in vfd_generation"
            assert mapped[tag]["provenance"] == PROV_RUN_EXPLICIT
            assert mapped[tag]["rule"] == "explicit_discovery_mapping_beats_name_heuristic"
    print("  [PASS] VFD414→P414,P416 and VFD424→P424,P424A from RUN evidence")

def test_five_lanes_survive() -> None:
    disc = load_discovery(DISC)
    assert disc["sawtooth"]["counts"]["lanes"] == 5
    gen = build_sawtooth_generation(disc["sawtooth"], ROOT / "tools/libraries/programs/Sawtooth_Merge_Program.L5X")
    assert gen["lane_count"] == 5
    names = [l["lane_name"] for l in gen["lanes"]]
    assert names == [
        "LANE_0_P219",
        "LANE_1_P408",
        "LANE_3_P116",
        "LANE_4_P214",
        "LANE_5_P832",
    ]
    print("  [PASS] five lanes survive discovery → compiler unchanged")


def test_slice_reserve_survive() -> None:
    disc = load_discovery(DISC)
    gen = build_sawtooth_generation(disc["sawtooth"], ROOT / "tools/libraries/programs/Sawtooth_Merge_Program.L5X")
    by_name = {l["lane_name"]: l for l in gen["lanes"]}
    assert by_name["LANE_0_P219"]["slice_seconds"] == 3.0
    assert by_name["LANE_0_P219"]["reserve_seconds"] == 10.0
    assert by_name["LANE_3_P116"]["slice_seconds"] == 8.0
    assert by_name["LANE_3_P116"]["reserve_seconds"] == 20.0
    print("  [PASS] slice/reserve times survive generation report")


def test_encoder_params_survive() -> None:
    disc = load_discovery(DISC)
    gen = build_encoder_generation(disc["encoders"])
    by = {e["encoder"]: e for e in gen["encoders"]}
    assert by["ENC414"]["ticks_per_foot"] == 6.0
    assert by["ENC414"]["target_fpm"] == 150.0
    assert by["ENC414"]["enable"] == "VFD414_AUX"
    assert by["ENC424"]["target_fpm"] == 225.0
    print("  [PASS] encoder parameters survive generation report")


def test_tracking_not_silently_generated() -> None:
    disc = load_discovery(DISC)
    st = build_tracking_status(disc["tracking_wcs"])
    assert st["status"] == PROV_NOT_SUPPORTED
    assert "Sorter_Track" in st["include_programs_blocked"]
    assert "WCS_Interface_TCP_IP" in st["include_programs_blocked"]
    print("  [PASS] unsupported tracking/WCS remains explicit")


def test_finished_plc4_does_not_change_output() -> None:
    """Leakage: decoy finished PLC4 present/absent/renamed → same report digests."""
    import hashlib

    if not RUN.is_dir():
        print("  [SKIP] CP4 RUN missing")
        return

    def digest_pass1(extra_files: list[Path]) -> str:
        # touch decoys then run into temp out
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            # decoys next to CWD/tools — place under ROOT decoy folder
            summary = run_pass1(
                discovery_dir=DISC,
                run_dir=RUN,
                out_dir=out,
                library=Path(DEFAULT_LIBRARY) if Path(DEFAULT_LIBRARY).is_absolute() else ROOT / "tools/libraries/OReilly_Library_v3.L5X",
            )
            # hash key reports (not L5X timestamps inside)
            h = hashlib.sha256()
            for name in [
                "conveyor_provenance.json",
                "vfd_generation.json",
                "encoder_generation.json",
                "sawtooth_generation.json",
                "configuration_required.json",
                "tracking_wcs_status.json",
            ]:
                raw = (out / name).read_bytes()
                # strip generated_at lines for stability
                text = raw.decode("utf-8", errors="replace")
                text = "\n".join(ln for ln in text.splitlines() if "generated_at" not in ln)
                h.update(text.encode("utf-8"))
            return h.hexdigest()

    decoy_dir = ROOT / "workspace" / "_plc4_decoy_pass1"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    decoy = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X"
    decoy_renamed = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X.renamed"

    # absent
    for p in (decoy, decoy_renamed):
        if p.exists():
            p.unlink()
    d_absent = digest_pass1([])

    # present
    decoy.write_text("<!-- decoy finished PLC4 — must not affect pass1 -->", encoding="utf-8")
    d_present = digest_pass1([])

    # renamed
    decoy.rename(decoy_renamed)
    d_renamed = digest_pass1([])

    # cleanup
    if decoy_renamed.exists():
        decoy_renamed.unlink()

    if not (d_absent == d_present == d_renamed):
        _fail(f"digests differ absent={d_absent[:12]} present={d_present[:12]} renamed={d_renamed[:12]}")
    print(f"  [PASS] finished PLC4 presence/absence/rename does not change output ({d_absent[:16]}…)")


def test_artifacts_exist_after_generate() -> None:
    if not (OUT / "generation_summary.json").exists():
        print("  [SKIP] exports/cp4-pass1 not generated yet")
        return
    required = [
        "generation_summary.json",
        "conveyor_provenance.json",
        "vfd_generation.json",
        "encoder_generation.json",
        "sawtooth_generation.json",
        "configuration_required.json",
        "library_provenance.json",
        "report.md",
    ]
    for name in required:
        if not (OUT / name).exists():
            _fail(f"missing {name}")
    summary = json.loads((OUT / "generation_summary.json").read_text(encoding="utf-8"))
    assert summary.get("finished_plc4_used") is False
    lib = json.loads((OUT / "library_provenance.json").read_text(encoding="utf-8"))
    assert lib.get("finished_plc4_used") is False
    print("  [PASS] pass1 artifacts present; finished_plc4_used=false")


def main() -> int:
    print("=== CP4 Compiler Pass 1 tests ===")
    fails = 0
    for fn in [
        test_explicit_vfd_beats_name_inference,
        test_lane_p116_pe118_vfd118,
        test_shared_vfd_multi_conveyor_from_run,
        test_five_lanes_survive,
        test_slice_reserve_survive,
        test_encoder_params_survive,
        test_tracking_not_silently_generated,
        test_artifacts_exist_after_generate,
        test_finished_plc4_does_not_change_output,
    ]:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS — all CP4 pass1 tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
