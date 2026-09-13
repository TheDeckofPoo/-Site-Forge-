#!/usr/bin/env python3
"""Capture CP2/CP4/CP5 I/O regression baselines from load_from_run + UI-path L5X.

Preserves identity-level expectations (modules, slots, word/bit, tags, direction)
— not counts alone.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import load_from_run  # noqa: E402
from fortna_runtime_acceptance_recovery import _last_json, _l5x_counts, _py, _run  # noqa: E402
from fortna_site_model import write_json  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _import(archive: Path) -> dict[str, Any]:
    r = _run(_py() + [str(SCRIPTS / "apply_recipe.py"), "import", str(archive)])
    if not r.get("ok"):
        raise RuntimeError(r.get("stderr") or r.get("stdout") or "import failed")
    meta = _last_json(r.get("stdout") or "") or {}
    if not meta.get("run_dir"):
        raise RuntimeError("import missing run_dir")
    return meta


def _module_snapshot(inp) -> list[dict[str, Any]]:
    rows = []
    for m in getattr(inp, "modules", None) or []:
        rows.append(
            {
                "name": getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None),
                "catalog": getattr(m, "catalog_number", None)
                or getattr(m, "catalog", None)
                or (m.get("catalog_number") if isinstance(m, dict) else None)
                or (m.get("catalog") if isinstance(m, dict) else None),
                "parent": getattr(m, "parent", None) or (m.get("parent") if isinstance(m, dict) else None),
                "slot": getattr(m, "slot", None) if not isinstance(m, dict) else m.get("slot"),
                "address": getattr(m, "address", None) if not isinstance(m, dict) else m.get("address"),
                "direction": getattr(m, "direction", None) if not isinstance(m, dict) else m.get("direction"),
            }
        )
    # Also flatten eip_topology adapters/children when modules list is sparse
    topo = getattr(inp, "eip_topology", None) or []
    for ad in topo:
        if not isinstance(ad, dict):
            continue
        rows.append(
            {
                "name": ad.get("name") or ad.get("rio_name"),
                "catalog": ad.get("type") or ad.get("catalog"),
                "parent": None,
                "slot": None,
                "address": ad.get("ip") or ad.get("address"),
                "direction": "ADAPTER",
                "kind": "eip_adapter",
            }
        )
        for ch in ad.get("modules") or []:
            if not isinstance(ch, dict):
                continue
            rows.append(
                {
                    "name": ch.get("name"),
                    "catalog": ch.get("type") or ch.get("catalog"),
                    "parent": ad.get("name") or ad.get("rio_name"),
                    "slot": ch.get("slot") or ch.get("flex_slot"),
                    "address": None,
                    "direction": ch.get("direction"),
                    "kind": "eip_child",
                }
            )
    # Dedupe by name
    seen = set()
    out = []
    for r in rows:
        n = str(r.get("name") or "")
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(r)
    return out


def _word_map_snapshot(inp) -> list[dict[str, Any]]:
    wm = getattr(inp, "io_word_map", None) or {}
    rows = []
    for word, info in sorted(wm.items(), key=lambda kv: str(kv[0])):
        if not isinstance(info, dict):
            continue
        rows.append(
            {
                "word": str(word),
                "rio_name": info.get("rio_name"),
                "flex_slot": info.get("flex_slot"),
                "direction": info.get("direction"),
                "type": info.get("type"),
                "family": info.get("family"),
                "resolved_bank": info.get("resolved_bank"),
            }
        )
    return rows


def _io_points_snapshot(inp, *, limit: int = 80) -> list[dict[str, Any]]:
    rows = []
    for p in getattr(inp, "io_points", None) or []:
        name = getattr(p, "device_name", None) or ""
        if not name or str(name).upper() in {"SPARE", "INVALID", "N/A"}:
            continue
        rows.append(
            {
                "device_name": name,
                "device_type": getattr(p, "device_type", None),
                "direction": getattr(p, "direction", None),
                "fortna_bank": getattr(p, "fortna_bank", None),
                "fortna_bit": getattr(p, "fortna_bit", None),
            }
        )
    # Prefer PE / VFD / motor-ish first for representative fixtures
    def score(r: dict) -> tuple:
        n = str(r["device_name"]).upper()
        pe = 0 if re.match(r"^(?:EZ)?PE\d", n) else 1
        vfd = 0 if n.startswith("VFD") else 1
        return (pe, vfd, n)

    rows.sort(key=score)
    return rows[:limit]


def _parse_l5x_modules(text: str) -> list[dict[str, Any]]:
    mods = []
    for m in re.finditer(
        r'<Module\b([^>]*)>(.*?)</Module>|<Module\b([^/]*)/>',
        text,
        re.I | re.S,
    ):
        attrs = m.group(1) or m.group(3) or ""
        name = re.search(r'\bName="([^"]+)"', attrs)
        cat = re.search(r'\bCatalogNumber="([^"]+)"', attrs)
        parent = re.search(r'\bParentModule="([^"]+)"', attrs)
        slot = re.search(r'\bInhibited="[^"]*"[^>]*|\bSlot="([^"]+)"', attrs)
        # Slot often in Ports/Port Address
        body = m.group(2) or ""
        addr = re.search(r'Address="([^"]+)"', body) or re.search(r'Address="([^"]+)"', attrs)
        mods.append(
            {
                "name": name.group(1) if name else None,
                "catalog": cat.group(1) if cat else None,
                "parent": parent.group(1) if parent else None,
                "address": addr.group(1) if addr else None,
            }
        )
    # Prefer Module Name= over nested noise
    out = []
    seen = set()
    for mod in mods:
        n = mod.get("name")
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(mod)
    return out


def _parse_iomap_mappings(text: str, *, limit: int = 40) -> list[dict[str, Any]]:
    """Extract representative XIC/OTE mappings from IO_MAP program."""
    m = re.search(r'<Program[^>]*Name="IO_MAP"[^>]*>(.*?)</Program>', text, re.I | re.S)
    if not m:
        return []
    section = m.group(1)
    rows = []
    for rung in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", section, re.S):
        logic = rung.group(1).strip()
        if "NOP()" in logic and "XIC(" not in logic:
            continue
        # Input style: XIC(RIO:I.Data[s].b)OTE(TAG...)
        mi = re.search(
            r"XIC\(([^)]+:I\.Data\[(\d+)\]\.(\d+))\)OTE\(([^)]+)\);",
            logic,
        )
        mo = re.search(
            r"XIC\(([^)]+)\)OTE\(([^)]+:O\.Data\[(\d+)\]\.(\d+))\);",
            logic,
        )
        if mi:
            rows.append(
                {
                    "direction": "I",
                    "channel": mi.group(1),
                    "slot": int(mi.group(2)),
                    "bit": int(mi.group(3)),
                    "tag": mi.group(4),
                    "rung": logic,
                }
            )
        elif mo:
            rows.append(
                {
                    "direction": "O",
                    "channel": mo.group(2),
                    "slot": int(mo.group(3)),
                    "bit": int(mo.group(4)),
                    "tag": mo.group(1),
                    "rung": logic,
                }
            )
        if len(rows) >= limit:
            break
    return rows


def _representative_expectations(
    points: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pick identity checks: PE input + VFD/motor output + named modules."""
    exps: list[dict[str, Any]] = []
    # Modules: first adapter-like and first child
    adapters = [m for m in modules if m.get("name") and ("RIO" in str(m["name"]).upper() or "AENT" in str(m["name"]).upper())]
    for m in adapters[:3]:
        exps.append({"kind": "module_present", "name": m["name"], "catalog": m.get("catalog")})
    # PE mapping from L5X
    pe_maps = [r for r in mappings if re.search(r"PE\d", str(r.get("tag") or ""), re.I)]
    for r in pe_maps[:5]:
        exps.append(
            {
                "kind": "io_map_exact",
                "direction": r["direction"],
                "tag": r["tag"],
                "channel": r["channel"],
                "slot": r["slot"],
                "bit": r["bit"],
            }
        )
    # Output mapping
    out_maps = [r for r in mappings if r.get("direction") == "O"]
    for r in out_maps[:5]:
        exps.append(
            {
                "kind": "io_map_exact",
                "direction": "O",
                "tag": r["tag"],
                "channel": r["channel"],
                "slot": r["slot"],
                "bit": r["bit"],
            }
        )
    # Discovered PE points must remain mappable candidates
    for p in points:
        if re.match(r"^(?:EZ)?PE\d", str(p["device_name"]), re.I) and p.get("fortna_bank") is not None:
            exps.append(
                {
                    "kind": "discovered_pe_point",
                    "device_name": p["device_name"],
                    "fortna_bank": str(p["fortna_bank"]),
                    "fortna_bit": str(p.get("fortna_bit") or ""),
                    "direction": p.get("direction") or "I",
                }
            )
            if len([e for e in exps if e["kind"] == "discovered_pe_point"]) >= 5:
                break
    return exps


def capture_one(label: str, archive: Path, machine_hint: str, l5x: Path, out_dir: Path) -> dict[str, Any]:
    meta = _import(archive)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or machine_hint).upper()
    pn = str(meta.get("project_name") or meta.get("export_name") or "")
    m = re.search(r"_([A-Z0-9]+)$", pn, re.I)
    if m:
        machine = m.group(1).upper()

    inp = load_from_run(run_dir)
    modules = _module_snapshot(inp)
    word_map = _word_map_snapshot(inp)
    points = _io_points_snapshot(inp, limit=120)

    l5x_text = l5x.read_text(encoding="utf-8", errors="replace") if l5x.is_file() else ""
    l5x_counts = _l5x_counts(l5x) if l5x.is_file() else {"exists": False}
    l5x_modules = _parse_l5x_modules(l5x_text) if l5x_text else []
    mappings = _parse_iomap_mappings(l5x_text, limit=60) if l5x_text else []

    pe_points = [p for p in points if re.match(r"^(?:EZ)?PE\d", str(p["device_name"]), re.I)]
    out_points = [p for p in points if str(p.get("direction") or "").upper() in {"O", "OUT", "OUTPUT"}]

    baseline = {
        "generated_at": _ts(),
        "label": label,
        "machine": machine,
        "run_dir": str(run_dir),
        "archive": str(archive),
        "l5x_path": str(l5x) if l5x.is_file() else None,
        "source_of_truth": "RUN + load_from_run + UI-path L5X candidate",
        "generator_stack": [
            "fortna_autogen.load_from_run",
            "fortna_autogen.load_eip_topology",
            "fortna_autogen._load_eip_adapters",
            "fortna_autogen._build_eip_bank_index",
            "fortna_autogen build_l5x Modules + IO_MAP",
        ],
        "counts": {
            "modules_from_run": len(modules),
            "word_map_entries": len(word_map),
            "io_points_non_spare_sample": len(points),
            "pe_points_sample": len(pe_points),
            "output_points_sample": len(out_points),
            "l5x_module_entries": l5x_counts.get("module_entries"),
            "l5x_io_map_xic_ote": l5x_counts.get("io_map_xic_ote_refs"),
            "l5x_io_map_nop_only": l5x_counts.get("io_map_nop_only"),
            "l5x_programs": l5x_counts.get("programs"),
            "mapped_mappings_parsed": len(mappings),
        },
        "input_modules": [m for m in modules if str(m.get("direction") or "").upper() in {"I", "IN", "INPUT", "ADAPTER", ""}][:40],
        "output_modules": [m for m in modules if str(m.get("direction") or "").upper() in {"O", "OUT", "OUTPUT"}][:40],
        "remote_racks": [m for m in modules if m.get("kind") == "eip_adapter" or ("RIO" in str(m.get("name") or "").upper())][:20],
        "child_modules": [m for m in modules if m.get("kind") == "eip_child" or m.get("parent")][:60],
        "word_map_sample": word_map[:40],
        "io_points_sample": points[:40],
        "l5x_modules": l5x_modules[:80],
        "representative_mappings": mappings[:30],
        "expectations": _representative_expectations(points, mappings, l5x_modules or modules),
    }
    write_json(out_dir / f"{label.lower()}_io_baseline.json", baseline)
    return baseline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "io-regression-lock")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    inbox = ROOT / "workspace" / "inbox"
    studio = ROOT / "exports" / "studio-validation"
    specs = [
        ("CP2", inbox / "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz", "ORNCCP2", studio / "ORNCCP2_ui_candidate.L5X"),
        ("CP4", inbox / "20251016-0933-OReillyGreensboro-ORNCCP4-RUN.tar.gz", "ORNCCP4", studio / "ORNCCP4_ui_candidate.L5X"),
        ("CP5", inbox / "20251016-0933-OReillyGreensboro-ORNCCP5-RUN.tar.gz", "ORNCCP5", studio / "ORNCCP5_ui_candidate.L5X"),
    ]
    results = []
    for label, archive, mach, l5x in specs:
        print(f"=== baseline {label} ===", flush=True)
        if not archive.is_file():
            results.append({"label": label, "ok": False, "error": f"missing {archive}"})
            continue
        try:
            b = capture_one(label, archive, mach, l5x, out)
            results.append(
                {
                    "label": label,
                    "ok": True,
                    "machine": b["machine"],
                    "counts": b["counts"],
                    "expectation_count": len(b["expectations"]),
                }
            )
            print(json.dumps(results[-1], indent=2), flush=True)
        except Exception as exc:  # noqa: BLE001
            results.append({"label": label, "ok": False, "error": str(exc)})
            print(results[-1], flush=True)

    summary = {
        "generated_at": _ts(),
        "ok": all(r.get("ok") for r in results),
        "results": results,
        "note": "Baselines combine load_from_run (RUN truth) with UI-path studio L5X candidates",
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
