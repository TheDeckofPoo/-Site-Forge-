#!/usr/bin/env python3
"""Site Forge diagnostic log writer (Gate 7).

Writes exports/logs/site_forge_<timestamp>.log with runtime SHA, I/O
topology/ownership counts, and unresolved rejection_reason counts.

Also maintains exports/logs/site_forge_latest.path for Help → Diagnostics.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

LOG_DIR = REPO_ROOT / "exports" / "logs"
LATEST_PATH_FILE = LOG_DIR / "site_forge_latest.path"


def _ts_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _runtime_sha() -> dict[str, Any]:
    try:
        from fortna_runtime_provenance import collect

        p = collect(REPO_ROOT, mode="dev")
        return {
            "gitSha": p.get("gitSha"),
            "gitShaShort": p.get("gitShaShort"),
            "branch": p.get("branch"),
            "repoRoot": p.get("repoRoot"),
            "mode": p.get("mode"),
        }
    except Exception as exc:
        return {"gitSha": "unknown", "error": str(exc)}


def write_site_forge_log(
    *,
    machine: str = "",
    run_dir: str = "",
    io_summary: dict[str, Any] | None = None,
    configio: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    log_dir: Path | None = None,
) -> Path:
    """Write a diagnostic log and update the latest-path pointer. Returns log path."""
    out_dir = Path(log_dir) if log_dir else LOG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _ts_stamp()
    path = out_dir / f"site_forge_{stamp}.log"

    payload: dict[str, Any] = {
        "generated_at": _ts_iso(),
        "runtime": _runtime_sha(),
        "machine": (machine or "").strip() or None,
        "run_dir": run_dir or None,
        "io_summary": io_summary or {},
        "configio": configio or {},
        "extra": extra or {},
    }

    lines = [
        f"Site Forge diagnostic log — {payload['generated_at']}",
        "=" * 60,
        f"runtime.sha: {payload['runtime'].get('gitShaShort') or payload['runtime'].get('gitSha')}",
        f"runtime.branch: {payload['runtime'].get('branch')}",
        f"runtime.repo: {payload['runtime'].get('repoRoot')}",
        f"machine: {payload.get('machine')}",
        f"run_dir: {payload.get('run_dir')}",
        "",
        "I/O ownership counts:",
    ]
    summary = payload.get("io_summary") or {}
    for key in (
        "channel_count",
        "assigned",
        "proven_spare",
        "engineer_spare",
        "unresolved",
        "unknown",
        "module_audit_failures",
    ):
        if key in summary:
            lines.append(f"  {key}: {summary.get(key)}")
    states = summary.get("owner_states") or {}
    if states:
        lines.append("  owner_states:")
        for k, n in sorted(states.items()):
            lines.append(f"    {k}: {n}")
    sources = summary.get("owner_sources") or {}
    if sources:
        lines.append("  owner_sources:")
        for k, n in sorted(sources.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"    {k}: {n}")
    reasons = summary.get("rejection_reason_counts") or {}
    lines.append("  rejection_reason_counts:")
    if reasons:
        for k, n in sorted(reasons.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"    {k}: {n}")
    else:
        lines.append("    (none)")

    cfg = payload.get("configio") or {}
    if cfg:
        lines.extend(
            [
                "",
                "Configio:",
                f"  path: {cfg.get('path')}",
                f"  rows_loaded: {cfg.get('rows_loaded')}",
                f"  desc_topology: {cfg.get('desc_topology')}",
                f"  desc_nonempty: {cfg.get('desc_nonempty')}",
                f"  conveyor_named_points: {cfg.get('conveyor_named_points')}",
            ]
        )

    extra = payload.get("extra") or {}
    if extra:
        lines.append("")
        lines.append("Extra:")
        for k, v in extra.items():
            lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("--- JSON ---")
    lines.append(json.dumps(payload, indent=2))
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    latest = out_dir / "site_forge_latest.path"
    latest.write_text(str(path.resolve()), encoding="utf-8")
    # Convenience copy pointer also at fixed name for UI
    try:
        LATEST_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
        if latest.resolve() != LATEST_PATH_FILE.resolve():
            LATEST_PATH_FILE.write_text(str(path.resolve()), encoding="utf-8")
    except Exception:
        pass
    return path


def latest_log_path(log_dir: Path | None = None) -> Path | None:
    out_dir = Path(log_dir) if log_dir else LOG_DIR
    pointer = out_dir / "site_forge_latest.path"
    if pointer.is_file():
        raw = pointer.read_text(encoding="utf-8").strip()
        if raw and Path(raw).is_file():
            return Path(raw)
    if not out_dir.is_dir():
        return None
    cands = sorted(out_dir.glob("site_forge_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write / locate Site Forge diagnostic log")
    ap.add_argument("--machine", default="")
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--summary-json", type=Path, default=None, help="Optional io_channel_trace.json")
    ap.add_argument("--print-latest", action="store_true")
    args = ap.parse_args(argv)

    if args.print_latest:
        p = latest_log_path()
        print(str(p) if p else "")
        return 0 if p else 1

    summary = {}
    configio = {}
    if args.summary_json and args.summary_json.is_file():
        data = json.loads(args.summary_json.read_text(encoding="utf-8"))
        summary = data.get("summary") or {}
        configio = data.get("gate4_configio") or {}
        if not args.machine:
            args.machine = data.get("machine") or ""
        if not args.run_dir:
            args.run_dir = data.get("run_dir") or ""

    path = write_site_forge_log(
        machine=args.machine,
        run_dir=args.run_dir,
        io_summary=summary,
        configio=configio,
    )
    print(json.dumps({"ok": True, "log": str(path), "latest_pointer": str(LATEST_PATH_FILE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
