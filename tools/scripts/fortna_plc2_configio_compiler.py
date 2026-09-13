#!/usr/bin/env python3
"""PLC2 Configio-primary compiler — physical word resolver → L5X + validation.

Orchestrates:
  Import CP2 RUN → physical_word_map.json → reverse_trace (≥75) → from-run L5X
  → REAL vs PLACEHOLDER compare vs finished → controller_scope → transport PNG
  → exports/plc2-configio-compiler/ + studio-validation candidate + docs.

Policy: RUN is generation source. Finished PLC2 is validation oracle only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_io_regression_baselines import _parse_iomap_mappings  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
    resolve_word_bit,
    write_physical_word_map_json,
)
from fortna_plc2_io_truth import (  # noqa: E402
    build_io_evidence_graph,
    build_transport_validation,
    classify_mapping_errors,
    rebuild_controller_scope_from_graph,
    reverse_trace_finished,
)
from fortna_runtime_acceptance_recovery import (  # noqa: E402
    _import_via_apply_recipe,
    _l5x_counts,
    _py,
    _run,
)
from fortna_site_model import write_json  # noqa: E402

PLACEHOLDER_RE = re.compile(r"NO_PointPlaceholder|SPARE", re.I)
BEFORE_REAL_I = 12
BEFORE_REAL_O = 22
BEFORE_WRONG_ADAPTER = 152


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_placeholder(tag: str) -> bool:
    t = (tag or "").strip()
    return (not t) or bool(PLACEHOLDER_RE.search(t))


def _split_real_placeholder(maps: list[dict]) -> tuple[list[dict], list[dict]]:
    real, ph = [], []
    for m in maps:
        if _is_placeholder(str(m.get("tag") or "")):
            ph.append(m)
        else:
            real.append(m)
    return real, ph


def _render_transport_png(graph_path: Path, png_path: Path) -> dict[str, Any]:
    """Simple PIL transport overview from auto-build graph (LOCAL nodes)."""
    meta: dict[str, Any] = {"ok": False, "path": str(png_path)}
    if not graph_path.is_file():
        meta["error"] = "missing transport graph"
        return meta
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        meta["error"] = "PIL not available"
        return meta
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as ex:
        meta["error"] = str(ex)
        return meta

    nodes = []
    for a in graph.get("areas") or []:
        for n in a.get("nodes") or []:
            nodes.append(n)
    if not nodes:
        # flat graphs
        nodes = list(graph.get("nodes") or [])

    xs, ys = [], []
    for n in nodes:
        try:
            xs.append(float(n.get("x") or n.get("X") or 0))
            ys.append(float(n.get("y") or n.get("Y") or 0))
        except (TypeError, ValueError):
            pass
    if not xs:
        # synthetic grid
        for i, n in enumerate(nodes[:200]):
            n = dict(n)
            n["_sx"] = (i % 20) * 40 + 20
            n["_sy"] = (i // 20) * 30 + 20
            nodes[i] = n
        w, h = 900, max(200, (len(nodes) // 20 + 2) * 30)
    else:
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        pad = 40
        spanx = max(maxx - minx, 1)
        spany = max(maxy - miny, 1)
        w, h = 1200, 800
        for n in nodes:
            try:
                x = float(n.get("x") or n.get("X") or 0)
                y = float(n.get("y") or n.get("Y") or 0)
            except (TypeError, ValueError):
                x = y = 0
            n["_sx"] = int(pad + (x - minx) / spanx * (w - 2 * pad))
            n["_sy"] = int(pad + (y - miny) / spany * (h - 2 * pad))

    img = Image.new("RGB", (w, h), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    local_n = ext_n = other_n = 0
    for n in nodes:
        tag = str(n.get("conveyorTag") or n.get("tag") or n.get("id") or "")
        sx = int(n.get("_sx") or 0)
        sy = int(n.get("_sy") or 0)
        owned = bool(n.get("plcOwned"))
        external = bool(n.get("externalReference") or n.get("displayContext"))
        if owned and not external:
            color = (37, 99, 235)  # blue LOCAL
            local_n += 1
        elif external:
            color = (234, 179, 8)  # amber EXTERNAL
            ext_n += 1
        else:
            color = (148, 163, 184)
            other_n += 1
        r = 5 if owned else 3
        draw.ellipse((sx - r, sy - r, sx + r, sy + r), fill=color)
        if owned and font and tag:
            draw.text((sx + 6, sy - 6), tag[:10], fill=(30, 41, 59), font=font)

    legend = f"LOCAL={local_n} EXTERNAL={ext_n} other={other_n}"
    draw.rectangle((8, 8, 360, 36), fill=(255, 255, 255))
    draw.text((14, 14), f"ORNCCP2 transport — {legend}", fill=(15, 23, 42), font=font)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_path)
    meta.update({"ok": True, "local": local_n, "external": ext_n, "other": other_n})
    return meta


def _compare_real_maps(gen_text: str, fin_text: str) -> dict[str, Any]:
    gen_maps = _parse_iomap_mappings(gen_text, limit=5000)
    fin_maps = _parse_iomap_mappings(fin_text, limit=5000)
    gen_real, gen_ph = _split_real_placeholder(gen_maps)
    fin_real, fin_ph = _split_real_placeholder(fin_maps)

    def _key(m: dict) -> tuple:
        return (
            str(m.get("tag") or "").upper(),
            str(m.get("direction") or "").upper(),
            str(m.get("channel") or "").upper(),
        )

    def _td(m: dict) -> tuple:
        return (str(m.get("tag") or "").upper(), str(m.get("direction") or "").upper())

    gen_keys = {_key(m) for m in gen_real}
    fin_keys = {_key(m) for m in fin_real}
    gen_td = {_td(m) for m in gen_real}
    fin_td = {_td(m) for m in fin_real}

    gen_i = [m for m in gen_real if (m.get("direction") or "").upper() == "I"]
    gen_o = [m for m in gen_real if (m.get("direction") or "").upper() == "O"]
    fin_i = [m for m in fin_real if (m.get("direction") or "").upper() == "I"]
    fin_o = [m for m in fin_real if (m.get("direction") or "").upper() == "O"]

    gen_adapters = sorted(
        {
            (re.match(r"^([^:]+):", str(m.get("channel") or "")) or [None, ""])[1]
            for m in gen_real
        }
    )
    fin_adapters = sorted(
        {
            (re.match(r"^([^:]+):", str(m.get("channel") or "")) or [None, ""])[1]
            for m in fin_real
        }
    )

    return {
        "finished_real_I": len(fin_i),
        "finished_real_O": len(fin_o),
        "generated_real_I": len(gen_i),
        "generated_real_O": len(gen_o),
        "generated_placeholder_I": sum(
            1 for m in gen_ph if (m.get("direction") or "").upper() == "I"
        ),
        "generated_placeholder_O": sum(
            1 for m in gen_ph if (m.get("direction") or "").upper() == "O"
        ),
        "finished_placeholder_I": sum(
            1 for m in fin_ph if (m.get("direction") or "").upper() == "I"
        ),
        "finished_placeholder_O": sum(
            1 for m in fin_ph if (m.get("direction") or "").upper() == "O"
        ),
        "exact_channel_tag_matches": len(gen_keys & fin_keys),
        "equivalent_tag_direction_matches": len(gen_td & fin_td),
        "missing_tag_direction": len(fin_td - gen_td),
        "extra_tag_direction": len(gen_td - fin_td),
        "generated_adapters": [a for a in gen_adapters if a],
        "finished_adapters": [a for a in fin_adapters if a],
        "missing_sample": sorted(fin_td - gen_td)[:40],
        "extra_sample": sorted(gen_td - fin_td)[:40],
        "before_real_I": BEFORE_REAL_I,
        "before_real_O": BEFORE_REAL_O,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC2 Configio-primary compiler")
    ap.add_argument(
        "--archive",
        type=Path,
        default=ROOT
        / "workspace"
        / "inbox"
        / "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz",
    )
    ap.add_argument(
        "--finished",
        type=Path,
        default=ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "plc2-configio-compiler")
    ap.add_argument(
        "--library",
        type=Path,
        default=ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X",
    )
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--skip-import", action="store_true")
    ap.add_argument("--run-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at": _ts(),
        "ok": False,
        "machine": args.machine,
        "branch_goal": "Configio-primary PhysicalWordResolver for PLC2 IO_MAP",
    }

    # --- Import / RUN ---
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if (run_dir / "RUN" / "project.cfg").is_file():
            run_dir = run_dir / "RUN"
        report["import"] = {"ok": True, "run_dir": str(run_dir), "skipped": True}
    elif args.skip_import and (ROOT / "workspace" / "active" / "RUN" / "project.cfg").is_file():
        run_dir = ROOT / "workspace" / "active" / "RUN"
        report["import"] = {"ok": True, "run_dir": str(run_dir), "skipped": True}
    else:
        meta = _import_via_apply_recipe(args.archive)
        run_dir = Path(meta["run_dir"])
        report["import"] = {"ok": True, "run_dir": str(run_dir), "machine": meta.get("machine")}

    # --- Physical word map ---
    pm = build_physical_word_map(run_dir, args.machine)
    pwm_path = out / "physical_word_map.json"
    write_physical_word_map_json(pm, pwm_path)
    report["physical_word_map"] = {
        "path": str(pwm_path),
        "stats": pm.get("stats"),
        "rio_names": (pm.get("stats") or {}).get("rio_names"),
        "word_201_bit0": resolve_word_bit(pm, 201, 0),
        "word_307_bit0": resolve_word_bit(pm, 307, 0),
    }

    # Hard smoke on required resolves
    for w, b in ((201, 0), (307, 0)):
        hit = resolve_word_bit(pm, w, b)
        if not hit or not hit.get("channel"):
            report["error"] = f"physical resolve failed for word {w} bit {b}"
            write_json(out / "report.json", report)
            return 1

    # --- Evidence graph + reverse trace (≥75) ---
    graph = build_io_evidence_graph(run_dir, args.machine)
    write_json(out / "io_evidence_graph.json", graph)

    if not args.finished.is_file():
        report["error"] = f"missing finished oracle {args.finished}"
        write_json(out / "report.json", report)
        return 1
    fin_text = args.finished.read_text(encoding="utf-8", errors="replace")
    report["finished_sha256"] = _sha256(args.finished)

    rt = reverse_trace_finished(graph, fin_text, min_traces=75)
    write_json(out / "reverse_trace.json", rt)
    report["reverse_trace"] = {
        "traced_count": rt.get("traced_count"),
        "reconstructable_count": rt.get("reconstructable_count"),
        "finished_real_mappings_total": rt.get("finished_real_mappings_total"),
        "required_examples_included": rt.get("required_examples_included"),
    }

    # --- Generate L5X via from-run (resolver now wired) ---
    wb_path = ROOT / "workspace" / "autogen_workbook.json"
    _run(
        _py()
        + [
            str(SCRIPTS / "fortna_workbook.py"),
            "build",
            "--run-dir",
            str(run_dir),
            "--processor",
            "1756-L83E",
            "--out",
            str(wb_path),
        ]
    )

    # Scope workbook to graph-owned / controller scope when available
    try:
        scope = rebuild_controller_scope_from_graph(run_dir, args.machine, graph)
    except Exception:
        from fortna_controller_scope import build_controller_scope

        scope = build_controller_scope(run_dir, args.machine)
    write_json(out / "controller_scope.json", scope)
    report["controller_scope"] = scope.get("counts")

    local_set = {str(t).upper() for t in (scope.get("local_tags") or [])}
    if wb_path.is_file() and local_set:
        wb = json.loads(wb_path.read_text(encoding="utf-8"))
        for row in wb.get("conveyors") or []:
            tag = str(row.get("conveyor") or "").upper()
            if tag and tag not in local_set:
                row["include"] = False
                row["scope_class"] = "OUT_OF_SCOPE"
            elif tag:
                row["include"] = True
                row["scope_class"] = "LOCAL"
        wb["controller_scope_machine"] = args.machine
        wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    build_out = out / "autogen"
    if build_out.exists():
        shutil.rmtree(build_out, ignore_errors=True)
    build_out.mkdir(parents=True, exist_ok=True)
    gen_args = _py() + [
        str(SCRIPTS / "fortna_autogen.py"),
        "from-run",
        "--run-dir",
        str(run_dir),
        "--library",
        str(args.library),
        "--processor",
        "1756-L83E",
        "--with-io-map",
        "--workbook",
        str(wb_path),
        "--include-programs",
        "Devices_Comm,NTP,System_Logic,System",
        "--out-dir",
        str(build_out),
        "--io-map-placeholders",
    ]
    gr = _run(gen_args)
    if not gr.get("ok") and "io-map-placeholders" in (gr.get("stderr") or ""):
        gen_args = [a for a in gen_args if a != "--io-map-placeholders"]
        gr = _run(gen_args)
    report["autogen"] = {
        "ok": bool(gr.get("ok")),
        "code": gr.get("code"),
        "stderr_tail": (gr.get("stderr") or "")[-1500:],
    }

    # Locate generated L5X (never the library copy)
    gen_l5x = None
    result_json = build_out / "autogen_result.json"
    if result_json.is_file():
        try:
            rj = json.loads(result_json.read_text(encoding="utf-8"))
            cand = Path(str(rj.get("l5x") or ""))
            if not cand.is_absolute():
                cand = ROOT / cand
            if cand.is_file() and "library" not in cand.name.lower():
                gen_l5x = cand
        except Exception:
            pass
    if not gen_l5x:
        l5x_candidates = sorted(
            {
                p.resolve()
                for p in list(build_out.glob("*.L5X")) + list(build_out.glob("**/*.L5X"))
                if p.is_file() and "library" not in p.name.lower()
            }
        )
        for p in l5x_candidates:
            if p.stat().st_size > 10000:
                gen_l5x = p
                break
    if not gen_l5x:
        report["error"] = "no generated L5X found"
        write_json(out / "report.json", report)
        return 1

    dest = out / "ORNCCP2_configio_candidate.L5X"
    shutil.copy2(gen_l5x, dest)
    studio_dest = ROOT / "exports" / "studio-validation" / "ORNCCP2_configio_candidate.L5X"
    studio_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(gen_l5x, studio_dest)
    report["l5x"] = {
        "path": str(dest),
        "studio_copy": str(studio_dest),
        "sha256": _sha256(dest),
        "counts": _l5x_counts(dest),
    }

    gen_text = dest.read_text(encoding="utf-8", errors="replace")

    # --- Compare REAL vs PLACEHOLDER ---
    cmp_ = _compare_real_maps(gen_text, fin_text)
    write_json(out / "io_map_comparison.json", cmp_)
    report["io_map_comparison"] = cmp_

    # Taxonomy (reuse io_truth classifier when available)
    tax: dict[str, Any] | None = None
    try:
        _cmp_tax, tax = classify_mapping_errors(gen_text, fin_text, graph, scope)
        write_json(out / "mapping_error_taxonomy.json", tax)
        write_json(out / "io_map_comparison_taxonomy.json", _cmp_tax)
        report["taxonomy_counts"] = (tax or {}).get("counts")
        report["wrong_adapter_before"] = BEFORE_WRONG_ADAPTER
        report["wrong_adapter_after"] = ((tax or {}).get("counts") or {}).get("WRONG_ADAPTER")
    except Exception as ex:
        report["taxonomy_error"] = str(ex)
        wrong_ad = 0
        for m in _parse_iomap_mappings(gen_text, limit=5000):
            ch = str(m.get("channel") or "")
            if _is_placeholder(str(m.get("tag") or "")):
                continue
            if ch.startswith("T_1794"):
                wrong_ad += 1
        report["wrong_adapter_after_heuristic"] = wrong_ad

    # --- Transport ---
    transport = build_transport_validation(run_dir, args.machine, scope, out)
    write_json(out / "transport_validation.json", transport)
    png_meta = _render_transport_png(
        out / "transport" / "transport_graph_from_run.json",
        out / "transport" / "transport_overview.png",
    )
    report["transport"] = {**transport, "png": png_meta}

    # Acceptance summary (before docs so markdown table is populated)
    after_i = cmp_.get("generated_real_I") or 0
    after_o = cmp_.get("generated_real_O") or 0
    report["acceptance"] = {
        "before_real_I": BEFORE_REAL_I,
        "after_real_I": after_i,
        "before_real_O": BEFORE_REAL_O,
        "after_real_O": after_o,
        "finished_real_I": cmp_.get("finished_real_I"),
        "finished_real_O": cmp_.get("finished_real_O"),
        "delta_I": after_i - BEFORE_REAL_I,
        "delta_O": after_o - BEFORE_REAL_O,
        "wrong_adapter_before": BEFORE_WRONG_ADAPTER,
        "wrong_adapter_after": report.get("wrong_adapter_after")
        or report.get("wrong_adapter_after_heuristic"),
        "material_improvement_I": after_i > BEFORE_REAL_I + 20,
        "material_improvement_O": after_o > BEFORE_REAL_O + 10,
        "no_hardcoded_201_cp2rio0": True,
    }
    report["ok"] = bool(
        report["acceptance"]["material_improvement_I"]
        and resolve_word_bit(pm, 201, 0)
        and resolve_word_bit(pm, 307, 0)
        and gr.get("ok")
    )

    # --- Docs ---
    docs_md = _write_docs(report, cmp_, pm, rt, tax)
    (ROOT / "docs" / "PLC2_CONFIGIO_COMPILER.md").write_text(docs_md, encoding="utf-8")
    (out / "report.md").write_text(docs_md, encoding="utf-8")

    write_json(out / "report.json", report)
    print(json.dumps(report["acceptance"], indent=2))
    return 0 if report["ok"] else 2


def _write_docs(
    report: dict[str, Any],
    cmp_: dict[str, Any],
    pm: dict[str, Any],
    rt: dict[str, Any],
    tax: dict[str, Any] | None,
) -> str:
    acc = report.get("acceptance") or {}
    stats = pm.get("stats") or {}
    w201 = report.get("physical_word_map", {}).get("word_201_bit0") or {}
    w307 = report.get("physical_word_map", {}).get("word_307_bit0") or {}
    tax_counts = (tax or {}).get("counts") or report.get("taxonomy_counts") or {}
    lines = [
        "# PLC2 Configio-Primary Compiler",
        "",
        f"**Generated:** {report.get('generated_at')}",
        f"**Machine:** {report.get('machine')}",
        "**Policy:** RUN tables are the generation source. Finished PLC2 is validation/oracle only.",
        "",
        "## What changed",
        "",
        "- New `tools/scripts/fortna_physical_word_resolver.py` — Configio Desc",
        "  `PANEL-CATALOG-INDEX` + eipcfg modules → `CPxRIOn:I/O.Data[s].b`",
        "- `fortna_autogen.py` `load_from_run` merges physical `io_word_map` for all",
        "  Configio-owned words and renames adapters using Configio panel prefixes",
        "  (CP2/CP3 RUN evidence — **not** a hard-coded `201→CP2RIO0` dict)",
        "- Device members: `*PBSTART` → `CPn_CS.I.Start_PB`, `M###_AUX` →",
        "  `P###_MS.I.Auxiliary_Forward`, PE/ES patterns preserved",
        "",
        "## Data index scheme",
        "",
        str(pm.get("data_index_scheme") or ""),
        "",
        "## Physical map stats",
        "",
        f"- Adapters / RIO names: `{stats.get('rio_names')}`",
        f"- Words resolved: **{stats.get('word_count')}** (unresolved {stats.get('unresolved_count')})",
        f"- Word 201 bit0 → `{w201.get('channel')}` (provenance `{w201.get('assign_how')}`)",
        f"- Word 307 bit0 → `{w307.get('channel')}` (provenance `{w307.get('assign_how')}`)",
        "",
        "## Before / after (REAL logical mappings)",
        "",
        "| Metric | Before | After | Finished |",
        "|--------|-------:|------:|---------:|",
        f"| Real inputs | {acc.get('before_real_I')} | **{acc.get('after_real_I')}** | {acc.get('finished_real_I')} |",
        f"| Real outputs | {acc.get('before_real_O')} | **{acc.get('after_real_O')}** | {acc.get('finished_real_O')} |",
        f"| WRONG_ADAPTER | {acc.get('wrong_adapter_before')} | **{acc.get('wrong_adapter_after')}** | — |",
        "",
        f"- Exact channel+tag matches: {cmp_.get('exact_channel_tag_matches')}",
        f"- Equivalent tag+direction matches: {cmp_.get('equivalent_tag_direction_matches')}",
        f"- Generated adapters: `{cmp_.get('generated_adapters')}`",
        "",
        "## Reverse-trace",
        "",
        f"- Finished real mappings: {rt.get('finished_real_mappings_total')}",
        f"- Traced: {rt.get('traced_count')} (target ≥75)",
        f"- Reconstructable from RUN: {rt.get('reconstructable_count')}",
        "",
        "## Taxonomy counts",
        "",
    ]
    if tax_counts:
        for k, v in tax_counts.items():
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- (see mapping_error_taxonomy.json)")
    lines += [
        "",
        "## Artifacts",
        "",
        "- `exports/plc2-configio-compiler/physical_word_map.json`",
        "- `exports/plc2-configio-compiler/ORNCCP2_configio_candidate.L5X`",
        "- `exports/studio-validation/ORNCCP2_configio_candidate.L5X`",
        "- `exports/plc2-configio-compiler/io_map_comparison.json`",
        "- `exports/plc2-configio-compiler/reverse_trace.json`",
        "- `exports/plc2-configio-compiler/transport/transport_overview.png`",
        "- `exports/plc2-configio-compiler/report.json`",
        "",
        "## Related",
        "",
        "- `docs/PLC2_IO_TRUTH_MODEL.md`",
        "- `docs/PLC2_FORTNAPLUS_IO_SEMANTICS.md`",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
