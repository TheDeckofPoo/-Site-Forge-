#!/usr/bin/env python3
"""PLC2 foundation reset orchestration.

ControllerScope → Transport LOCAL/EXTERNAL → IO tree → IO_MAP (with placeholders)
→ foundation L5X → finished-oracle comparisons (validation only).

Does not expand PLC4/PLC5/Sawtooth/Sorter/WCS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import load_from_run  # noqa: E402
from fortna_io_regression_baselines import _parse_iomap_mappings, _parse_l5x_modules  # noqa: E402
from fortna_runtime_acceptance_recovery import (  # noqa: E402
    _import_via_apply_recipe,
    _last_json,
    _l5x_counts,
    _py,
    _run,
)
from fortna_site_model import write_json  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_finished_routines(text: str, name: str) -> dict[str, Any]:
    m = re.search(rf'<Routine[^>]*Name="{name}"[^>]*>(.*?)</Routine>', text, re.S | re.I)
    if not m:
        return {"found": False}
    body = m.group(1)
    rung_nums = [int(x) for x in re.findall(r'<Rung\b[^>]*Number="(\d+)"', body)]
    # CDATA or plain Text
    texts = re.findall(r"<!\[CDATA\[(.*?)\]\]>", body, re.S)
    if not texts:
        texts = re.findall(r"<Text>(.*?)</Text>", body, re.S)
    real = []
    placeholders = 0
    nops = 0
    for t in texts:
        t = t.strip()
        if "NO_PointPlaceholder" in t:
            placeholders += 1
        elif t.startswith("NOP"):
            nops += 1
        elif "XIC(" in t or "XIO(" in t:
            real.append(t)
    return {
        "found": True,
        "max_rung": max(rung_nums) if rung_nums else None,
        "rung_count": len(rung_nums),
        "real_mapping_texts": len(real),
        "placeholder_rungs": placeholders,
        "nop_rungs": nops,
        "xic": len(re.findall(r"XIC\(", body)),
        "ote": len(re.findall(r"OTE\(", body)),
        "channels": sorted(set(re.findall(r"((?:CP\dRIO\d+|T_1794_AENT_\d+)):[IO]\.Data\[\d+\]\.\d+", body)))[:40],
    }


def _extract_finished_device_tags(text: str) -> set[str]:
    """Finished PLC2 uses P###_Conv / P###_MS style tags — normalize to P###."""
    tags: set[str] = set()
    for n in re.findall(r'\bName="(P\d{2,4}[A-Za-z0-9_]*)"', text):
        nu = n.upper()
        if nu.startswith("PE") or nu.startswith("PB"):
            continue
        m = re.match(r"^(P\d{2,4}[A-Z]?)(?:_|$)", nu)
        if m:
            tags.add(m.group(1))
    for n in re.findall(r"\b(P\d{2,4}[A-Za-z]?)_(?:Conv|VFD|MS|CS)\b", text, re.I):
        tags.add(n.upper())
    return tags


def _compare_scope_to_finished(scope: dict[str, Any], finished_tags: set[str]) -> dict[str, Any]:
    by = scope.get("by_scope") or {}
    local = {str(t).upper() for t in (by.get("LOCAL") or scope.get("local_tags") or [])}
    if not local:
        local = {
            str(d.get("conveyor_tag") or d.get("device") or "").upper()
            for d in (scope.get("devices") or [])
            if (d.get("scope_class") or d.get("class")) == "LOCAL"
        }
    external = {str(t).upper() for t in (by.get("EXTERNAL_REFERENCE") or [])}
    if not external:
        external = {
            str(d.get("conveyor_tag") or d.get("device") or "").upper()
            for d in (scope.get("devices") or [])
            if (d.get("scope_class") or d.get("class")) == "EXTERNAL_REFERENCE"
        }
    # Normalize finished tags to parent P### when lettered
    fin_norm: set[str] = set()
    for t in finished_tags:
        tu = t.upper()
        fin_norm.add(tu)
        m = re.match(r"^(P\d{2,4})[A-Z]$", tu)
        if m:
            fin_norm.add(m.group(1))
    # Also expand LOCAL lettered → parent for overlap
    local_norm = set(local)
    for t in list(local):
        m = re.match(r"^(P\d{2,4})[A-Z]$", t)
        if m:
            local_norm.add(m.group(1))
    correct = sorted(local_norm & fin_norm)
    missed = sorted(fin_norm - local_norm - external)
    # Filter trivial noise like P01/P02 program-ish
    missed = [t for t in missed if re.match(r"^P\d{3}", t)]
    incorrect = sorted(local - fin_norm)
    # Parent LOCAL matching finished lettered child counts as correct, not incorrect
    incorrect = [
        t
        for t in incorrect
        if t not in fin_norm
        and not any(f.startswith(t) for f in fin_norm)
        and not any(t.startswith(f) for f in fin_norm if len(f) >= 4)
    ]
    return {
        "finished_device_tags": len(finished_tags),
        "finished_normalized": len(fin_norm),
        "correct_local": len(correct),
        "correct_local_sample": correct[:40],
        "missed_local": len(missed),
        "missed_local_sample": missed[:40],
        "incorrect_local": len(incorrect),
        "incorrect_local_sample": incorrect[:40],
        "external_reference_count": len(external),
        "finished_only_approx": missed[:40],
        "run_only_local": incorrect[:40],
        "note": "Validation only — finished PLC is oracle, not generation input. Lettered finished AOIs (P130A) vs RUN parent (P130) are treated as related.",
    }


def _compare_io_trees(gen_mods: list[dict], fin_text: str) -> dict[str, Any]:
    fin_mods = re.findall(
        r'<Module\b[^>]*?(?<![A-Za-z])Name="([^"]+)"[^>]*CatalogNumber="([^"]+)"',
        fin_text,
    )
    if not fin_mods:
        # try reverse attr order via separate scans
        names = re.findall(r'<Module\b[^>]*?(?<![A-Za-z])Name="([^"]+)"', fin_text)
        fin_mods = [(n, "") for n in names]
    gen_names = {m.get("name") for m in gen_mods if m.get("name")}
    fin_names = {n for n, _c in fin_mods}
    gen_cats = sorted({m.get("catalog") for m in gen_mods if m.get("catalog")})
    fin_cats = sorted({c for _n, c in fin_mods if c})
    # Structural compare by catalog multiset + adapter count (names differ T_1794 vs CP2RIO)
    return {
        "generated_module_count": len(gen_mods),
        "finished_module_count": len(fin_mods),
        "generated_names_sample": sorted(gen_names)[:30],
        "finished_names_sample": sorted(fin_names)[:30],
        "generated_catalogs": gen_cats,
        "finished_catalogs": fin_cats,
        "catalog_overlap": sorted(set(gen_cats) & set(fin_cats)),
        "adapters_generated": [
            m for m in gen_mods
            if m.get("catalog") in {"1794-AENT", "1756-EN2T", "1756-L83E"}
            or re.match(r"T_1794_AENT_\d+$", str(m.get("name") or ""))
            or str(m.get("name")) in {"Local", "CPXXENET1"}
        ],
        "note": "Name families differ (T_1794_AENT_* vs CP2RIO*/CP3RIO*). Compare catalogs/slots structurally; rack name is not ownership.",
    }


def _compare_iomap(gen_text: str, fin_text: str) -> dict[str, Any]:
    gen_i = _parse_finished_routines(gen_text, "CP_I")
    gen_o = _parse_finished_routines(gen_text, "CP_O")
    fin_i = _parse_finished_routines(fin_text, "CP_I")
    fin_o = _parse_finished_routines(fin_text, "CP_O")
    gen_maps = _parse_iomap_mappings(gen_text, limit=2000)
    # Exact tag matches ignoring module name family
    def norm_map(m: dict) -> tuple:
        tag = re.sub(r"^T_\d*", "", str(m.get("tag") or ""))
        return (tag, m.get("direction"), m.get("slot"), m.get("bit"))

    gen_keys = {norm_map(m) for m in gen_maps}
    # Parse finished real mappings similarly
    fin_maps = []
    for rn in ("CP_I", "CP_O"):
        m = re.search(rf'<Routine[^>]*Name="{rn}"[^>]*>(.*?)</Routine>', fin_text, re.S | re.I)
        if not m:
            continue
        body = m.group(1)
        for logic in re.findall(r"<!\[CDATA\[(.*?)\]\]>", body, re.S) or re.findall(r"<Text>(.*?)</Text>", body, re.S):
            logic = logic.strip()
            if "NO_PointPlaceholder" in logic or logic.startswith("NOP"):
                continue
            mi = re.search(r"XIC\(([^)]+:I\.Data\[(\d+)\]\.(\d+))\)OTE\(([^)]+)\);", logic)
            mo = re.search(r"XIC\(([^)]+)\)OTE\(([^)]+:O\.Data\[(\d+)\]\.(\d+))\);", logic)
            if mi:
                fin_maps.append({"direction": "I", "channel": mi.group(1), "slot": int(mi.group(2)), "bit": int(mi.group(3)), "tag": mi.group(4)})
            elif mo:
                fin_maps.append({"direction": "O", "channel": mo.group(2), "slot": int(mo.group(3)), "bit": int(mo.group(4)), "tag": mo.group(1)})
    fin_keys = {norm_map(m) for m in fin_maps}
    exact = gen_keys & fin_keys
    # Equivalent: same tag+direction ignoring slot/bit (module remaps)
    def tag_dir(k: tuple) -> tuple:
        return (k[0], k[1])

    gen_td = {tag_dir(k) for k in gen_keys}
    fin_td = {tag_dir(k) for k in fin_keys}
    equiv = gen_td & fin_td
    return {
        "finished_CP_I": fin_i,
        "generated_CP_I": gen_i,
        "finished_CP_O": fin_o,
        "generated_CP_O": gen_o,
        "finished_real_input_mappings": sum(1 for m in fin_maps if m["direction"] == "I"),
        "generated_real_input_mappings": sum(1 for m in gen_maps if m["direction"] == "I"),
        "finished_real_output_mappings": sum(1 for m in fin_maps if m["direction"] == "O"),
        "generated_real_output_mappings": sum(1 for m in gen_maps if m["direction"] == "O"),
        "exact_matches": len(exact),
        "equivalent_tag_direction_matches": len(equiv),
        "missing_tag_direction": len(fin_td - gen_td),
        "extra_tag_direction": len(gen_td - fin_td),
        "missing_sample": sorted(fin_td - gen_td)[:30],
        "extra_sample": sorted(gen_td - fin_td)[:30],
        "generated_placeholder_rungs_I": gen_i.get("placeholder_rungs"),
        "generated_placeholder_rungs_O": gen_o.get("placeholder_rungs"),
        "finished_placeholder_rungs_I": fin_i.get("placeholder_rungs"),
        "finished_placeholder_rungs_O": fin_o.get("placeholder_rungs"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--archive",
        type=Path,
        default=ROOT / "workspace" / "inbox" / "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz",
    )
    ap.add_argument(
        "--finished",
        type=Path,
        default=ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "plc2-foundation")
    ap.add_argument("--library", type=Path, default=ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X")
    ap.add_argument("--machine", default="ORNCCP2")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {"generated_at": _ts(), "ok": False, "machine": args.machine}

    # Import
    meta = _import_via_apply_recipe(args.archive)
    run_dir = Path(meta["run_dir"])
    report["import"] = {"ok": True, "run_dir": str(run_dir), "machine": meta.get("machine")}

    # Controller scope
    try:
        from fortna_controller_scope import build_controller_scope, write_controller_scope
    except ImportError:
        # Fallback thin wrapper on ownership until module lands
        from fortna_cp2_ownership import classify_ownership

        own = classify_ownership(run_dir, args.machine)
        devices = []
        for row in own.get("classifications") or []:
            cls = row["class"]
            if cls == "CP2_CONFIRMED":
                scls = "LOCAL"
            elif cls == "CP2_CANDIDATE":
                scls = "LOCAL"  # treat as local pending engineer; still RUN-owned
            elif cls == "NOT_CP2":
                scls = "OUT_OF_SCOPE"
            else:
                scls = "UNRESOLVED"
            devices.append(
                {
                    "device": row["conveyor_tag"],
                    "class": scls,
                    "ownership_class": cls,
                    "evidence": (row.get("evidence") or {}).get("reasons") or [],
                    "owned_io": (row.get("evidence") or {}).get("pe_links") or [],
                    "related_io": (
                        (row.get("evidence") or {}).get("motor_links") or []
                    )
                    + ((row.get("evidence") or {}).get("vfd_links") or []),
                    "why": f"ownership:{cls}",
                }
            )
        scope = {
            "generated_at": _ts(),
            "machine": args.machine,
            "source_of_truth": "RUN ownership (fortna_cp2_ownership) — no P-number heuristics",
            "counts": {
                "total_conveyor_rows": own.get("counts_total_mechanical"),
                "LOCAL": sum(1 for d in devices if d["class"] == "LOCAL"),
                "EXTERNAL_REFERENCE": 0,
                "OUT_OF_SCOPE": sum(1 for d in devices if d["class"] == "OUT_OF_SCOPE"),
                "UNRESOLVED": sum(1 for d in devices if d["class"] == "UNRESOLVED"),
            },
            "devices": devices,
            "local_tags": [d["device"] for d in devices if d["class"] == "LOCAL"],
            "ownership_raw_counts": own.get("counts"),
        }
        write_json(out / "controller_scope.json", scope)
    else:
        scope = build_controller_scope(run_dir, args.machine)
        write_controller_scope(scope, out / "controller_scope.json")

    report["controller_scope"] = scope.get("counts")

    # Finished oracle comparisons (validation only)
    if not args.finished.is_file():
        report["error"] = f"missing finished oracle {args.finished}"
        write_json(out / "report.json", report)
        return 1
    fin_text = args.finished.read_text(encoding="utf-8", errors="replace")
    fin_tags = _extract_finished_device_tags(fin_text)
    report["finished_validation"] = _compare_scope_to_finished(scope, fin_tags)

    # Workbook fresh + Build PLC with placeholders
    wb_path = ROOT / "workspace" / "autogen_workbook.json"
    if wb_path.is_file():
        wb_path.unlink()
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
    # Restrict workbook conveyors to LOCAL tags when possible
    local_set = {t.upper() for t in (scope.get("local_tags") or [])}
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
    ]
    # Optional placeholders flag if present
    gen_args.append("--io-map-placeholders")
    gr = _run(gen_args)
    # If flag unknown, retry without
    if not gr.get("ok") and "io-map-placeholders" in (gr.get("stderr") or ""):
        gen_args = [a for a in gen_args if a != "--io-map-placeholders"]
        gr = _run(gen_args)

    parsed = _last_json(gr.get("stdout") or "") or {}
    l5x = Path(parsed.get("l5x") or "")
    if not l5x.is_file():
        cands = [p for p in sorted(build_out.rglob("*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True) if "Library" not in p.name]
        l5x = cands[0] if cands else Path()
    if not l5x.is_file():
        report["build"] = {"ok": False, "error": parsed.get("error") or gr.get("stderr")}
        write_json(out / "report.json", report)
        return 1

    dest = out / "ORNCCP2_foundation_candidate.L5X"
    studio = ROOT / "exports" / "studio-validation" / "ORNCCP2_foundation_candidate.L5X"
    shutil.copy2(l5x, dest)
    studio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(l5x, studio)
    gen_text = dest.read_text(encoding="utf-8", errors="replace")
    gen_mods = _parse_l5x_modules(gen_text)
    l5x_c = _l5x_counts(dest)

    report["io_tree"] = _compare_io_trees(gen_mods, fin_text)
    report["io_tree"]["adapters_generated_count"] = len(report["io_tree"]["adapters_generated"])
    report["io_tree"]["child_modules_generated"] = max(
        0, (l5x_c.get("module_entries") or 0) - report["io_tree"]["adapters_generated_count"]
    )

    iomap = _compare_iomap(gen_text, fin_text)
    write_json(out / "io_map_comparison.json", iomap)
    report["io_map"] = {
        "generated_modules": l5x_c.get("module_entries"),
        "generated_xic_ote_refs": l5x_c.get("io_map_xic_ote_refs"),
        "nop_only": l5x_c.get("io_map_nop_only"),
        "comparison": {
            "finished_CP_I_rungs": (iomap.get("finished_CP_I") or {}).get("rung_count"),
            "generated_CP_I_rungs": (iomap.get("generated_CP_I") or {}).get("rung_count"),
            "finished_CP_O_rungs": (iomap.get("finished_CP_O") or {}).get("rung_count"),
            "generated_CP_O_rungs": (iomap.get("generated_CP_O") or {}).get("rung_count"),
            "finished_real_inputs": iomap.get("finished_real_input_mappings"),
            "generated_real_inputs": iomap.get("generated_real_input_mappings"),
            "finished_real_outputs": iomap.get("finished_real_output_mappings"),
            "generated_real_outputs": iomap.get("generated_real_output_mappings"),
            "exact_matches": iomap.get("exact_matches"),
            "equivalent_matches": iomap.get("equivalent_tag_direction_matches"),
            "missing": iomap.get("missing_tag_direction"),
            "extra": iomap.get("extra_tag_direction"),
        },
    }

    # Transport auto-build (scoped)
    tr = _run(
        _py()
        + [
            str(SCRIPTS / "fortna_run_physical_layout.py"),
            "--run-dir",
            str(run_dir),
            "--machine",
            args.machine,
            "--out",
            str(out / "transport"),
            "--stdout-graph",
        ]
    )
    graph = None
    for line in reversed((tr.get("stdout") or "").splitlines()):
        if not line.startswith("{"):
            continue
        try:
            parsed_g = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed_g, dict) and isinstance(parsed_g.get("areas"), list):
            graph = parsed_g
            break
    gpath = out / "transport" / "transport_graph_from_run.json"
    if gpath.is_file():
        graph = json.loads(gpath.read_text(encoding="utf-8"))
    transport_report = {"ok": False}
    if graph and isinstance(graph.get("areas"), list):
        nodes = []
        for a in graph["areas"]:
            nodes.extend(a.get("nodes") or [])
        local_n = [n for n in nodes if n.get("plcOwned") and not n.get("displayContext") and not n.get("externalReference")]
        ext_n = [n for n in nodes if n.get("externalReference") or (n.get("displayContext") and not n.get("plcOwned"))]
        # Heuristic: remote network clutter if many non-owned full conveyors
        remote_full = [n for n in nodes if not n.get("plcOwned") and not n.get("externalReference") and not n.get("displayContext")]
        transport_report = {
            "ok": True,
            "nodes_total": len(nodes),
            "local_rendered": len(local_n),
            "external_boundaries": len(ext_n),
            "full_remote_networks_rendered": len(remote_full) > 5,
            "local_sample": [n.get("conveyorTag") for n in local_n[:30]],
            "external_sample": [n.get("conveyorTag") for n in ext_n[:20]],
        }
    report["transport"] = transport_report

    report["l5x"] = {
        "path": str(dest),
        "studio_path": str(studio),
        "sha256": _sha256(dest),
        "programs": l5x_c.get("programs"),
        "module_entries": l5x_c.get("module_entries"),
    }
    report["acceptance_gate"] = {
        "CONTROLLER_SCOPE": scope.get("counts"),
        "FINISHED_VALIDATION": {
            "correct_local_devices": report["finished_validation"]["correct_local"],
            "missing_local_devices": report["finished_validation"]["missed_local"],
            "incorrect_local_devices": report["finished_validation"]["incorrect_local"],
        },
        "IO_TREE": {
            "adapters_generated": report["io_tree"]["adapters_generated_count"],
            "child_modules_generated": report["io_tree"]["child_modules_generated"],
            "catalog_overlap": report["io_tree"]["catalog_overlap"],
        },
        "CP_I": {
            "finished_rungs": report["io_map"]["comparison"]["finished_CP_I_rungs"],
            "generated_rungs": report["io_map"]["comparison"]["generated_CP_I_rungs"],
            "real_mappings_finished": report["io_map"]["comparison"]["finished_real_inputs"],
            "real_mappings_generated": report["io_map"]["comparison"]["generated_real_inputs"],
        },
        "CP_O": {
            "finished_rungs": report["io_map"]["comparison"]["finished_CP_O_rungs"],
            "generated_rungs": report["io_map"]["comparison"]["generated_CP_O_rungs"],
            "real_mappings_finished": report["io_map"]["comparison"]["finished_real_outputs"],
            "real_mappings_generated": report["io_map"]["comparison"]["generated_real_outputs"],
        },
        "MAPPINGS": {
            "exact_or_equivalent": report["io_map"]["comparison"]["equivalent_matches"],
            "exact": report["io_map"]["comparison"]["exact_matches"],
            "missing": report["io_map"]["comparison"]["missing"],
            "extra": report["io_map"]["comparison"]["extra"],
        },
        "TRANSPORT": {
            "full_remote_networks_rendered": transport_report.get("full_remote_networks_rendered"),
            "external_boundaries_rendered": (transport_report.get("external_boundaries") or 0) > 0
            or not transport_report.get("full_remote_networks_rendered"),
        },
        "STUDIO_candidate": str(studio),
    }
    report["ok"] = bool(
        (scope.get("counts") or {}).get("LOCAL", 0) > 0
        and (l5x_c.get("module_entries") or 0) > 0
        and not l5x_c.get("io_map_nop_only")
        and (report["io_map"]["comparison"]["generated_real_inputs"] or 0) > 0
    )
    write_json(out / "report.json", report)
    print(json.dumps({"ok": report["ok"], "gate": report["acceptance_gate"], "l5x": report["l5x"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
