#!/usr/bin/env python3
"""CP4 Sawtooth semantics tests — scenario transitions, genericity, leakage.

Does not emulate full Logix. Finished PLC4 is never a generation input.
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


import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import DEFAULT_LIBRARY  # noqa: E402
from fortna_cp4_pass1 import load_discovery  # noqa: E402
from fortna_cp4_semantics_compile import (  # noqa: E402
    build_genericity_fixture_model,
    run_semantics_compile,
)
from fortna_cp4_sawtooth import content_digest_from_l5x  # noqa: E402
from fortna_sawtooth_param import inventory_pack_symbols  # noqa: E402
from fortna_cp4_pass1 import SAWTOOTH_TEMPLATE  # noqa: E402
from fortna_sawtooth_semantics import (  # noqa: E402
    CLS_CAN,
    CLS_DOC,
    STATE_CLEAR,
    STATE_DISABLED,
    STATE_OCCUPIED,
    STATE_REQUEST,
    STATE_RESERVED,
    STATE_RELEASING,
    STATE_SLICING,
    build_semantic_model,
    encoder_advance,
    encoder_reset,
    lane_clear,
    lane_release,
    lane_request,
    lane_set_occupied,
    lane_start_slice,
    lane_try_reserve,
)

DISC = ROOT / "exports" / "cp4-discovery"
OUT = ROOT / "exports" / "cp4-semantics"
RUN = ROOT / "workspace" / "cp4-run" / "RUN"
LIB = Path(DEFAULT_LIBRARY) if Path(DEFAULT_LIBRARY).is_absolute() else ROOT / "tools/libraries/OReilly_Library_v3.L5X"


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def _load(name: str) -> dict:
    path = OUT / name
    if not path.is_file():
        _fail(f"missing artifact {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _model():
    discovery = load_discovery(DISC)
    pack = set()
    if SAWTOOTH_TEMPLATE.is_file():
        pack = set(
            inventory_pack_symbols(
                SAWTOOTH_TEMPLATE.read_text(encoding="utf-8", errors="replace")
            )
        )
    return build_semantic_model(discovery, run_dir=RUN, pack_symbols=pack)


def test_artifacts_exist() -> None:
    required = [
        "semantic_model.json",
        "merge_signal_map.json",
        "encoder_semantics.json",
        "vfd_semantics.json",
        "placeholder_audit.json",
        "validation_report.json",
        "genericity_test.json",
        "report.md",
    ]
    for name in required:
        if not (OUT / name).is_file():
            _fail(f"missing {name}")
    assert (OUT / "generated").is_dir()
    print("  [PASS] semantics artifacts present")


def test_scenario_happy_path() -> None:
    model = _model()
    model.merge_available = True
    lane = model.lane_by_name("LANE_3_P116")
    assert lane is not None
    assert lane.photoeye and lane.photoeye.symbol == "PE118_P"
    assert lane.drive and lane.drive.symbol == "VFD118_EN"

    lane_set_occupied(lane, True)
    assert lane.state == STATE_OCCUPIED
    assert lane_request(lane)
    assert lane.state == STATE_REQUEST
    assert lane_try_reserve(lane, model)
    assert lane.state == STATE_RESERVED
    assert model.merge_available is False
    assert lane_start_slice(lane)
    assert lane.state == STATE_SLICING
    assert lane_release(lane, model)
    assert lane.state == STATE_RELEASING
    assert model.merge_available is True
    assert lane_clear(lane)
    assert lane.state == STATE_CLEAR
    print("  [PASS] scenario occupied→request→reserve→slice→release→clear")


def test_scenario_disabled_and_merge_unavailable() -> None:
    model = _model()
    lane = model.lanes[0]
    lane.allowed_to_run = False
    lane_set_occupied(lane, True)
    assert lane.state == STATE_DISABLED
    assert lane_request(lane) is False

    lane2 = model.lanes[1]
    lane2.allowed_to_run = True
    lane2.state = STATE_CLEAR
    lane_set_occupied(lane2, True)
    lane_request(lane2)
    model.merge_available = False
    assert lane_try_reserve(lane2, model) is False
    assert lane2.state == STATE_REQUEST
    print("  [PASS] disabled + merge unavailable scenarios")


def test_scenario_encoder_advance_reset() -> None:
    model = _model()
    enc414 = model.encoder_by_name("ENC414")
    enc424 = model.encoder_by_name("ENC424")
    assert enc414 and enc414.sawtooth_associated
    assert enc424 and enc424.role == "CITY_COUNTER" and not enc424.sawtooth_associated
    assert encoder_advance(enc414, 3) is True
    assert enc414.pulses == 3
    assert encoder_reset(enc414) is True
    assert enc414.pulses == 0
    assert encoder_advance(enc424, 5) is False
    assert enc424.pulses == 0
    print("  [PASS] encoder advance/reset (ENC424 blocked as CITY COUNTER)")


def test_encoder_semantics_city_counter() -> None:
    enc = _load("encoder_semantics.json")
    by = {e["encoder"]: e for e in enc.get("encoders") or []}
    assert by["ENC414"]["sawtooth_associated"] is True
    assert by["ENC414"]["generation_policy"] == CLS_CAN
    assert by["ENC424"]["role"] == "CITY_COUNTER"
    assert by["ENC424"]["generation_policy"] == CLS_DOC
    print("  [PASS] encoder semantics ENC424 documentation-only")


def test_real_logic_in_l5x() -> None:
    summary = _load("semantics_compile_summary.json")
    l5x = Path(summary.get("l5x") or "")
    assert l5x.is_file(), "controller L5X missing"
    text = l5x.read_text(encoding="utf-8", errors="replace")
    assert "XIO(PE118_P.I.PE_Clear)OTE(SawSem_L3_Occupied)" in text
    assert "XIC(VFD414_AUX)OTE(SawSem_ENC414_Enable)" in text
    assert "SawSem_L3_Occupied" in text
    # ENC424 must remain NOP / doc in Conv_Enc
    m = re.search(r'<Routine Name="Conv_Enc" Type="RLL">(.*?)</Routine>', text, flags=re.S)
    assert m, "Conv_Enc missing"
    enc_body = m.group(1)
    assert "ENC424" in enc_body
    assert "CITY COUNTER" in enc_body or "CITY" in enc_body
    print("  [PASS] real logic present for PE118 / ENC414; ENC424 not forced")


def test_validation_report() -> None:
    rep = _load("validation_report.json")
    assert rep.get("ok") is True, f"validation failed: {[c for c in rep.get('checks') if not c.get('ok')]}"
    print("  [PASS] structural validation_report ok")


def test_genericity_synthetic_fixture() -> None:
    g = _load("genericity_test.json")
    assert g.get("ok") is True, f"leaks={g.get('leaks_found')}"
    syn = build_genericity_fixture_model()
    model = build_semantic_model(syn, run_dir=RUN, pack_symbols=set())
    payload = {
        "lanes": [ln.name for ln in model.lanes],
        "encoders": [e.encoder for e in model.encoders],
        "merge": model.name,
        "motor": model.motor_io.symbol if model.motor_io else None,
    }
    blob = json.dumps(payload)
    for tok in ("414", "219", "408", "116", "214", "832", "Greensboro", "ORNCCP4"):
        assert tok not in blob, f"leak {tok} in synthetic model {blob}"
    assert model.lanes[0].photoeye and model.lanes[0].photoeye.symbol == "PE701_P"
    print("  [PASS] genericity synthetic fixture has no Greensboro leak")


def test_answer_sheet_leakage_digest() -> None:
    if not RUN.is_dir():
        print("  [SKIP] CP4 RUN missing")
        return

    decoy_dir = ROOT / "workspace" / "_plc4_decoy_semantics"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    decoy = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X"
    decoy_renamed = decoy_dir / "ORLY_Greensboro_NC_PLC4_Finished.L5X.renamed"

    def run_digest() -> str:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            summary = run_semantics_compile(
                discovery_dir=DISC,
                run_dir=RUN,
                out_dir=out,
                library=LIB,
            )
            h = hashlib.sha256()
            l5x = Path(summary.get("l5x") or "")
            if l5x.is_file():
                h.update(content_digest_from_l5x(l5x).encode("utf-8"))
            for name in (
                "semantic_model.json",
                "merge_signal_map.json",
                "encoder_semantics.json",
                "vfd_semantics.json",
            ):
                text = (out / name).read_text(encoding="utf-8")
                text = "\n".join(ln for ln in text.splitlines() if "generated_at" not in ln)
                text = re.sub(re.escape(str(out)).replace("\\", "\\\\"), "OUT", text, flags=re.I)
                h.update(text.encode("utf-8"))
            return h.hexdigest()

    for p in (decoy, decoy_renamed):
        if p.exists():
            p.unlink()
    d_absent = run_digest()
    decoy.write_text(
        "<!-- decoy finished PLC4 — must not affect semantics -->\n"
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
    committed = Path(_load("semantics_compile_summary.json").get("l5x") or "")
    if committed.is_file():
        assert "DECOY_SHOULD_NOT_APPEAR" not in committed.read_text(encoding="utf-8", errors="replace")
    print(f"  [PASS] finished PLC4 present/absent/renamed digest stable ({d_absent[:16]}…)")


def test_placeholder_reduced() -> None:
    before = _load("placeholder_audit.json")
    after_path = OUT / "placeholder_audit_after.json"
    if not after_path.is_file():
        _fail("missing placeholder_audit_after.json")
    after = json.loads(after_path.read_text(encoding="utf-8"))
    b = before.get("counts") or {}
    a = after.get("counts") or {}
    assert b.get("was_nop", 0) > a.get("was_nop", 0), f"NOP not reduced before={b} after={a}"
    assert a.get(CLS_CAN, 0) >= 5
    print(
        f"  [PASS] placeholder NOP {b.get('was_nop')} → {a.get('was_nop')}; "
        f"CAN={a.get(CLS_CAN)}"
    )


def main() -> int:
    print("=== CP4 Sawtooth semantics tests ===")
    fails = 0
    tests = [
        test_artifacts_exist,
        test_scenario_happy_path,
        test_scenario_disabled_and_merge_unavailable,
        test_scenario_encoder_advance_reset,
        test_encoder_semantics_city_counter,
        test_real_logic_in_l5x,
        test_validation_report,
        test_genericity_synthetic_fixture,
        test_placeholder_reduced,
        test_answer_sheet_leakage_digest,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS — CP4 sawtooth semantics tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
