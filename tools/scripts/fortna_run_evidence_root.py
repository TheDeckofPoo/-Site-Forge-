#!/usr/bin/env python3
"""Bind the active machine/controller RUN evidence root explicitly.

Never switch the evidence root merely because a nested RUN\\RUN folder exists.
Competing candidate roots are reported as REVIEW/INTEGRITY — not silently chosen.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

_CFG_MACHINE_RE = re.compile(r"MACHINENAME\s*=\s*(\S+)", re.I)


def _is_run_root(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        if (path / "project.cfg").is_file():
            return True
        if (path / "FORTNA").is_dir() and any((path / "FORTNA").glob("Conveyor.asc*")):
            return True
    except OSError:
        return False
    return False


def _read_machine(path: Path) -> str:
    cfg = path / "project.cfg"
    if not cfg.is_file():
        return ""
    try:
        txt = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = _CFG_MACHINE_RE.search(txt)
    return (m.group(1).strip().upper() if m else "")


def _candidate_record(path: Path, *, reason: str) -> dict[str, Any]:
    resolved = path.resolve() if path.exists() else path
    return {
        "path": str(resolved),
        "reason": reason,
        "is_run_root": _is_run_root(path),
        "machine": _read_machine(path) if _is_run_root(path) else "",
        "nested_run_child": _is_run_root(path / "RUN"),
    }


def discover_evidence_root_candidates(
    preferred: Path | str | None = None,
    *,
    workspace_active: Path | str | None = None,
    meta_run_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List plausible RUN roots without selecting among nested competitors."""
    active = Path(workspace_active) if workspace_active else (ROOT / "workspace" / "active")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(path: Path | None, reason: str) -> None:
        if path is None:
            return
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            return
        seen.add(key)
        out.append(_candidate_record(Path(path), reason=reason))

    if preferred:
        pref = Path(preferred)
        _add(pref, "preferred")
        # Nested child is recorded as a competitor, never an automatic winner.
        if _is_run_root(pref) and _is_run_root(pref / "RUN"):
            _add(pref / "RUN", "nested_child_of_preferred")
        elif (not _is_run_root(pref)) and _is_run_root(pref / "RUN"):
            _add(pref / "RUN", "preferred_missing_cfg_child_run")

    if meta_run_dir:
        meta = Path(meta_run_dir)
        _add(meta, "active_meta_run_dir")
        if _is_run_root(meta) and _is_run_root(meta / "RUN"):
            _add(meta / "RUN", "nested_child_of_active_meta")

    _add(active / "RUN", "workspace_active_run")
    if _is_run_root(active / "RUN") and _is_run_root(active / "RUN" / "RUN"):
        _add(active / "RUN" / "RUN", "nested_run_run_under_active")

    _add(active / ".." / "active_work" / "RUN", "workspace_active_work_run")
    return out


def bind_evidence_root(
    preferred: Path | str | None = None,
    *,
    machine: str | None = None,
    workspace_active: Path | str | None = None,
    meta_run_dir: Path | str | None = None,
    allow_nested_fallback: bool = False,
) -> dict[str, Any]:
    """Bind one active evidence root for the current machine/controller.

    Rules:
      1. Prefer an explicitly bound preferred / active-meta root that is already a RUN.
      2. Never switch to a nested RUN\\RUN solely because it exists.
      3. Competing viable roots → status REVIEW_REQUIRED / INTEGRITY.
      4. Nested fallback only when the bound parent is NOT a RUN and allow_nested_fallback.
    """
    want = (machine or "").strip().upper()
    candidates = discover_evidence_root_candidates(
        preferred,
        workspace_active=workspace_active,
        meta_run_dir=meta_run_dir,
    )
    viable = [c for c in candidates if c.get("is_run_root")]

    bound: dict[str, Any] | None = None
    status = "OK"
    integrity: list[str] = []

    # Explicit preferred wins when it is already a RUN root.
    for c in candidates:
        if c.get("reason") == "preferred" and c.get("is_run_root"):
            bound = c
            break
    if bound is None:
        for c in candidates:
            if c.get("reason") == "active_meta_run_dir" and c.get("is_run_root"):
                bound = c
                break
    if bound is None:
        for c in candidates:
            if c.get("reason") == "workspace_active_run" and c.get("is_run_root"):
                bound = c
                break

    # Parent missing cfg but child RUN exists — only with explicit fallback.
    if bound is None and allow_nested_fallback:
        for c in candidates:
            if c.get("reason") in {
                "preferred_missing_cfg_child_run",
                "nested_child_of_preferred",
            } and c.get("is_run_root"):
                bound = c
                status = "REVIEW_REQUIRED"
                integrity.append("nested_fallback_used")
                break

    # Competing viable roots (e.g. RUN and RUN\\RUN both have project.cfg).
    nested_pairs = []
    for c in viable:
        child = Path(c["path"]) / "RUN"
        if _is_run_root(child):
            nested_pairs.append((c["path"], str(child.resolve())))
    if nested_pairs:
        status = "REVIEW_REQUIRED"
        integrity.append("competing_nested_run_roots")
        for parent, child in nested_pairs:
            integrity.append(f"competing:{parent}|{child}")

    # Machine mismatch across viable roots.
    if want:
        mismatched = [
            c for c in viable
            if c.get("machine") and c["machine"] != want
        ]
        matched = [c for c in viable if c.get("machine") == want]
        if mismatched and matched and bound and bound.get("machine") and bound["machine"] != want:
            status = "REVIEW_REQUIRED"
            integrity.append("active_machine_mismatch")
        elif len({c.get("machine") for c in viable if c.get("machine")}) > 1:
            status = "REVIEW_REQUIRED"
            integrity.append("competing_machine_labels")

    if bound is None:
        return {
            "ok": False,
            "status": "REVIEW_REQUIRED",
            "integrity": ["no_viable_evidence_root"] + integrity,
            "bound_root": None,
            "machine": want or None,
            "candidates": candidates,
            "policy": {
                "never_switch_for_nested_run": True,
                "competing_roots_are_review": True,
            },
        }

    # If we bound the parent and a nested child also exists, keep parent — do not switch.
    bound_path = Path(bound["path"])
    if _is_run_root(bound_path / "RUN"):
        integrity.append("nested_run_present_ignored")
        if status == "OK":
            status = "OK"  # parent remains authoritative; integrity note only
        # Presence alone is not a switch; competing cfg content elevates REVIEW above.
        child_cfg = bound_path / "RUN" / "project.cfg"
        parent_cfg = bound_path / "project.cfg"
        if child_cfg.is_file() and parent_cfg.is_file():
            try:
                if child_cfg.read_bytes() != parent_cfg.read_bytes():
                    status = "REVIEW_REQUIRED"
                    if "competing_nested_run_roots" not in integrity:
                        integrity.append("competing_nested_run_roots")
            except OSError:
                status = "REVIEW_REQUIRED"
                integrity.append("competing_nested_run_unreadable")

    return {
        "ok": True,
        "status": status,
        "integrity": integrity,
        "bound_root": str(bound_path),
        "machine": bound.get("machine") or want or None,
        "candidates": candidates,
        "policy": {
            "never_switch_for_nested_run": True,
            "competing_roots_are_review": True,
        },
    }


def normalize_bound_run_dir(
    run_dir: Path | str,
    *,
    machine: str | None = None,
) -> Path:
    """Resolve a caller-supplied run_dir without chasing nested RUN\\RUN."""
    result = bind_evidence_root(run_dir, machine=machine, allow_nested_fallback=False)
    bound = result.get("bound_root")
    if bound:
        return Path(bound)
    path = Path(run_dir)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preferred", type=Path, default=None)
    ap.add_argument("--machine", default="")
    ap.add_argument("--meta-run-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    payload = bind_evidence_root(
        args.preferred,
        machine=args.machine or None,
        meta_run_dir=args.meta_run_dir,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
