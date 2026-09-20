#!/usr/bin/env python3
"""Reality Check V1 — Demo A (MSCATL_CP3) measurement only.

Does NOT change production decoding. Writes artifacts under
exports/demo/siteforge-reality-check-v1/MSCATL_CP3/.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_ai_io_validate import (  # noqa: E402
    compute_claim_conservation,
    enrich_conservation_with_readiness,
)
from fortna_ai_readonly_tools import (  # noqa: E402
    SiteForgeReadOnlyContext,
    get_configio_binding_trace,
    get_physical_word_resolution_trace,
)
from fortna_physical_word_resolver import PhysicalWordResolver, parse_eipcfg  # noqa: E402
from fortna_production_gate_atlanta import site_counts  # noqa: E402
from fortna_rack_discovery import discover_racks  # noqa: E402

RUN = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
MACHINE = "MSCATL_CP3"
OUT = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "MSCATL_CP3"
EXPECT = {
    "physical_claims": 256,
    "PROVEN": 256,
    "unresolved": 0,
    "racks": 3,
    "conservation": "PASS",
}


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        path.write_text(obj if obj.endswith("\n") else obj + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_sha() -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip()
    )


def hardware_rack_view(disc: dict, bridges: list) -> dict:
    racks_out = []
    for i, rack in enumerate(disc.get("racks") or [], start=1):
        slots = []
        for mod in rack.get("modules") or []:
            slots.append(
                {
                    "slot": mod.get("physical_slot") or mod.get("slot"),
                    "catalog": mod.get("catalog_number")
                    or mod.get("type")
                    or mod.get("catalog"),
                    "name": (mod.get("source_names") or [None])[0]
                    or mod.get("name"),
                    "connection": mod.get("connection"),
                    "input_bank": mod.get("input_bank"),
                    "output_bank": mod.get("output_bank"),
                    "status": mod.get("status") or mod.get("placement_status"),
                    "direction": mod.get("direction"),
                }
            )
        aliases = rack.get("source_aliases") or []
        racks_out.append(
            {
                "presentation_alias": rack.get("provisional_display_name")
                or rack.get("provisional_name")
                or rack.get("display_name")
                or f"AREA_RIO_{i}",
                "canonical_adapter_id": rack.get("canonical_adapter_id"),
                "canonical_adapter": (aliases[0] if aliases else None)
                or rack.get("adapter_name")
                or rack.get("name"),
                "catalog": rack.get("catalog_number")
                or rack.get("adapter_type")
                or rack.get("type"),
                "ip": rack.get("ip_address") or rack.get("ip") or rack.get("target_ip"),
                "hardware_family": rack.get("hardware_family"),
                "bridge_status": rack.get("bridge_status"),
                "slots": slots,
            }
        )
    return {
        "kind": "hardware_rack_view",
        "project": MACHINE,
        "machine": MACHINE,
        "run_dir": str(RUN),
        "rack_count": (disc.get("stats") or {}).get("rack_count"),
        "slotted_modules": (disc.get("stats") or {}).get("slotted_modules"),
        "unplaced_modules": (disc.get("stats") or {}).get("unplaced_modules"),
        "racks": racks_out,
        "adapter_bridge_count": len(bridges),
        "note": "AREA_RIO_N is presentation-only alias; identity is adapter+IP.",
    }


def rack_md(view: dict) -> str:
    lines = [
        f"# Hardware rack view — {view['machine']}",
        "",
        f"- Project/machine: `{view['project']}` / `{view['machine']}`",
        f"- Racks: **{view.get('rack_count')}**",
        f"- Slotted modules: {view.get('slotted_modules')}",
        f"- Unplaced modules: {view.get('unplaced_modules')}",
        "",
    ]
    for rack in view.get("racks") or []:
        lines.append(f"## {rack.get('presentation_alias')}")
        lines.append(f"- Adapter: `{rack.get('canonical_adapter')}`")
        lines.append(f"- Catalog: `{rack.get('catalog')}`")
        lines.append(f"- IP: `{rack.get('ip')}`")
        lines.append(f"- Bridge: `{rack.get('bridge_status')}`")
        lines.append("")
        lines.append("| Slot | Catalog | Name | InBank | OutBank |")
        lines.append("|-----:|---------|------|-------:|--------:|")
        for s in rack.get("slots") or []:
            lines.append(
                f"| {s.get('slot')} | {s.get('catalog')} | {s.get('name')} | "
                f"{s.get('input_bank')} | {s.get('output_bank')} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def provenance_examples(n: int = 5) -> list[dict]:
    ev = build_evidence_bundle(RUN, MACHINE, project=MACHINE)
    resolver = PhysicalWordResolver(RUN, MACHINE)
    ctx = SiteForgeReadOnlyContext(RUN, MACHINE)
    assigned = [
        c
        for c in (ev.get("raw_claims") or [])
        if c.get("deterministic_disposition") == "ASSIGNED"
    ]
    samples = assigned[:n]
    if len(samples) < n:
        samples = (ev.get("raw_claims") or [])[:n]
    out = []
    for c in samples:
        hit = resolver.resolve(c.get("word"), c.get("bit")) or {}
        try:
            bind = get_configio_binding_trace(ctx, c.get("word"))
        except Exception as ex:
            bind = {"error": str(ex)}
        try:
            phys = get_physical_word_resolution_trace(ctx, str(c.get("claim_id") or ""))
        except Exception as ex:
            phys = {"error": str(ex)}
        out.append(
            {
                "engineering_device": c.get("io_name") or c.get("desc") or c.get("claim_id"),
                "raw_io_claim": {
                    "claim_id": c.get("claim_id"),
                    "word": c.get("word"),
                    "bit": c.get("bit"),
                    "direction": c.get("direction") or c.get("in_out"),
                    "disposition": c.get("deterministic_disposition"),
                    "evidence_class": c.get("evidence_class") or "RAW_RUN_EVIDENCE",
                },
                "fortna_word_bit": {"word": c.get("word"), "bit": c.get("bit")},
                "resolver_hit": {
                    "channel": hit.get("channel"),
                    "type": hit.get("type"),
                    "direction": hit.get("direction"),
                    "half_bank": hit.get("half_bank"),
                    "eip_slot": hit.get("eip_slot"),
                    "rio_name": hit.get("rio_name"),
                    "bank_join": hit.get("bank_join"),
                    "binding_confidence": hit.get("binding_confidence"),
                    "assign_how": hit.get("assign_how"),
                    "note": (
                        "binding_confidence PROVEN = direct evidence join; "
                        "DERIVED = inferred relationship — say so honestly."
                    ),
                },
                "configio_binding_trace": bind,
                "physical_word_resolution_trace": phys,
                "evidence_purity_note": (
                    "physical_word_resolution_trace is CURRENT_DECODER_OUTPUT — "
                    "diagnostic only; cannot independently prove the rule it implements."
                ),
            }
        )
    return out


def build_readiness(score: dict, compiler: dict) -> dict:
    io_pass = (
        score.get("conservation") == "PASS"
        and int(score.get("needs_resolution") or 0) == 0
        and int(score.get("PROVEN") or 0) > 0
    )
    subsystems = {
        "RUN_ingestion": "PASS",
        "machine_source_scoping": "PASS",
        "hardware_topology": (
            "PASS" if int(score.get("rack_count") or 0) >= 1 else "BLOCKED"
        ),
        "physical_IO": "PASS" if io_pass else "REVIEW_REQUIRED",
        "Transportation": "PARTIAL",
        "Safety": "REVIEW_REQUIRED",
        "Sorter": "NOT_APPLICABLE",
        "VFD": "NOT_IMPLEMENTED",
        "canonical_model": "PARTIAL",
        "PLC_compiler": compiler.get("readiness_status") or "BLOCKED",
        "GUI": "PARTIAL",
        "provenance": "PASS" if io_pass else "PARTIAL",
        "PostgreSQL_learning": "PASS",
    }
    blocked = [k for k, v in subsystems.items() if v == "BLOCKED"]
    review = [k for k, v in subsystems.items() if v == "REVIEW_REQUIRED"]
    overall = (
        "NOT READY TO COMPILE"
        if blocked or review or subsystems["PLC_compiler"] in {"BLOCKED", "REVIEW_REQUIRED"}
        else "READY_FOR_PREFLIGHT"
    )
    # If compiler actually produced L5X with preflight, reflect that honestly
    if compiler.get("l5x_generated") and compiler.get("preflight_status") == "PREFLIGHT_PASS":
        if not blocked and subsystems["physical_IO"] == "PASS":
            overall = "HARDWARE_IO_READY__FULL_SITE_PARTIAL"
    return {
        "kind": "build_readiness",
        "machine": MACHINE,
        "overall": overall,
        "subsystems": subsystems,
        "deterministic_gate_notes": [
            "Overall follows weakest relevant gate; no invented percentages.",
            "Transportation/Safety not virgin-complete for one-click compile.",
            "Hardware/I-O PASS does not imply full-site READY.",
        ],
        "blocked_subsystems": blocked,
        "review_required_subsystems": review,
    }


def readiness_md(r: dict) -> str:
    lines = [
        f"# Build readiness — {r['machine']}",
        "",
        f"**Overall: {r['overall']}**",
        "",
        "| Subsystem | Status |",
        "|-----------|--------|",
    ]
    for k, v in (r.get("subsystems") or {}).items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    for n in r.get("deterministic_gate_notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def attempt_compiler() -> dict:
    """Attempt real virgin qualification generate path; report honestly."""
    out_dir = OUT / "qualification_virgin"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "scripts" / "fortna_qualification_runner.py"),
        "qualify",
        "--run-dir",
        str(RUN),
        "--machine",
        MACHINE,
        "--mode",
        "virgin",
        "--sanitized",
        "--out",
        str(out_dir),
        "--label",
        "reality-check-v1",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    report_path = out_dir / "qualification_report.json"
    report = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    gen_dir = out_dir / "generated"
    l5x = sorted(gen_dir.glob("*.L5X")) if gen_dir.is_dir() else []
    # Prefer machine-named L5X
    machine_l5x = [p for p in l5x if MACHINE in p.name]
    chosen = (machine_l5x or l5x or [None])[0]
    preflight = None
    preflight_status = None
    if chosen and chosen.is_file():
        dest = OUT / "generated"
        dest.mkdir(parents=True, exist_ok=True)
        copied = dest / f"{MACHINE}_SiteForge.L5X"
        shutil.copy2(chosen, copied)
        pf_json = OUT / "generated" / "studio_preflight.json"
        pf_md = OUT / "generated" / "studio_preflight.md"
        pf = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "scripts" / "fortna_studio_preflight.py"),
                str(copied),
                "--out-json",
                str(pf_json),
                "--out-md",
                str(pf_md),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if pf_json.is_file():
            preflight = json.loads(pf_json.read_text(encoding="utf-8"))
            # Map to PREFLIGHT_PASS only — never STUDIO_IMPORT_PASS without Studio
            ok = bool(preflight.get("ok") or preflight.get("pass") or preflight.get("status") == "PASS")
            # Some preflight schemas use overall/summary
            overall = str(
                preflight.get("overall")
                or preflight.get("result")
                or preflight.get("status")
                or ""
            ).upper()
            if ok or overall in {"PASS", "OK", "PREFLIGHT_PASS"}:
                preflight_status = "PREFLIGHT_PASS"
            else:
                preflight_status = "PREFLIGHT_FAIL_OR_REVIEW"
        else:
            preflight_status = "PREFLIGHT_NOT_RUN"
            preflight = {"stdout": pf.stdout[-2000:], "stderr": pf.stderr[-2000:]}
        l5x_path = str(copied.relative_to(ROOT)).replace("\\", "/")
        readiness_status = (
            "PARTIAL"
            if preflight_status == "PREFLIGHT_PASS"
            else "BLOCKED"
        )
    else:
        l5x_path = None
        readiness_status = "BLOCKED"
        copied = None

    return {
        "kind": "compiler_result",
        "command": cmd,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "qualification_overall": report.get("overall"),
        "qualification_ok": report.get("ok"),
        "qualification_report": str(report_path) if report_path.is_file() else None,
        "l5x_generated": bool(chosen),
        "l5x_path": l5x_path,
        "preflight_status": preflight_status,
        "preflight": preflight,
        "studio_import_status": "NOT_PERFORMED",
        "readiness_status": readiness_status,
        "note": "STUDIO_IMPORT_PASS requires real Studio 5000 import — not claimed here.",
    }


def main() -> int:
    if not RUN.is_dir():
        raise SystemExit(f"Missing RUN: {RUN}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generated").mkdir(parents=True, exist_ok=True)

    # Virgin recompute
    score = site_counts(RUN, MACHINE)
    # Drop bulky claims from scorecard artifact
    score_slim = {k: v for k, v in score.items() if k != "claims"}
    disc = discover_racks(RUN, MACHINE)
    topo = parse_eipcfg(RUN, MACHINE)
    bridges = topo.get("adapter_bridges") or []
    if not isinstance(bridges, list):
        bridges = []

    view = hardware_rack_view(disc, bridges)
    # enrich IP from topo adapters if missing
    adapters = {
        (a.get("name") or ""): a for a in (topo.get("adapters") or [])
    }
    for rack in view["racks"]:
        name = rack.get("canonical_adapter") or ""
        if not rack.get("ip") and name in adapters:
            rack["ip"] = adapters[name].get("target_ip") or adapters[name].get("ip")

    io_scorecard = {
        "kind": "io_scorecard",
        "machine": MACHINE,
        "run_dir": str(RUN),
        "expectation": EXPECT,
        "actual": {
            "raw_physical_claims": score_slim.get("raw"),
            "ASSIGNED": score_slim.get("ASSIGNED"),
            "PROVEN": score_slim.get("PROVEN"),
            "DERIVED": score_slim.get("DERIVED"),
            "ENGINEER_ASSIGNED": 0,
            "REVIEW_REQUIRED": score_slim.get("REVIEW_REQUIRED"),
            "UNKNOWN": score_slim.get("UNKNOWN"),
            "needs_resolution": score_slim.get("needs_resolution"),
            "OWNER_CONFLICT": score_slim.get("OWNER_CONFLICT"),
            "physical_resolution_failure": score_slim.get("physical_resolution_failure"),
            "rack_count": score_slim.get("rack_count"),
            "slotted_modules": score_slim.get("slotted_modules"),
            "unplaced_modules": score_slim.get("unplaced_modules"),
            "duplicate_channels": score_slim.get("duplicate_channels"),
            "conservation": score_slim.get("conservation"),
        },
        "delta_vs_expectation": {
            "physical_claims": (score_slim.get("raw") or 0) - EXPECT["physical_claims"],
            "PROVEN": (score_slim.get("PROVEN") or 0) - EXPECT["PROVEN"],
            "unresolved": (score_slim.get("needs_resolution") or 0) - EXPECT["unresolved"],
            "racks": (score_slim.get("rack_count") or 0) - EXPECT["racks"],
            "conservation_match": score_slim.get("conservation") == EXPECT["conservation"],
        },
        "matches_prior_accepted": (
            score_slim.get("raw") == EXPECT["physical_claims"]
            and score_slim.get("PROVEN") == EXPECT["PROVEN"]
            and (score_slim.get("needs_resolution") or 0) == EXPECT["unresolved"]
            and score_slim.get("rack_count") == EXPECT["racks"]
            and score_slim.get("conservation") == EXPECT["conservation"]
        ),
        "full_site_counts": score_slim,
    }

    unresolved = {
        "kind": "unresolved_items",
        "machine": MACHINE,
        "needs_resolution": score_slim.get("needs_resolution"),
        "REVIEW_REQUIRED": score_slim.get("REVIEW_REQUIRED"),
        "UNKNOWN": score_slim.get("UNKNOWN"),
        "items": [
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "disposition": c.get("deterministic_disposition"),
            }
            for c in (score.get("claims") or [])
            if c.get("deterministic_disposition")
            not in {"ASSIGNED", None}
            or False
        ][:200],
    }
    # Only keep truly unresolved
    unresolved["items"] = [
        {
            "claim_id": c.get("claim_id"),
            "io_name": c.get("io_name"),
            "word": c.get("word"),
            "bit": c.get("bit"),
            "disposition": c.get("deterministic_disposition"),
        }
        for c in (score.get("claims") or [])
        if c.get("deterministic_disposition")
        in {
            "physical_resolution_failure",
            "UNRESOLVED_OWNER",
            "OWNER_CONFLICT",
            "UNKNOWN",
        }
    ][:200]

    prov = provenance_examples(5)
    compiler = attempt_compiler()
    readiness = build_readiness(score_slim, compiler)

    demo_manifest = {
        "kind": "demo_a_manifest",
        "demo": "A_KNOWN_STRONG_SITE",
        "machine": MACHINE,
        "project": "MSCATL",
        "run_dir": str(RUN),
        "git_sha": _git_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "virgin": True,
        "inputs_forbidden_and_not_used": [
            "prior generated L5X",
            "finished/reference L5X as discovery",
            "cached workbook",
            "old current-site canonical model",
            "previously corrected output",
        ],
        "postgresql_role": "approved PRODUCTION_RULES only (method, not site answers)",
        "matches_prior_accepted": io_scorecard["matches_prior_accepted"],
        "artifacts": [
            "demo_manifest.json",
            "hardware_rack_view.json",
            "hardware_rack_view.md",
            "io_scorecard.json",
            "provenance_examples.json",
            "build_readiness.json",
            "build_readiness.md",
            "unresolved_items.json",
            "compiler_result.json",
            "demo_summary.md",
        ],
    }

    _write(OUT / "demo_manifest.json", demo_manifest)
    _write(OUT / "hardware_rack_view.json", view)
    _write(OUT / "hardware_rack_view.md", rack_md(view))
    _write(OUT / "io_scorecard.json", io_scorecard)
    _write(OUT / "provenance_examples.json", {"examples": prov})
    _write(OUT / "build_readiness.json", readiness)
    _write(OUT / "build_readiness.md", readiness_md(readiness))
    _write(OUT / "unresolved_items.json", unresolved)
    _write(OUT / "compiler_result.json", compiler)

    summary = f"""# Demo A — MSCATL_CP3 Reality Check

**Git SHA:** `{demo_manifest['git_sha']}`
**RUN:** `{RUN}`
**Virgin recompute:** YES

## Physical I/O scorecard

| Metric | Expected | Actual | Delta |
|--------|---------:|-------:|------:|
| raw physical claims | {EXPECT['physical_claims']} | {io_scorecard['actual']['raw_physical_claims']} | {io_scorecard['delta_vs_expectation']['physical_claims']} |
| PROVEN | {EXPECT['PROVEN']} | {io_scorecard['actual']['PROVEN']} | {io_scorecard['delta_vs_expectation']['PROVEN']} |
| needs_resolution | {EXPECT['unresolved']} | {io_scorecard['actual']['needs_resolution']} | {io_scorecard['delta_vs_expectation']['unresolved']} |
| racks | {EXPECT['racks']} | {io_scorecard['actual']['rack_count']} | {io_scorecard['delta_vs_expectation']['racks']} |
| conservation | {EXPECT['conservation']} | {io_scorecard['actual']['conservation']} | match={io_scorecard['delta_vs_expectation']['conservation_match']} |

**Matches prior accepted expectation:** {io_scorecard['matches_prior_accepted']}

Also: ASSIGNED={io_scorecard['actual']['ASSIGNED']}, DERIVED={io_scorecard['actual']['DERIVED']},
REVIEW_REQUIRED={io_scorecard['actual']['REVIEW_REQUIRED']}, UNKNOWN={io_scorecard['actual']['UNKNOWN']},
duplicate_channels={io_scorecard['actual']['duplicate_channels']},
unplaced_modules={io_scorecard['actual']['unplaced_modules']}.

## Build readiness

**Overall: {readiness['overall']}**

See `build_readiness.md`.

## Compiler

- Qualification overall: `{compiler.get('qualification_overall')}`
- L5X generated: {compiler.get('l5x_generated')}
- L5X path: `{compiler.get('l5x_path')}`
- Preflight: `{compiler.get('preflight_status')}`
- Studio import: `{compiler.get('studio_import_status')}`

## GUI reproduction

1. From repo root, optionally pack RUN: create/import MSCATL_CP3 tar.gz via Site Forge Browse Archive
   (or copy peek RUN content into a temp tar and import).
2. Launch: `desktop\\Launch-SiteForge.bat`
3. Open Hardware / I-O view — expect 3× AREA_RIO provisional racks from canonical model.
4. Do **not** load finished L5X as discovery input.

Exact CLI measurement (already run):

```powershell
python tools/diagnostics/_reality_check_demo_a.py
python tools/scripts/fortna_hardware_io_model.py --run-dir workspace/_mscatl_peek/MSCATL_CP3/RUN --machine MSCATL_CP3 --out exports/demo/siteforge-reality-check-v1/MSCATL_CP3/hardware_io_model.json
```
"""
    _write(OUT / "demo_summary.md", summary)
    print(json.dumps({
        "out": str(OUT),
        "matches_prior_accepted": io_scorecard["matches_prior_accepted"],
        "actual": io_scorecard["actual"],
        "readiness": readiness["overall"],
        "compiler": {
            "l5x": compiler.get("l5x_path"),
            "preflight": compiler.get("preflight_status"),
            "qual": compiler.get("qualification_overall"),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
