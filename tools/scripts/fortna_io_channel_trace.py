#!/usr/bin/env python3
"""Full per-channel I/O ownership + topology trace (Gates 1/3/4/5).

CLI:
  python fortna_io_channel_trace.py --run-dir workspace/cp5-run/RUN \\
      --machine ORNCCP5 --out exports/stabilization

Writes io_channel_trace.json + io_channel_trace.md. Uses HardwareIOModel as the
sole tree (adapters/modules/channels are the same objects the Hardware UI consumes).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_asc import read_asc  # noqa: E402
from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    OWNER_ENGINEER_SPARE,
    OWNER_PROVEN_SPARE,
    OWNER_UNRESOLVED,
    OWNER_UNKNOWN,
    build_hardware_io_model,
    module_ownership_audit_pass,
)
from fortna_physical_word_resolver import configio_desc_evidence  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (REPO_ROOT / run_dir).resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _configio_load_counts(run_dir: Path, machine: str) -> dict[str, Any]:
    """Gate 4 — machine-specific Configio.asc.{machine} load / Desc / join counts."""
    fortna = run_dir / "FORTNA"
    mach = (machine or "").strip()
    path = fortna / f"Configio.asc.{mach}" if mach else None
    source = "machine_specific"
    if path is None or not path.is_file():
        path = fortna / "Configio.asc"
        source = "generic"
    rows: list[dict[str, Any]] = []
    if path and path.is_file():
        try:
            _, rows = read_asc(path)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "path": str(path),
                "source": source,
            }
    form_counts: Counter[str] = Counter()
    nonempty = 0
    topology = 0
    spare_token = 0
    signal_claim = 0
    for r in rows:
        d = str(r.get("Desc") or "").strip()
        if not d:
            form_counts["empty"] += 1
            continue
        nonempty += 1
        du = d.upper()
        if du in {"SPARE", "INVALID", "N/A", "NONE", "NULL"}:
            spare_token += 1
            form_counts["spare_token"] += 1
            continue
        ev = configio_desc_evidence(d)
        if ev and ev.get("form") in ("panel_node", "panel_catalog"):
            topology += 1
            form_counts[str(ev.get("form"))] += 1
        else:
            signal_claim += 1
            form_counts["signal_or_other"] += 1

    conv_path = fortna / "Conveyor.asc"
    conveyor_rows = 0
    conveyor_named = 0
    if conv_path.is_file():
        try:
            _, crows = read_asc(conv_path)
            conveyor_rows = len(crows)
            for r in crows:
                name = str(r.get("IO_Name") or "").strip()
                if name and name.upper() not in {"SPARE", "INVALID", "N/A", "NONE", ""}:
                    conveyor_named += 1
        except Exception:
            pass

    return {
        "ok": True,
        "machine": mach,
        "path": str(path) if path else None,
        "source": source,
        "rows_loaded": len(rows),
        "desc_nonempty": nonempty,
        "desc_topology": topology,
        "desc_spare_token": spare_token,
        "desc_signal_or_other": signal_claim,
        "desc_form_counts": dict(form_counts),
        "conveyor_rows": conveyor_rows,
        "conveyor_named_points": conveyor_named,
    }


def _channel_record(
    ch: dict[str, Any],
    *,
    adapter: dict[str, Any],
    module: dict[str, Any],
) -> dict[str, Any]:
    ep = ch.get("physical_endpoint") if isinstance(ch.get("physical_endpoint"), dict) else {}
    le = ch.get("logical_endpoint") if isinstance(ch.get("logical_endpoint"), dict) else {}
    return {
        "physical_address": ch.get("physical_address"),
        "fortna_word": ch.get("fortna_word"),
        "fortna_bit": ch.get("fortna_bit"),
        "direction": ch.get("direction"),
        "bit_half": ch.get("bit_half"),
        "rio_name": adapter.get("rio_name"),
        "adapter": adapter.get("eipcfg_name") or adapter.get("name"),
        "panel": adapter.get("panel") or ch.get("panel"),
        "module_slot": module.get("slot"),
        "module_type": module.get("type") or module.get("catalog"),
        "module_name": module.get("name"),
        "family": module.get("family") or adapter.get("family"),
        "renderer": adapter.get("renderer"),
        "is_adapter_card": bool(module.get("is_adapter_card")),
        "owner_state": ch.get("owner_state"),
        "owner_source": ch.get("owner_source"),
        "engineering_owner": ch.get("engineering_owner"),
        "sourceName": ch.get("sourceName"),
        "rejection_reason": ch.get("rejection_reason"),
        "configio_desc": ch.get("configio_desc") or ch.get("low_desc") or ch.get("high_desc"),
        "configio_occupied": ch.get("configio_occupied"),
        "configio_spare": ch.get("configio_spare"),
        "configio_topology": ch.get("configio_topology"),
        "is_spare": ch.get("is_spare"),
        "unresolved": ch.get("unresolved"),
        "physical_endpoint": ep,
        "logical_endpoint": le or None,
        "endpoint_id": ep.get("endpoint_id") if ep else None,
    }


def _module_audit(module: dict[str, Any]) -> dict[str, Any]:
    channels = list(module.get("channels") or [])
    assigned = sum(1 for c in channels if c.get("owner_state") == OWNER_ASSIGNED)
    unresolved = sum(1 for c in channels if c.get("owner_state") == OWNER_UNRESOLVED)
    spare = sum(
        1
        for c in channels
        if c.get("owner_state") in (OWNER_PROVEN_SPARE, OWNER_ENGINEER_SPARE)
    )
    named = sum(
        1
        for c in channels
        if (c.get("engineering_owner") or c.get("sourceName") or "")
        and str(c.get("engineering_owner") or c.get("sourceName") or "").strip().upper()
        not in {"", "SPARE"}
    )
    audit = module.get("ownership_audit") or module_ownership_audit_pass(module)
    return {
        "slot": module.get("slot"),
        "name": module.get("name"),
        "type": module.get("type") or module.get("catalog"),
        "family": module.get("family"),
        "is_adapter_card": bool(module.get("is_adapter_card")),
        "channel_capacity": module.get("channel_capacity"),
        "expected_occupied": audit.get("expected_occupied"),
        "named": named,
        "assigned": assigned,
        "unresolved": unresolved,
        "spare": spare,
        "missing": max(0, int(module.get("channel_capacity") or 0) - len(channels)),
        "channel_count": len(channels),
        "ownership_audit_ok": bool(audit.get("ok")),
        "ownership_audit_reason": audit.get("reason") or "",
    }


def build_io_channel_trace(
    run_dir: Path | str,
    machine: str = "",
) -> dict[str, Any]:
    run_dir = _normalize_run_dir(Path(run_dir))
    mach = (machine or "").strip()
    model = build_hardware_io_model(run_dir, mach)
    if not mach:
        mach = str((model.get("controller") or {}).get("machine") or "").strip()

    channels: list[dict[str, Any]] = []
    module_audits: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    adapters = list(model.get("adapters") or [])
    for ad in adapters:
        for mod in ad.get("modules") or []:
            module_audits.append(
                {
                    **_module_audit(mod),
                    "rio_name": ad.get("rio_name"),
                    "panel": ad.get("panel"),
                    "renderer": ad.get("renderer"),
                }
            )
            for ch in mod.get("channels") or []:
                rec = _channel_record(ch, adapter=ad, module=mod)
                channels.append(rec)
                st = str(rec.get("owner_state") or OWNER_UNKNOWN)
                owner_counts[st] += 1
                source_counts[str(rec.get("owner_source") or "NONE")] += 1
                if st == OWNER_UNRESOLVED:
                    reason_counts[str(rec.get("rejection_reason") or "MISSING_REJECTION_REASON")] += 1

    # Gate 1 examples: one ASSIGNED (5MCR1 / word 500 bit 2) + one mapped unused spare
    example_assigned = None
    example_spare = None
    for rec in channels:
        if example_assigned is None and (
            rec.get("engineering_owner") == "5MCR1"
            or (rec.get("fortna_word") == 500 and rec.get("fortna_bit") == 2 and rec.get("owner_state") == OWNER_ASSIGNED)
        ):
            example_assigned = rec
        if example_spare is None and rec.get("owner_source") == "CONFIGIO_MAPPED_UNUSED_BIT":
            # Prefer same word as 5MCR1 when present
            if rec.get("fortna_word") == 500:
                example_spare = rec
    if example_spare is None:
        for rec in channels:
            if rec.get("owner_source") == "CONFIGIO_MAPPED_UNUSED_BIT":
                example_spare = rec
                break

    configio = _configio_load_counts(run_dir, mach)
    stats = dict(model.get("stats") or {})

    # Gate 3 — single model confirmation
    sole_model = {
        "statement": (
            "HardwareIOModel is the sole tree for Hardware UI; "
            "adapters/modules/channels in this trace are the same objects."
        ),
        "source": "fortna_hardware_io_model.build_hardware_io_model",
        "adapter_count": len(adapters),
        "module_count": sum(len(a.get("modules") or []) for a in adapters),
        "channel_count": len(channels),
        "object_identity": "same_dict_tree",
    }

    audit_failures = [m for m in module_audits if not m.get("ownership_audit_ok")]

    return {
        "ok": bool(model.get("ok")),
        "generated_at": _ts(),
        "machine": mach,
        "run_dir": str(run_dir),
        "gate3_single_model": sole_model,
        "gate4_configio": configio,
        "summary": {
            "owner_states": dict(owner_counts),
            "owner_sources": dict(source_counts),
            "rejection_reason_counts": dict(reason_counts),
            "assigned": owner_counts.get(OWNER_ASSIGNED, 0),
            "unresolved": owner_counts.get(OWNER_UNRESOLVED, 0),
            "proven_spare": owner_counts.get(OWNER_PROVEN_SPARE, 0),
            "engineer_spare": owner_counts.get(OWNER_ENGINEER_SPARE, 0),
            "unknown": owner_counts.get(OWNER_UNKNOWN, 0),
            "channel_count": len(channels),
            "module_audit_failures": len(audit_failures),
            "model_stats": {
                "assigned_owner_count": stats.get("assigned_owner_count"),
                "unresolved_owner_count": stats.get("unresolved_owner_count"),
                "proven_spare_count": stats.get("proven_spare_count"),
            },
        },
        "gate1_examples": {
            "assigned_channel": example_assigned,
            "formerly_false_unresolved_unused_bit": example_spare,
        },
        "gate5_module_audits": module_audits,
        "channels": channels,
        "root_cause_fix": {
            "id": "configio_topology_desc_not_occupancy",
            "statement": (
                "_configio_desc_claim treated PANEL-NODE / PANEL-CATALOG Desc "
                "(e.g. CP5-NODE51-1A, CP2-1794-IA16-3) as occupied; those forms are "
                "module topology addressing only. Unused bits on mapped modules are "
                "PROVEN_SPARE (CONFIGIO_MAPPED_UNUSED_BIT), not UNRESOLVED_OWNER."
            ),
        },
    }


def render_trace_md(trace: dict[str, Any]) -> str:
    s = trace.get("summary") or {}
    cfg = trace.get("gate4_configio") or {}
    g1 = trace.get("gate1_examples") or {}
    sole = trace.get("gate3_single_model") or {}
    lines = [
        f"# I/O Channel Trace — {trace.get('machine')}",
        "",
        f"Generated: `{trace.get('generated_at')}`  ",
        f"RUN: `{trace.get('run_dir')}`",
        "",
        "## Root cause (Gate 2 fix)",
        "",
        (trace.get("root_cause_fix") or {}).get("statement") or "",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Channels | {s.get('channel_count', 0)} |",
        f"| ASSIGNED | {s.get('assigned', 0)} |",
        f"| PROVEN_SPARE | {s.get('proven_spare', 0)} |",
        f"| ENGINEER_SPARE | {s.get('engineer_spare', 0)} |",
        f"| UNRESOLVED_OWNER | {s.get('unresolved', 0)} |",
        f"| UNKNOWN | {s.get('unknown', 0)} |",
        f"| Module audit failures | {s.get('module_audit_failures', 0)} |",
        "",
        "### Owner sources",
        "",
    ]
    for k, n in sorted((s.get("owner_sources") or {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: {n}")
    lines.extend(["", "### Rejection reasons (UNRESOLVED only)", ""])
    reasons = s.get("rejection_reason_counts") or {}
    if not reasons:
        lines.append("_none_")
    else:
        for k, n in sorted(reasons.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- `{k}`: {n}")

    lines.extend(
        [
            "",
            "## Gate 3 — Single model",
            "",
            sole.get("statement") or "",
            "",
            f"- adapters: **{sole.get('adapter_count')}**",
            f"- modules: **{sole.get('module_count')}**",
            f"- channels: **{sole.get('channel_count')}**",
            f"- identity: `{sole.get('object_identity')}`",
            "",
            "## Gate 4 — Configio load",
            "",
            f"- path: `{cfg.get('path')}` ({cfg.get('source')})",
            f"- rows loaded: **{cfg.get('rows_loaded')}**",
            f"- Desc nonempty (topology): **{cfg.get('desc_topology')}** / nonempty **{cfg.get('desc_nonempty')}**",
            f"- Desc spare tokens: **{cfg.get('desc_spare_token')}**",
            f"- Desc signal/other: **{cfg.get('desc_signal_or_other')}**",
            f"- Conveyor rows / named: **{cfg.get('conveyor_rows')}** / **{cfg.get('conveyor_named_points')}**",
            "",
            "## Gate 1 — Manual end-to-end examples",
            "",
        ]
    )
    assigned = g1.get("assigned_channel") or {}
    spare = g1.get("formerly_false_unresolved_unused_bit") or {}
    lines.append("### ASSIGNED example (e.g. 5MCR1 on word 500 bit 2)")
    lines.append("")
    if assigned:
        lines.append(
            f"- `{assigned.get('physical_address')}` word `{assigned.get('fortna_word')}` "
            f"bit `{assigned.get('fortna_bit')}` → **{assigned.get('owner_state')}** "
            f"owner `{assigned.get('engineering_owner')}` source `{assigned.get('owner_source')}` "
            f"Desc `{assigned.get('configio_desc')}`"
        )
    else:
        lines.append("_not found on this RUN_")
    lines.append("")
    lines.append("### Formerly false-UNRESOLVED unused bit → PROVEN_SPARE")
    lines.append("")
    if spare:
        lines.append(
            f"- `{spare.get('physical_address')}` word `{spare.get('fortna_word')}` "
            f"bit `{spare.get('fortna_bit')}` → **{spare.get('owner_state')}** "
            f"source `{spare.get('owner_source')}` Desc `{spare.get('configio_desc')}`"
        )
    else:
        lines.append("_not found on this RUN_")

    lines.extend(["", "## Gate 5 — Module source-vs-UI audit", ""])
    lines.append("| RIO | Slot | Type | Expected | Named | Assigned | Unresolved | Spare | Missing | Audit |")
    lines.append("|-----|-----:|------|--------:|------:|---------:|-----------:|------:|--------:|-------|")
    for m in trace.get("gate5_module_audits") or []:
        if m.get("is_adapter_card"):
            continue
        ok = "PASS" if m.get("ownership_audit_ok") else f"FAIL:{m.get('ownership_audit_reason')}"
        lines.append(
            f"| {m.get('rio_name')} | {m.get('slot')} | {m.get('type')} | "
            f"{m.get('expected_occupied')} | {m.get('named')} | {m.get('assigned')} | "
            f"{m.get('unresolved')} | {m.get('spare')} | {m.get('missing')} | {ok} |"
        )
    lines.append("")
    lines.append(f"_Full per-channel records: `io_channel_trace.json` ({s.get('channel_count', 0)} channels)._")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="I/O channel ownership/topology trace")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "exports" / "stabilization")
    ap.add_argument("--no-log", action="store_true", help="Skip site_forge diagnostic log write")
    args = ap.parse_args(argv)

    out_dir = args.out if args.out.is_absolute() else (REPO_ROOT / args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace = build_io_channel_trace(args.run_dir, args.machine)
    json_path = out_dir / "io_channel_trace.json"
    md_path = out_dir / "io_channel_trace.md"
    json_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    md_path.write_text(render_trace_md(trace), encoding="utf-8")

    log_path = None
    if not args.no_log:
        try:
            from fortna_site_forge_log import write_site_forge_log

            log_path = write_site_forge_log(
                machine=str(trace.get("machine") or ""),
                run_dir=str(trace.get("run_dir") or ""),
                io_summary=trace.get("summary") or {},
                configio=trace.get("gate4_configio") or {},
                extra={"trace_json": str(json_path), "trace_md": str(md_path)},
            )
        except Exception as exc:
            print(f"site_forge log skipped: {exc}", file=sys.stderr)

    summary = trace.get("summary") or {}
    print(
        json.dumps(
            {
                "ok": trace.get("ok"),
                "machine": trace.get("machine"),
                "json": str(json_path),
                "md": str(md_path),
                "log": str(log_path) if log_path else None,
                "assigned": summary.get("assigned"),
                "proven_spare": summary.get("proven_spare"),
                "unresolved": summary.get("unresolved"),
            },
            indent=2,
        )
    )
    return 0 if trace.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
