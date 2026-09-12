#!/usr/bin/env python3
"""CP4 Sawtooth semantics compile — regenerate L5X with evidence-backed real logic.

Reuses fortna_cp4_sawtooth / fortna_sawtooth_param. Does not read finished PLC4.
Tracking/WCS remains GENERATION NOT YET SUPPORTED. Does not polish Transport.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import DEFAULT_LIBRARY  # noqa: E402
from fortna_cp4_pass1 import SAWTOOTH_TEMPLATE, load_discovery  # noqa: E402
from fortna_cp4_sawtooth import (  # noqa: E402
    content_digest_from_l5x,
    run_sawtooth_fidelity,
)
from fortna_sawtooth_param import inventory_pack_symbols  # noqa: E402
from fortna_sawtooth_semantics import (  # noqa: E402
    CLS_CAN,
    CLS_CFG,
    CLS_DOC,
    CLS_UNSUPPORTED,
    PROV_NOT_SUPPORTED,
    apply_semantic_renames,
    audit_placeholders,
    build_encoder_semantics,
    build_merge_signal_map,
    build_semantic_conv_routines,
    build_semantic_model,
    build_semantic_tags_xml,
    build_vfd_semantics,
    count_resolution_buckets,
    force_replace_routines,
    inject_semantic_tags,
    model_to_json,
    validate_generated_l5x,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_json_if(path: Path) -> Any | None:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"raw_path": str(path), "parse_error": True}
    return None


def _integrate_audit_sidecar(out_dir: Path) -> list[str]:
    """Consume parallel audit outputs under exports/cp4-semantics/ if present."""
    notes: list[str] = []
    for name in (
        "unresolved_symbol_audit.json",
        "unresolved_symbol_audit.md",
        "reserve_eye_analysis.md",
        "reserve_eye_analysis.json",
    ):
        p = out_dir / name
        if p.is_file():
            notes.append(f"Integrated sidecar: `{name}` ({p.stat().st_size} bytes)")
    return notes


def upgrade_l5x_with_semantics(
    l5x_path: Path,
    model,
    audit: dict[str, Any],
) -> dict[str, Any]:
    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    text, renames = apply_semantic_renames(text, model)
    tags = build_semantic_tags_xml(model)
    text, tag_mode = inject_semantic_tags(text, tags)
    routines = build_semantic_conv_routines(model, audit)
    text, routine_report = force_replace_routines(text, routines)
    l5x_path.write_text(text, encoding="utf-8")
    return {
        "renames": renames,
        "tag_inject": tag_mode,
        "tags_injected": tags.count("<Tag Name="),
        "routines": routine_report,
        "real_logic_rungs": sum(
            1
            for it in audit.get("items") or []
            if it.get("classification") == CLS_CAN and it.get("proposed_text")
        ),
    }


def build_genericity_fixture_model() -> dict[str, Any]:
    """Synthetic discovery-shaped sawtooth for genericity tests (no Greensboro ids)."""
    return {
        "sawtooth": {
            "merges": [
                {
                    "name": "SYN_MERGE_A",
                    "motor_io": "VFD501_AUX",
                    "reservation": "SYN_RESERVATION",
                    "lane_enable_delay_tm": "tmSynMerge_DLY",
                    "slice_seconds": 12.0,
                    "provenance": "RUN_EXPLICIT",
                    "source_file": "synthetic",
                }
            ],
            "lanes": [
                {
                    "name": "LANE_0_P701",
                    "conveyor": "P701",
                    "lane_index": 1,
                    "approach": "SYN_APP_0",
                    "collision": "SYN_COL_0",
                    "lane_input": "SYN_IN_0",
                    "photoeye": "PE701_P",
                    "drive": "VFD701_EN",
                    "slice_seconds": 4.0,
                    "reserve_seconds": 9.0,
                    "allowed_to_run": "Y",
                    "provenance": "RUN_EXPLICIT",
                },
                {
                    "name": "LANE_1_P702",
                    "conveyor": "P702",
                    "lane_index": 2,
                    "approach": "SYN_APP_1",
                    "collision": "SYN_COL_1",
                    "lane_input": "SYN_IN_1",
                    "photoeye": "PE702_P",
                    "drive": "VFD702_EN",
                    "slice_seconds": 5.0,
                    "reserve_seconds": 11.0,
                    "allowed_to_run": "Y",
                    "provenance": "RUN_EXPLICIT",
                },
            ],
        },
        "encoders": {
            "encoders": [
                {
                    "encoder": "ENC501",
                    "io": "ENC501",
                    "ticks_per_foot": 8.0,
                    "target_fpm": 180.0,
                    "enable": "VFD501_AUX",
                    "jamzone": "SYN MERGE",
                    "provenance": "RUN_EXPLICIT",
                    "associations": [
                        {
                            "type": "encoder_to_saw_merge_via_motor_io",
                            "to": "SYN_MERGE_A",
                            "via": "VFD501_AUX",
                            "provenance": "RUN_EXPLICIT",
                        }
                    ],
                },
                {
                    "encoder": "ENC599",
                    "io": "ENC599",
                    "ticks_per_foot": 8.0,
                    "target_fpm": 200.0,
                    "enable": "VFD599_AUX",
                    "jamzone": "CITY COUNTER",
                    "provenance": "RUN_EXPLICIT",
                    "associations": [],
                },
            ]
        },
        "vfd": {"devices": [], "vfds": []},
    }


def run_semantics_compile(
    *,
    discovery_dir: Path,
    run_dir: Path,
    out_dir: Path,
    library: Path,
    prior_l5x: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = out_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    discovery = load_discovery(discovery_dir)
    pack_syms = inventory_pack_symbols(
        SAWTOOTH_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    ) if SAWTOOTH_TEMPLATE.is_file() else []
    pack_set = set(pack_syms)

    model = build_semantic_model(discovery, run_dir=run_dir, pack_symbols=pack_set)
    semantic_json = model_to_json(model)
    merge_map = build_merge_signal_map(model)
    enc_sem = build_encoder_semantics(model)
    vfd_sem = build_vfd_semantics(discovery, model)

    _write_json(out_dir / "semantic_model.json", semantic_json)
    _write_json(out_dir / "merge_signal_map.json", merge_map)
    _write_json(out_dir / "encoder_semantics.json", enc_sem)
    _write_json(out_dir / "vfd_semantics.json", vfd_sem)

    # Prefer prior parameterized Sawtooth program (clean Conv_* NOP fills) for audit baseline
    prior = prior_l5x
    if prior is None:
        cand2 = (
            ROOT
            / "exports"
            / "cp4-sawtooth-pass"
            / "generated"
            / "Sawtooth_Merge_Parameterized.L5X"
        )
        prior = cand2 if cand2.is_file() else None
    if prior is None:
        cand = (
            ROOT
            / "exports"
            / "cp4-sawtooth-pass"
            / "generated"
            / "OReillyGreensboro_ORNCCP4.L5X"
        )
        prior = cand if cand.is_file() else None

    audit_before = (
        audit_placeholders(prior, model)
        if prior and prior.is_file()
        else {
            "generated_at": _ts(),
            "source_l5x": None,
            "counts": {"total": 0, "was_nop": 0, CLS_CAN: 0, CLS_CFG: 0, CLS_DOC: 0, CLS_UNSUPPORTED: 0},
            "items": [],
            "note": "No prior L5X found for placeholder audit",
        }
    )
    _write_json(out_dir / "placeholder_audit.json", audit_before)

    # Regenerate via fidelity path into semantics out
    fidelity_summary = run_sawtooth_fidelity(
        discovery_dir=discovery_dir,
        run_dir=run_dir,
        out_dir=out_dir,
        library=library,
    )
    l5x_path = Path(fidelity_summary.get("l5x") or "")
    prog_path = Path(fidelity_summary.get("parameterized_program") or "")

    # Re-audit the fidelity (still NOP) output then upgrade
    if l5x_path.is_file():
        audit_fidelity = audit_placeholders(l5x_path, model)
        upgrade = upgrade_l5x_with_semantics(l5x_path, model, audit_fidelity)
        audit_after = audit_placeholders(l5x_path, model)
        # After upgrade, was_nop should drop for CAN items — recompute was_nop from text
        text_after = l5x_path.read_text(encoding="utf-8", errors="replace")
        nop_after = len(re.findall(r"NOP\(\);", text_after))
        # Count NOP only inside Conv_* routines
        conv_nop = 0
        for rname in ("Conv_PE", "Conv_Enc", "Conv_Fast"):
            m = re.search(
                rf'<Routine Name="{rname}" Type="RLL"[^>]*>(.*?)</Routine>',
                text_after,
                flags=re.S,
            )
            if m:
                conv_nop += m.group(1).count("NOP();")
        audit_after["counts"]["was_nop"] = conv_nop
        audit_after["counts"]["nop_global_approx"] = nop_after
        audit_after["upgrade"] = upgrade
        _write_json(out_dir / "placeholder_audit_after.json", audit_after)
    else:
        audit_fidelity = audit_before
        audit_after = audit_before
        upgrade = {}

    if prog_path.is_file():
        audit_prog = audit_placeholders(prog_path, model)
        upgrade_l5x_with_semantics(prog_path, model, audit_prog)

    validation = validate_generated_l5x(
        l5x_path if l5x_path.is_file() else out_dir / "generated" / "missing.L5X",
        model,
        expect_real_logic=True,
    )
    _write_json(out_dir / "validation_report.json", validation)

    # Genericity synthetic check (model-only, no Greensboro leak)
    syn_disc = build_genericity_fixture_model()
    syn_model = build_semantic_model(syn_disc, run_dir=Path("__no_run__"), pack_symbols=set())
    syn_payload = {
        "merge": syn_model.name,
        "motor_io": syn_model.motor_io.symbol if syn_model.motor_io else None,
        "lanes": [
            {
                "name": ln.name,
                "conveyor": ln.conveyor,
                "photoeye": ln.photoeye.symbol if ln.photoeye else None,
                "drive": ln.drive.symbol if ln.drive else None,
                "slice_seconds": ln.slice_seconds,
                "reserve_seconds": ln.reserve_seconds,
            }
            for ln in syn_model.lanes
        ],
        "encoders": [
            {
                "encoder": e.encoder,
                "enable": e.enable,
                "role": e.role,
                "jamzone": e.jamzone,
            }
            for e in syn_model.encoders
        ],
    }
    forbidden = ["414", "219", "408", "116", "214", "832", "Greensboro", "ORNCCP4", "PE118", "VFD118"]
    syn_blob = json.dumps(syn_payload)
    leaks = [tok for tok in forbidden if tok in syn_blob]
    genericity = {
        "generated_at": _ts(),
        "fixture": "synthetic_two_lane_merge",
        "lane_count": len(syn_model.lanes),
        "encoders": [e.encoder for e in syn_model.encoders],
        "payload": syn_payload,
        "forbidden_tokens_checked": forbidden,
        "leaks_found": leaks,
        "ok": len(leaks) == 0,
        "note": "Synthetic fixture must not emit Greensboro/ORNCCP4/site digits unless in fixture input",
    }
    _write_json(out_dir / "genericity_test.json", genericity)

    buckets = count_resolution_buckets(merge_map, enc_sem, vfd_sem, audit_before, audit_after)
    # Fold fidelity configuration_required inventory into headline counts
    cfg_path = out_dir / "configuration_required.json"
    if cfg_path.is_file():
        try:
            cfg_doc = json.loads(cfg_path.read_text(encoding="utf-8"))
            buckets["CONFIGURATION_REQUIRED"] = max(
                int(buckets.get("CONFIGURATION_REQUIRED") or 0),
                int((cfg_doc.get("counts") or {}).get("configuration_required") or 0),
            )
            buckets["UNSUPPORTED"] = max(
                int(buckets.get("UNSUPPORTED") or 0),
                int((cfg_doc.get("counts") or {}).get("generation_not_yet_supported") or 0),
            )
        except Exception:
            pass
    sidecar_notes = _integrate_audit_sidecar(out_dir)
    unresolved = _read_json_if(out_dir / "unresolved_symbol_audit.json")

    content_digest = None
    if l5x_path.is_file():
        content_digest = content_digest_from_l5x(l5x_path)

    summary = {
        "generated_at": _ts(),
        "pass": "cp4-sawtooth-semantics",
        "finished_plc4_used": False,
        "l5x": str(l5x_path) if l5x_path else None,
        "parameterized_program": str(prog_path) if prog_path else None,
        "content_digest": content_digest,
        "lane_count": len(model.lanes),
        "validation_ok": validation.get("ok"),
        "resolution_counts": buckets,
        "placeholder_before_nop": buckets.get("placeholder_before_nop"),
        "placeholder_after_nop": buckets.get("placeholder_after_nop"),
        "upgrade": upgrade,
        "genericity_ok": genericity.get("ok"),
        "sidecar_notes": sidecar_notes,
        "tracking_wcs": PROV_NOT_SUPPORTED,
        "ok": bool(validation.get("ok")) and bool(genericity.get("ok")),
    }
    _write_json(out_dir / "semantics_compile_summary.json", summary)

    # Human report
    unresolved_section = ""
    if isinstance(unresolved, dict):
        hist = unresolved.get("resolution_histogram") or unresolved.get("counts") or {}
        sample = []
        for sym in (unresolved.get("symbols") or [])[:12]:
            if isinstance(sym, dict):
                sample.append(
                    f"- `{sym.get('symbol') or sym.get('name')}`: "
                    f"{sym.get('resolution') or sym.get('classification') or sym.get('status')}"
                )
        unresolved_section = (
            "\n## Parallel unresolved symbol audit\n\n"
            f"- File: `unresolved_symbol_audit.json` / `.md`\n"
            f"- Symbol rows: **{len(unresolved.get('symbols') or [])}**\n"
            f"- Histogram: `{json.dumps(hist)}`\n"
            f"- Reserve-eye summary keys: "
            f"`{list((unresolved.get('reserve_eye_summary') or {}).keys())}`\n"
            + ("\n### Sample\n" + "\n".join(sample) + "\n" if sample else "")
        )
    reserve_eye = out_dir / "reserve_eye_analysis.md"
    reserve_section = ""
    if reserve_eye.is_file():
        # Keep a short pointer; full analysis remains in the sidecar file
        reserve_section = (
            "\n## Reserve / full-eye analysis (sidecar)\n\n"
            "See `reserve_eye_analysis.md` / `.json`. Semantics compile applies "
            "`EZPE127_F`→`EZPE217_F` as RUN_DERIVED when Fullline+ReserveTM agree; "
            "keeps LANE_4 F1/F2 paired roles without blind rename.\n"
        )

    biggest_uncertainty = (
        "LANE_0 full-eye gold slot EZPE127_F→EZPE217_F is RUN_DERIVED (Fullline-backed) "
        "but pack AOI wiring for upstream-P217 vs lane-P219 still needs engineer confirm; "
        "LANE_4 paired F1/F2 reserve-clear vs lane-full-eye dual roles; "
        "full Fast_Conv AOI rewrite remains unsupported without area/downstream config."
    )

    report = f"""# CP4 Sawtooth Semantics Compile

Generated: {summary['generated_at']}
Finished PLC4 used: **NO**
Pass: `cp4-sawtooth-semantics`

## Inputs
- Discovery: `{discovery_dir}` (immutable)
- RUN: `{run_dir}`
- Generic libraries under `tools/libraries/`
- Prior fidelity L5X for placeholder audit: `{prior}`

## Outputs
- Controller L5X: `{l5x_path}`
- Parameterized program: `{prog_path}`
- Semantic model: `semantic_model.json`
- Maps: `merge_signal_map.json`, `encoder_semantics.json`, `vfd_semantics.json`
- Placeholder audit: `placeholder_audit.json` / `placeholder_audit_after.json`
- Validation: `validation_report.json`
- Content digest: `{content_digest}`

## Resolution counts
| Bucket | Count |
|--------|------:|
| Resolved RUN (incl. RUN_DERIVED) | {buckets.get('resolved_RUN')} |
| Resolved library / documentation | {buckets.get('resolved_library')} |
| CONFIGURATION REQUIRED | {buckets.get('CONFIGURATION_REQUIRED')} |
| UNKNOWN | {buckets.get('UNKNOWN')} |
| UNSUPPORTED | {buckets.get('UNSUPPORTED')} |

## Placeholder NOP before → after
- Before (prior generation Conv_* NOP rungs): **{buckets.get('placeholder_before_nop')}**
- After (Conv_* NOP remaining): **{buckets.get('placeholder_after_nop')}**
- CAN_GENERATE_REAL_LOGIC applied: **{buckets.get('can_generate_after_applied')}**

## Semantic decisions
- Lanes: **{len(model.lanes)}** — indices preserved; `LANE_3_P116` → `PE118_P` / `VFD118_EN`
- ENC414: SAWTOOTH_COLLECTOR (real enable/reset logic)
- ENC424: CITY COUNTER — **DOCUMENTATION_ONLY** (not forced into Sawtooth)
- Conv_PE / Conv_Fast: real XIO/XIC → `SawSem_*` where RUN PE evidence exists
- Full Fast_Conv AOI rewrite: **UNSUPPORTED** (area/downstream CONFIG REQUIRED)
- Tracking/WCS: **GENERATION NOT YET SUPPORTED**

## Validation
- ok: **{validation.get('ok')}** ({validation.get('passed')}/{validation.get('passed',0)+(validation.get('failed') or 0)} checks)

## Genericity
- Synthetic fixture ok: **{genericity.get('ok')}** leaks={genericity.get('leaks_found')}

## Sidecars
{chr(10).join('- ' + n for n in sidecar_notes) if sidecar_notes else '- (none yet)'}
{reserve_section}{unresolved_section}
## Biggest remaining uncertainty
{biggest_uncertainty}

## UI
No Transport polish. No commit/push from this pass.
"""
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 Sawtooth semantics compile")
    ap.add_argument("--discovery", default="exports/cp4-discovery")
    ap.add_argument("--run-dir", default="workspace/cp4-run/RUN")
    ap.add_argument("--out", default="exports/cp4-semantics")
    ap.add_argument("--library", default=str(DEFAULT_LIBRARY))
    ap.add_argument(
        "--prior-l5x",
        default="",
        help="Prior fidelity L5X for placeholder audit (optional)",
    )
    args = ap.parse_args(argv)

    def _p(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (ROOT / path).resolve()

    prior = _p(args.prior_l5x) if args.prior_l5x else None
    summary = run_semantics_compile(
        discovery_dir=_p(args.discovery),
        run_dir=_p(args.run_dir),
        out_dir=_p(args.out),
        library=_p(args.library),
        prior_l5x=prior,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
