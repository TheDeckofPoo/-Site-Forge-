#!/usr/bin/env python3
"""Collect Site Forge runtime provenance (git SHA/branch/root) and write JSON.

Used by desktop launch + Electron main so Help/About always shows deterministic
repo identity even when git is unavailable at runtime (.runtime_build.json).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if r.returncode != 0:
            return None
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def _load_fallback(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def collect(
    repo_root: Path | None = None,
    *,
    mode: str = "dev",
    write_path: Path | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    script_dir = Path(__file__).resolve().parent
    root = Path(repo_root).resolve() if repo_root else script_dir.parent.parent
    desktop = root / "desktop"
    dashboard = root / "dashboard"
    fallback_path = desktop / ".runtime_build.json"
    fb = _load_fallback(fallback_path)

    sha = _git(root, "rev-parse", "HEAD")
    short = _git(root, "rev-parse", "--short", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    git_root = _git(root, "rev-parse", "--show-toplevel")
    source = "git"

    if not sha:
        sha = str(fb.get("gitSha") or fb.get("sha") or "").strip() or None
        short = str(fb.get("gitShaShort") or fb.get("shortSha") or "").strip() or None
        branch = str(fb.get("branch") or branch or "").strip() or None
        if sha:
            source = "runtime_build_json"
            if not short and len(sha) >= 7:
                short = sha[:7]

    if not short and sha and len(sha) >= 7:
        short = sha[:7]

    started = started_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[str, Any] = {
        "gitSha": sha or "unknown",
        "gitShaShort": short or "unknown",
        "branch": branch or "unknown",
        "repoRoot": str(Path(git_root).resolve() if git_root else root),
        "sourceRoot": str(root),
        "dashboardSource": str((dashboard / "index.html").resolve()),
        "desktopDir": str(desktop.resolve()),
        "pythonSource": sys.executable,
        "compilerSource": str((root / "tools" / "scripts").resolve()),
        "mode": mode or "dev",
        "startedAt": started,
        "provenanceSource": source if sha else "unavailable",
        "worktree": str(Path(git_root).resolve() if git_root else root),
    }

    target = Path(write_path).resolve() if write_path else fallback_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Persist launch-stable identity fields (overwrite startedAt on each write)
        persist = {
            "gitSha": out["gitSha"],
            "gitShaShort": out["gitShaShort"],
            "branch": out["branch"],
            "repoRoot": out["repoRoot"],
            "sourceRoot": out["sourceRoot"],
            "dashboardSource": out["dashboardSource"],
            "desktopDir": out["desktopDir"],
            "pythonSource": out["pythonSource"],
            "compilerSource": out["compilerSource"],
            "mode": out["mode"],
            "startedAt": out["startedAt"],
            "provenanceSource": out["provenanceSource"],
            "worktree": out["worktree"],
        }
        target.write_text(json.dumps(persist, indent=2) + "\n", encoding="utf-8")
        out["runtimeBuildPath"] = str(target)
    except Exception as exc:
        out["runtimeBuildWriteError"] = str(exc)

    return out


def classify_iomap_selfcheck() -> dict[str, Any]:
    """Exercise VFD/IO_MAP symbol classifier (actual call, not source-string)."""
    try:
        from fortna_plc_symbol_registry import (  # type: ignore
            NETWORK_DEVICE_STATUS,
            classify_cp_io_operand,
        )

        r = classify_cp_io_operand(
            "P220A_MS.I.Auxiliary_Forward",
            direction_hint="I",
            declared={
                "scope": "controller",
                "owner": "autogen",
                "datatype": "Motor_Starter_UDT",
            },
        )
        ok = r.get("semantic_class") == NETWORK_DEVICE_STATUS
        return {
            "ok": bool(ok),
            "id": "vfd_iomap_symbol_classifier_py",
            "detail": f"classify_cp_io_operand → {r.get('semantic_class')}",
            "result": {
                "semantic_class": r.get("semantic_class"),
                "requires_physical_endpoint": r.get("requires_physical_endpoint"),
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "id": "vfd_iomap_symbol_classifier_py",
            "detail": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Site Forge runtime provenance")
    ap.add_argument("--repo-root", default=None, help="FortnaPlus repo root")
    ap.add_argument("--mode", default="dev", help="dev | packaged")
    ap.add_argument("--write", default=None, help="Override .runtime_build.json path")
    ap.add_argument("--self-check", action="store_true", help="Also run IO_MAP classifier check")
    args = ap.parse_args(argv)

    data = collect(
        Path(args.repo_root) if args.repo_root else None,
        mode=args.mode,
        write_path=Path(args.write) if args.write else None,
    )
    if args.self_check:
        data["selfCheck"] = {"iomap": classify_iomap_selfcheck()}
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
