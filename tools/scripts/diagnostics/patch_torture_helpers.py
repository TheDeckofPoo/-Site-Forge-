#!/usr/bin/env python3
"""Shared helpers for Overnight Phase 2 PATCH torture gate (no product logic)."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "tools" / "scripts"
RENO_PEEK = REPO / "workspace" / "_reno_peek"

CONVERGENCE_L5X = (
    REPO
    / "exports"
    / "diagnostics"
    / "convergence_final"
    / "generated_safe_partial"
    / "MSCRENOSHIP.L5X"
)
CONVERGENCE_L5X_ALT = (
    REPO / "exports" / "diagnostics" / "convergence_final" / "FINAL_MSCRENOSHIP.L5X"
)

BLANK_OPERAND_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU|ONS|OSR|OSF)\s*\(\s*(?:\)|\?[,)]|,\s*[,)]|\"\"|''|_unnamed_)",
    re.I,
)
FOREIGN_DESC_RE = re.compile(
    r"(?i)SSV50[0-9]|Greensboro|Brownsburg|ORLY_|Raw_P504|CPXXENET1"
)
CDATA_DESC_RE = re.compile(
    r"<(?:Description|Comment)>\s*<!\[CDATA\[(.*?)\]\]>",
    re.S,
)

# Soft timing budgets for discovery smoke (P8). Fail only on hard ceiling.
P8_WARN_SECS = 30.0
P8_FAIL_SECS = 120.0


def git_sha(repo: Path | None = None) -> str:
    root = repo or REPO
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def git_sha_short(repo: Path | None = None) -> str:
    full = git_sha(repo)
    return full[:7] if full else ""


def run_path(machine: str) -> Path | None:
    needle = f"MSCRENO-{machine.upper()}-RUN"
    if not RENO_PEEK.is_dir():
        return None
    for child in sorted(RENO_PEEK.iterdir()):
        if child.is_dir() and needle in child.name.upper():
            run = child / "RUN"
            if run.is_dir() and (run / "project.cfg").is_file():
                return run
    return None


def resolve_convergence_l5x() -> Path | None:
    for p in (CONVERGENCE_L5X, CONVERGENCE_L5X_ALT):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def scan_l5x_static_quality(l5x: Path) -> dict[str, Any]:
    """P7 smoke: structural quality without full auditor promote path."""
    text = l5x.read_text(encoding="utf-8", errors="replace")
    blanks = BLANK_OPERAND_RE.findall(text)
    programs = re.findall(r'<Program Name="([^"]+)"', text)
    ctrl = re.search(r'<Controller[^>]*Name="([^"]+)"', text)
    foreign_in_desc: list[str] = []
    for m in CDATA_DESC_RE.finditer(text):
        body = m.group(1)
        hit = FOREIGN_DESC_RE.search(body)
        if hit:
            foreign_in_desc.append(hit.group(0))
            if len(foreign_in_desc) >= 10:
                break
    return {
        "path": str(l5x),
        "bytes": l5x.stat().st_size,
        "has_rslogix": "RSLogix5000Content" in text,
        "has_controller": bool(ctrl),
        "controller_name": (ctrl.group(1) if ctrl else ""),
        "program_count": len(programs),
        "has_io_map": "IO_MAP" in programs,
        "blank_operand_count": len(blanks),
        "blank_operand_sample": blanks[:5],
        "foreign_desc_hits": foreign_in_desc,
        "foreign_desc_count": len(foreign_in_desc),
    }


def discovery_timing(machine: str, out_dir: Path) -> dict[str, Any]:
    """P8 smoke: time fortna_run_workspace_discover.discover for one virgin RUN."""
    import sys

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from fortna_run_workspace_discover import discover

    run = run_path(machine)
    if run is None:
        return {
            "machine": machine,
            "ok": False,
            "skipped": True,
            "reason": "RUN_MISSING",
            "seconds": 0.0,
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    result = discover(run, machine, out_dir)
    seconds = time.perf_counter() - t0
    counts = result.get("counts") if isinstance(result, dict) else {}
    equipment = int((counts or {}).get("equipment") or 0)
    return {
        "machine": machine,
        "ok": bool(result.get("ok")) and equipment > 0 and seconds <= P8_FAIL_SECS,
        "skipped": False,
        "seconds": round(seconds, 3),
        "warn": seconds > P8_WARN_SECS,
        "fail_budget_secs": P8_FAIL_SECS,
        "warn_budget_secs": P8_WARN_SECS,
        "equipment": equipment,
        "counts": counts,
        "code": result.get("code"),
        "incomplete_run": bool(result.get("incomplete_run")),
    }


def residue_scan_configured_sorter() -> dict[str, Any]:
    """P6 smoke: configured Sorter_Track emit must scrub foreign Divert descriptions."""
    import sys

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from fortna_sorter_build import SORTER_TRACK_PACK, build_sorter_track

    if not SORTER_TRACK_PACK.is_file():
        return {"ok": False, "skipped": True, "reason": "SORTER_TRACK_PACK_MISSING"}
    sorter = {
        "divert_count": 16,
        "divert_host_conveyor": "PS1",
        "induct_conveyor": "PS1",
        "induct_pe": "PE60_I",
        "encoders": [{"name": "SHIP SORT", "io": "ENC_SHIP", "include": True}],
    }
    compiled = build_sorter_track(sorter, library_text="")
    blob = "\n".join(
        [
            compiled.get("program_xml") or "",
            "\n".join(compiled.get("tags") or []),
            "\n".join(compiled.get("program_local_tags") or []),
        ]
    )
    hits: list[str] = []
    for m in CDATA_DESC_RE.finditer(blob):
        body = m.group(1)
        hit = FOREIGN_DESC_RE.search(body)
        if hit:
            hits.append(f"{hit.group(0)}::{body[:60]}")
    report = compiled.get("report") or {}
    return {
        "ok": len(hits) == 0 and report.get("mode") == "configured_pack",
        "skipped": False,
        "mode": report.get("mode"),
        "foreign_description_scrubbed": int(report.get("foreign_description_scrubbed") or 0),
        "foreign_desc_hits": hits[:10],
        "foreign_desc_count": len(hits),
    }
