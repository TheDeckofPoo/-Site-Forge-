#!/usr/bin/env python3
"""Relay durable knowledge loader — read-only startup memory bootstrap.

STARTUP LOAD != AI CALL.

Loads ai/agents/relay/context_manifest.yaml, validates required files, loads in
deterministic order, computes SHA-256 hashes, and builds a context bundle.

Never:
  - calls an AI/API provider
  - opens a network socket
  - mutates knowledge files
  - auto-promotes lessons
  - fetches Google Drive
  - inspects TAR / finished L5X
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

STATUS_READY = "READY"
STATUS_DEGRADED = "DEGRADED"
STATUS_ERROR = "ERROR"

PANEL_LOCAL_MARKERS = (
    "PANEL-LOCAL AUTHORITY",
    "cross-panel",
)


def _repo_root_from_here() -> Path:
    # tools/scripts/fortna_relay_knowledge_loader.py → repo root
    return Path(__file__).resolve().parents[2]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_manifest_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root else _repo_root_from_here()
    return root / "ai" / "agents" / "relay" / "context_manifest.yaml"


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse context_manifest.yaml")
    raw = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a mapping")
    if "load_order" not in data or not isinstance(data["load_order"], list):
        raise ValueError("manifest.load_order must be a list")
    if not data.get("knowledge_pack_version"):
        raise ValueError("manifest.knowledge_pack_version is required")
    if not data.get("agent"):
        raise ValueError("manifest.agent is required")
    return data


def _expand_directory_markdown(
    dir_path: Path,
    *,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Deterministic ASCII-sorted *.md files (exclude list by basename)."""
    if not dir_path.is_dir():
        return []
    excl = {str(x) for x in (exclude or [])}
    files = [
        p
        for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() == ".md" and p.name not in excl
    ]
    return sorted(files, key=lambda p: p.name)


def _resolve_entry(
    ai_root: Path,
    entry: dict[str, Any],
) -> list[tuple[str, Path, dict[str, Any]]]:
    """Return list of (logical_id, path, entry_meta) for one load_order item."""
    rel = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
    kind = str(entry.get("kind") or "file").strip()
    eid = str(entry.get("id") or rel)
    if kind == "directory_markdown":
        paths = _expand_directory_markdown(
            ai_root / rel,
            exclude=list(entry.get("exclude") or []),
        )
        return [(f"{eid}:{p.name}", p, entry) for p in paths]
    return [(eid, ai_root / rel, entry)]


def build_relay_context_bundle(
    *,
    repo_root: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Build the Relay context bundle. Read-only. No network. No AI call."""
    root = Path(repo_root) if repo_root else _repo_root_from_here()
    ai_root = root / "ai"
    mpath = Path(manifest_path) if manifest_path else default_manifest_path(root)

    errors: list[str] = []
    warnings: list[str] = []
    loaded: list[dict[str, Any]] = []
    parts: list[str] = []

    if not mpath.is_file():
        return {
            "ok": False,
            "status": STATUS_ERROR,
            "agent": "relay",
            "knowledge_pack_version": None,
            "manifest_path": str(mpath),
            "errors": [f"manifest missing: {mpath}"],
            "warnings": [],
            "loaded_files": [],
            "loaded_file_count": 0,
            "bundle_hash": None,
            "load_timestamp": _now(),
            "ai_call": False,
            "network": False,
            "context_text": "",
        }

    try:
        manifest = load_manifest(mpath)
    except Exception as exc:
        return {
            "ok": False,
            "status": STATUS_ERROR,
            "agent": "relay",
            "knowledge_pack_version": None,
            "manifest_path": str(mpath),
            "errors": [f"manifest parse/validate failed: {exc}"],
            "warnings": [],
            "loaded_files": [],
            "loaded_file_count": 0,
            "bundle_hash": None,
            "load_timestamp": _now(),
            "ai_call": False,
            "network": False,
            "context_text": "",
        }

    agent = str(manifest.get("agent") or "relay")
    kver = str(manifest.get("knowledge_pack_version") or "")
    panel_local_ok = False

    for entry in manifest.get("load_order") or []:
        if not isinstance(entry, dict):
            errors.append("load_order entry is not a mapping")
            continue
        required = bool(entry.get("required", True))
        resolved = _resolve_entry(ai_root, entry)
        if not resolved:
            rel = str(entry.get("path") or "")
            kind = str(entry.get("kind") or "file")
            target = ai_root / rel.replace("\\", "/").lstrip("/")
            if kind == "directory_markdown":
                # Empty optional lesson dirs are OK (README-only / no lessons yet).
                if not target.is_dir() and required:
                    errors.append(f"missing required directory: {rel}")
                elif not target.is_dir() and not required:
                    warnings.append(f"optional directory missing: {rel}")
                # empty dir / only excluded READMEs → silent OK
                continue
            msg = f"missing path for load entry id={entry.get('id')}: {rel}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)
            continue

        for logical_id, fpath, meta in resolved:
            if not fpath.is_file():
                msg = f"missing file: {fpath.relative_to(root).as_posix()}"
                if required:
                    errors.append(msg)
                else:
                    warnings.append(msg)
                continue
            text = fpath.read_text(encoding="utf-8")
            digest = _sha256_text(text)
            rel = fpath.relative_to(root).as_posix()
            # Panel-local law must not be silently omitted
            markers = list(meta.get("must_include_substrings") or [])
            if markers:
                missing = [m for m in markers if m not in text]
                if missing:
                    errors.append(
                        f"panel-local law incomplete in {rel}: missing {missing}"
                    )
                else:
                    panel_local_ok = True
            elif fpath.name == "PANEL_LOCAL_IO_RULES.md":
                if all(m in text for m in PANEL_LOCAL_MARKERS):
                    panel_local_ok = True
                else:
                    errors.append(f"panel-local law markers missing in {rel}")

            loaded.append(
                {
                    "id": logical_id,
                    "path": rel,
                    "sha256": digest,
                    "bytes": len(text.encode("utf-8")),
                    "required": required,
                }
            )
            parts.append(f"===== {rel} =====\n{text.rstrip()}\n")

    # Optional metadata files (presence only — not required for READY)
    for opt in manifest.get("optional_files") or []:
        op = ai_root / str(opt).replace("\\", "/").lstrip("/")
        # optional_files are relative to ai/
        if not op.is_file():
            # also try repo-relative
            op2 = root / "ai" / str(opt).replace("\\", "/").lstrip("/")
            op = op2 if op2.is_file() else op
        if not op.is_file():
            warnings.append(f"optional file missing: {opt}")

    context_text = "\n".join(parts)
    bundle_hash = _sha256_text(context_text) if loaded else None

    if errors:
        status = STATUS_ERROR
        ok = False
    elif warnings:
        status = STATUS_DEGRADED
        ok = True
    else:
        status = STATUS_READY
        ok = True

    # Hard requirement: panel-local law must be in the bundle when READY/DEGRADED
    if ok and not panel_local_ok:
        errors.append("panel-local I/O law missing from context bundle")
        status = STATUS_ERROR
        ok = False

    return {
        "ok": ok,
        "status": status,
        "agent": agent,
        "knowledge_pack_version": kver,
        "schema_version": str(manifest.get("schema_version") or ""),
        "manifest_path": str(mpath.relative_to(root).as_posix())
        if mpath.is_relative_to(root)
        else str(mpath),
        "errors": errors,
        "warnings": warnings,
        "loaded_files": loaded,
        "loaded_file_count": len(loaded),
        "bundle_hash": bundle_hash,
        "load_timestamp": _now(),
        "ai_call": False,
        "network": False,
        "google_drive": False,
        "mutate_repository": False,
        "panel_local_law_present": panel_local_ok,
        "context_text": context_text,
    }


def status_line(bundle: dict[str, Any]) -> str:
    st = bundle.get("status") or STATUS_ERROR
    ver = bundle.get("knowledge_pack_version") or "?"
    n = bundle.get("loaded_file_count") or 0
    h = bundle.get("bundle_hash") or ""
    short = f"{h[:12]}…" if len(h) > 12 else h
    return f"RELAY KNOWLEDGE: {st} · v{ver} · files={n} · hash={short}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relay knowledge loader (read-only)")
    ap.add_argument("--repo-root", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="Emit full JSON (no context_text)")
    ap.add_argument(
        "--include-context",
        action="store_true",
        help="Include context_text in JSON output",
    )
    args = ap.parse_args(argv)
    bundle = build_relay_context_bundle(
        repo_root=args.repo_root,
        manifest_path=args.manifest,
    )
    if args.json:
        out = dict(bundle)
        if not args.include_context:
            out.pop("context_text", None)
        # Compact one-line JSON — Electron main.js parses last stdout line.
        print(json.dumps(out, separators=(",", ":"), default=str))
    else:
        print(status_line(bundle))
        for e in bundle.get("errors") or []:
            print(f"ERROR: {e}", file=sys.stderr)
        for w in bundle.get("warnings") or []:
            print(f"WARN: {w}", file=sys.stderr)
    return 0 if bundle.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
