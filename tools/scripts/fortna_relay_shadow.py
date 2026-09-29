#!/usr/bin/env python3
"""Relay shadow-mode orchestrator — analysis/review path only.

Flow:
  points → trigger → evidence packet → knowledge bundle → invoke → validate → queue

Never writes production endpoints.
Default: shadow disabled (no API spend on startup / ordinary open).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = SCRIPT_DIR.parents[1]

from fortna_relay_evidence_packet import (  # noqa: E402
    assert_packet_safe,
    build_evidence_packet,
)
from fortna_relay_invoke import invoke_relay  # noqa: E402
from fortna_relay_knowledge_loader import build_relay_context_bundle  # noqa: E402
from fortna_relay_review_queue import group_review_items, make_review_item  # noqa: E402
from fortna_relay_trigger import classify_relay_trigger, select_relay_candidates  # noqa: E402

CACHE_DIR = REPO_ROOT / "exports" / "relay-shadow" / "cache"
AUDIT_DIR = REPO_ROOT / "exports" / "relay-shadow" / "audit"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _git_sha(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (r.stdout or "").strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def shadow_enabled(flag: bool | None = None) -> bool:
    if flag is not None:
        return bool(flag)
    env = (os.environ.get("SITEFORGE_RELAY_SHADOW") or "").strip().lower()
    return env in {"1", "true", "yes", "on"}


def cache_key(
    *,
    site_forge_sha: str,
    knowledge_bundle_hash: str,
    evidence_packet_hash: str,
    agent_version: str,
) -> str:
    return _sha(
        {
            "site_forge_sha": site_forge_sha,
            "knowledge_bundle_hash": knowledge_bundle_hash,
            "evidence_packet_hash": evidence_packet_hash,
            "agent_version": agent_version,
        }
    )


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def read_cache(key: str) -> dict[str, Any] | None:
    p = _cache_path(key)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(key: str, payload: dict[str, Any]) -> None:
    p = _cache_path(key)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_audit(record: dict[str, Any]) -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    rid = record.get("result_hash") or _sha(record)[:16]
    path = AUDIT_DIR / f"audit_{rid}.json"
    # Never persist secrets
    safe = {k: v for k, v in record.items() if "key" not in str(k).lower()}
    path.write_text(json.dumps(safe, indent=2, default=str), encoding="utf-8")
    return path


def run_shadow_case(
    point: dict[str, Any],
    *,
    machine: str,
    repo_root: Path | None = None,
    enabled: bool | None = None,
    context_bundle: dict[str, Any] | None = None,
    packet_kwargs: dict[str, Any] | None = None,
    transport: Callable | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Run one shadow-mode Relay case (or skip if ineligible / disabled)."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    enabled_flag = shadow_enabled(enabled)
    trigger = classify_relay_trigger(point)
    if not trigger.get("eligible"):
        return {
            "ok": True,
            "status": "SKIPPED_NOT_ELIGIBLE",
            "shadow_mode": True,
            "production_authority": False,
            "ai_call": False,
            "endpoint_written": False,
            "trigger": trigger,
            "review_item": None,
        }

    bundle = context_bundle or build_relay_context_bundle(repo_root=root)
    packet = build_evidence_packet(
        point=point,
        machine=machine,
        **(packet_kwargs or {}),
    )
    violations = assert_packet_safe(packet)
    if violations:
        return {
            "ok": False,
            "status": "RELAY_PACKET_UNSAFE",
            "shadow_mode": True,
            "production_authority": False,
            "ai_call": False,
            "endpoint_written": False,
            "violations": violations,
            "trigger": trigger,
        }

    agent_version = str(bundle.get("knowledge_pack_version") or "0")
    sf_sha = _git_sha(root)
    key = cache_key(
        site_forge_sha=sf_sha,
        knowledge_bundle_hash=str(bundle.get("bundle_hash") or ""),
        evidence_packet_hash=str(packet.get("evidence_packet_hash") or ""),
        agent_version=agent_version,
    )

    cached = read_cache(key) if use_cache else None
    if cached and cached.get("ok") is not None:
        cached = {**cached, "cache_hit": True, "ai_call": False}
        return cached

    invocation = invoke_relay(
        packet,
        repo_root=root,
        context_bundle=bundle,
        enabled=enabled_flag,
        transport=transport,
    )
    review = None
    if invocation.get("result") or invocation.get("status") in {
        "RELAY_RESULT_INVALID",
        "RELAY_POLICY_VIOLATION",
        "RELAY_COMPLETE",
    }:
        review = make_review_item(
            deterministic_point=point,
            evidence_packet=packet,
            relay_invocation=invocation,
        )

    out = {
        "ok": bool(invocation.get("ok") or invocation.get("status") == "RELAY_DISABLED"),
        "status": invocation.get("status"),
        "shadow_mode": True,
        "production_authority": False,
        "ai_call": bool(invocation.get("ai_call")),
        "endpoint_written": False,
        "cache_hit": False,
        "trigger": trigger,
        "evidence_packet_hash": packet.get("evidence_packet_hash"),
        "knowledge_bundle_hash": bundle.get("bundle_hash"),
        "site_forge_sha": sf_sha,
        "agent_version": agent_version,
        "invocation": invocation,
        "review_item": review,
        "result_hash": _sha(invocation.get("result") or invocation.get("status")),
        "timestamp": _ts(),
    }
    audit_path = write_audit(
        {
            **{k: out[k] for k in out if k != "invocation"},
            "meta": (invocation.get("meta") or {}),
            "schema_validation_status": (invocation.get("validation") or {}).get("status"),
            "production_authority": False,
        }
    )
    out["audit_path"] = str(audit_path)
    if use_cache and enabled_flag and invocation.get("ai_call"):
        write_cache(key, out)
    return out


def run_shadow_batch(
    points: list[dict[str, Any]],
    *,
    machine: str,
    repo_root: Path | None = None,
    enabled: bool | None = None,
    transport: Callable | None = None,
) -> dict[str, Any]:
    """Select eligible points and run shadow review; return grouped queue."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    bundle = build_relay_context_bundle(repo_root=root)
    candidates = select_relay_candidates(points)
    skipped = len(points) - len(candidates)
    results = []
    reviews = []
    for p in candidates:
        r = run_shadow_case(
            p,
            machine=machine,
            repo_root=root,
            enabled=enabled,
            context_bundle=bundle,
            transport=transport,
        )
        results.append(r)
        if r.get("review_item"):
            reviews.append(r["review_item"])
    groups = group_review_items(reviews)
    return {
        "ok": True,
        "status": "RELAY_COMPLETE" if shadow_enabled(enabled) else "RELAY_DISABLED",
        "shadow_mode": True,
        "production_authority": False,
        "endpoint_written": False,
        "knowledge_status": bundle.get("status"),
        "knowledge_bundle_hash": bundle.get("bundle_hash"),
        "input_count": len(points),
        "eligible_count": len(candidates),
        "skipped_count": skipped,
        "results": results,
        "review_items": reviews,
        "review_groups": groups,
        "timestamp": _ts(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relay shadow-mode runner")
    ap.add_argument("--machine", required=True)
    ap.add_argument("--points-json", type=Path, help="JSON list of deterministic points")
    ap.add_argument("--enable", action="store_true", help="Allow AI invocation")
    ap.add_argument("--repo-root", type=Path, default=None)
    args = ap.parse_args(argv)
    points = []
    if args.points_json and args.points_json.is_file():
        points = json.loads(args.points_json.read_text(encoding="utf-8"))
    out = run_shadow_batch(
        points,
        machine=args.machine,
        repo_root=args.repo_root,
        enabled=args.enable,
    )
    # Strip bulky invocation payloads for CLI
    slim = {**out, "results": [{k: r.get(k) for k in (
        "status", "ai_call", "cache_hit", "trigger", "review_item"
    ) if k in r} for r in out.get("results") or []]}
    # Compact one-line JSON — Electron main.js parses last stdout line.
    print(json.dumps(slim, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
