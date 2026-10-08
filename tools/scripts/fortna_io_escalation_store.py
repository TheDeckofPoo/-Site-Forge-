#!/usr/bin/env python3
"""Durable I/O escalation snapshot — single source of truth for build + Workbench.

After live pre-build escalation, the canonical device ledger (with escalation_trace
per device) is persisted. The Engineering Review Workbench MUST load this snapshot
instead of rebuilding a blank ledger with not_yet_escalated stubs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

SNAPSHOT_NAME = "io_canonical_escalation_snapshot.json"
TRACE_JSONL = "io_resolution_trace.jsonl"
TRACE_TXT = "IO_RESOLUTION_TRACE.txt"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def default_snapshot_paths(
    *,
    repo: Path | str | None = None,
    diag_dir: Path | str | None = None,
    build_dir: Path | str | None = None,
) -> list[Path]:
    """Ordered search paths for the durable escalation snapshot."""
    root = Path(repo) if repo else REPO_ROOT
    paths: list[Path] = []
    if diag_dir:
        paths.append(Path(diag_dir) / SNAPSHOT_NAME)
    if build_dir:
        paths.append(Path(build_dir) / SNAPSHOT_NAME)
    paths.append(root / "workspace" / "active" / SNAPSHOT_NAME)
    paths.append(root / "workspace" / SNAPSHOT_NAME)
    paths.append(root / "exports" / "current" / SNAPSHOT_NAME)
    return paths


def save_escalation_snapshot(
    canonical: dict[str, Any],
    *,
    machine: str,
    run_dir: Path | str | None = None,
    build_id: str = "",
    diag_dir: Path | str | None = None,
    repo: Path | str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist escalated canonical ledger + write resolution traces.

    Returns {ok, snapshot_path, trace_jsonl, trace_txt, device_count}.
    """
    root = Path(repo) if repo else REPO_ROOT
    targets: list[Path] = []
    if diag_dir:
        targets.append(Path(diag_dir) / SNAPSHOT_NAME)
    # Always mirror into workspace/active for Workbench IPC
    active = root / "workspace" / "active"
    if active.is_dir() or True:
        active.mkdir(parents=True, exist_ok=True)
        targets.append(active / SNAPSHOT_NAME)
    targets.append(root / "workspace" / SNAPSHOT_NAME)

    snap = {
        "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
        "version": 1,
        "saved_at": _ts(),
        "machine": _norm(machine),
        "run_dir": str(run_dir or canonical.get("run_dir") or ""),
        "build_id": _norm(build_id),
        "metrics": {
            "SOURCE_CONSERVATION_PCT": canonical.get("SOURCE_CONSERVATION_PCT"),
            "PHYSICAL_DEVICE_RESOLUTION_PCT": canonical.get(
                "PHYSICAL_DEVICE_RESOLUTION_PCT"
            )
            or canonical.get("device_resolution_coverage_pct"),
            "GENERATED_PHYSICAL_IO_PCT": canonical.get("GENERATED_PHYSICAL_IO_PCT")
            or canonical.get("generated_io_coverage_pct"),
            "unique_physical_devices": canonical.get("unique_physical_devices"),
            "unique_mapped": canonical.get("unique_mapped"),
            "unique_review": canonical.get("unique_review"),
            "unique_unsupported": canonical.get("unique_unsupported"),
            "unique_spare": canonical.get("unique_spare"),
            "proven_physical_spares": canonical.get("proven_physical_spares"),
            "unique_foreign": canonical.get("unique_foreign"),
            "critical_unresolved_count": canonical.get("critical_unresolved_count"),
            "engineering_resolution_ok": canonical.get("engineering_resolution_ok"),
            "source_conservation_ok": canonical.get("source_conservation_ok"),
        },
        "prebuild_escalation": canonical.get("prebuild_escalation"),
        "critical_items_bypassing_escalation": canonical.get(
            "critical_items_bypassing_escalation"
        ),
        "devices": canonical.get("devices") or [],
        "safety": canonical.get("safety"),
        "pushbuttons": canonical.get("pushbuttons"),
        "active_configio_words": canonical.get("active_configio_words"),
        "extra": extra or {},
    }

    written: list[str] = []
    primary: Path | None = None
    blob = json.dumps(snap, indent=2, default=str)
    for p in targets:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(blob, encoding="utf-8")
            written.append(str(p))
            if primary is None:
                primary = p
        except Exception:
            continue

    trace_paths = write_resolution_traces(
        snap,
        diag_dir=diag_dir,
        repo=root,
        build_id=build_id,
        machine=machine,
    )
    return {
        "ok": bool(primary),
        "snapshot_path": str(primary) if primary else "",
        "written": written,
        "device_count": len(snap["devices"]),
        "metrics": snap["metrics"],
        **trace_paths,
    }


def load_escalation_snapshot(
    *,
    machine: str = "",
    run_dir: Path | str | None = None,
    diag_dir: Path | str | None = None,
    build_dir: Path | str | None = None,
    repo: Path | str | None = None,
    max_age_hours: float | None = None,
) -> dict[str, Any] | None:
    """Load newest matching escalation snapshot, or None."""
    mach = _norm(machine).upper()
    for p in default_snapshot_paths(repo=repo, diag_dir=diag_dir, build_dir=build_dir):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("ori") not in {
            "IO_CANONICAL_ESCALATION_SNAPSHOT",
            "CANONICAL_PHYSICAL_DEVICE_LEDGER",
        } and "devices" not in data:
            continue
        snap_mach = _norm(data.get("machine")).upper()
        if mach and snap_mach and snap_mach != mach:
            continue
        data["_loaded_from"] = str(p)
        return data
    return None


def apply_snapshot_to_canonical(
    canonical: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Merge durable escalation traces/status/metrics onto a freshly built canonical.

    Snapshot is authoritative for escalation_trace, final_status (when escalated),
    and metrics. Fresh ledger remains source for newly discovered devices.
    """
    snap_devices = {
        _norm(d.get("canonical_name")).upper(): d
        for d in (snapshot.get("devices") or [])
        if _norm(d.get("canonical_name"))
    }
    merged = 0
    for d in canonical.get("devices") or []:
        key = _norm(d.get("canonical_name")).upper()
        src = snap_devices.get(key)
        if not src:
            continue
        # Prefer snapshot escalation state
        if src.get("escalation_trace"):
            d["escalation_trace"] = src.get("escalation_trace")
        if src.get("final_status"):
            d["final_status"] = src.get("final_status")
        if src.get("ownership"):
            d["ownership"] = src.get("ownership")
        if src.get("reason"):
            d["reason"] = src.get("reason")
        if src.get("confidence"):
            d["confidence"] = src.get("confidence")
        if src.get("physical_endpoint") and not d.get("physical_endpoint"):
            d["physical_endpoint"] = src.get("physical_endpoint")
        if src.get("engineer_confirmation"):
            d["engineer_confirmation"] = src.get("engineer_confirmation")
        if src.get("assignable") is not None:
            d["assignable"] = src.get("assignable")
        merged += 1

    # Carry metrics from snapshot (build truth)
    metrics = snapshot.get("metrics") or {}
    for k, v in metrics.items():
        if v is not None:
            canonical[k] = v
    if snapshot.get("prebuild_escalation") is not None:
        canonical["prebuild_escalation"] = snapshot.get("prebuild_escalation")
    if snapshot.get("critical_items_bypassing_escalation") is not None:
        canonical["critical_items_bypassing_escalation"] = snapshot.get(
            "critical_items_bypassing_escalation"
        )
    canonical["escalation_snapshot_loaded_from"] = snapshot.get("_loaded_from")
    canonical["escalation_snapshot_merged_devices"] = merged
    # Keep device_resolution alias in sync
    if canonical.get("PHYSICAL_DEVICE_RESOLUTION_PCT") is not None:
        canonical["device_resolution_coverage_pct"] = canonical[
            "PHYSICAL_DEVICE_RESOLUTION_PCT"
        ]
    if canonical.get("GENERATED_PHYSICAL_IO_PCT") is not None:
        canonical["generated_io_coverage_pct"] = canonical["GENERATED_PHYSICAL_IO_PCT"]
    return {
        "merged": merged,
        "loaded_from": snapshot.get("_loaded_from"),
        "metrics": metrics,
    }


def write_resolution_traces(
    snapshot: dict[str, Any],
    *,
    diag_dir: Path | str | None = None,
    repo: Path | str | None = None,
    build_id: str = "",
    machine: str = "",
) -> dict[str, str]:
    """Write io_resolution_trace.jsonl + IO_RESOLUTION_TRACE.txt (no secrets)."""
    root = Path(repo) if repo else REPO_ROOT
    out_dirs: list[Path] = []
    if diag_dir:
        out_dirs.append(Path(diag_dir))
    out_dirs.append(root / "workspace" / "active")
    out_dirs.append(root / "exports" / "current")

    build = _norm(build_id) or _norm(snapshot.get("build_id")) or "unknown"
    mach = _norm(machine) or _norm(snapshot.get("machine"))
    lines_jsonl: list[str] = []
    lines_txt: list[str] = [
        f"IO_RESOLUTION_TRACE build_id={build} machine={mach} saved_at={snapshot.get('saved_at')}",
        "=" * 78,
    ]

    for d in snapshot.get("devices") or []:
        name = _norm(d.get("canonical_name"))
        if not name:
            continue
        trace = d.get("escalation_trace") or {}
        # Skip pure blank stubs unless critical/review/unsupported
        st = _norm(d.get("final_status")).split(":")[0]
        interesting = st in {
            "REVIEW_REQUIRED",
            "ENGINEER_CONFIRM_REQUIRED",
            "UNSUPPORTED",
            "ENGINEER_CONFIRMED",
            "MAPPED",
            "FOREIGN_CONTROLLER",
        } or bool(trace.get("ai_api_called") not in (False, "NO", None, "")) or bool(
            d.get("critical")
        )
        if not interesting and not trace:
            continue

        # Redact any accidental key-like fields
        safe_trace = {
            k: v
            for k, v in trace.items()
            if "api_key" not in k.lower()
            and "authorization" not in k.lower()
            and "secret" not in k.lower()
            and "token" not in k.lower()
        }
        row = {
            "build_id": build,
            "site": mach,
            "controller": _norm(d.get("controller")) or mach,
            "device": name,
            "device_type": d.get("device_type"),
            "cluster_id": safe_trace.get("cluster_id"),
            "source_evidence": d.get("source_evidence") or [],
            "deterministic_result": safe_trace.get("deterministic_result")
            or safe_trace.get("deterministic_attempt")
            or {
                "code": d.get("deterministic_code"),
                "ownership": d.get("ownership"),
                "reason": d.get("reason"),
            },
            "ai_api_called": safe_trace.get("ai_api_called"),
            "ai_result": _summarize_ai(safe_trace.get("ai_result")),
            "ai_validation": safe_trace.get("ai_validation"),
            "relay_called": safe_trace.get("relay_called"),
            "relay_result": _summarize_relay(safe_trace.get("relay_result")),
            "relay_validation": safe_trace.get("relay_validation"),
            "final_disposition": d.get("final_status")
            or safe_trace.get("final_classification"),
            "engineer_confirm_state": {
                "required": safe_trace.get("engineer_confirmation_required"),
                "confirmation": d.get("engineer_confirmation"),
                "decision": safe_trace.get("engineer_decision"),
            },
            "why_ai_not_called": safe_trace.get("why_ai_not_called"),
            "why_relay_not_called": safe_trace.get("why_relay_not_called"),
            "non_escalatable_reason": safe_trace.get("non_escalatable_reason"),
            "knowledge_base_evidence": safe_trace.get("knowledge_base_evidence"),
        }
        lines_jsonl.append(json.dumps(row, default=str))
        lines_txt.append(
            f"[{name}] type={d.get('device_type')} status={d.get('final_status')} "
            f"cluster={safe_trace.get('cluster_id') or '—'} "
            f"AI={safe_trace.get('ai_api_called')} Relay={safe_trace.get('relay_called')} "
            f"det={d.get('deterministic_code') or (safe_trace.get('deterministic_result') or {}).get('code')}"
        )
        if safe_trace.get("non_escalatable_reason"):
            lines_txt.append(f"  NON_ESCALATABLE: {safe_trace.get('non_escalatable_reason')}")
        if safe_trace.get("why_ai_not_called"):
            lines_txt.append(f"  why_ai_not_called: {safe_trace.get('why_ai_not_called')}")
        if d.get("reason"):
            lines_txt.append(f"  reason: {d.get('reason')}")

    metrics = snapshot.get("metrics") or {}
    lines_txt.append("=" * 78)
    lines_txt.append(
        "METRICS: "
        + ", ".join(f"{k}={v}" for k, v in metrics.items() if v is not None)
    )
    esc = snapshot.get("prebuild_escalation") or {}
    if esc:
        lines_txt.append(
            "ESCALATION: "
            f"candidates={esc.get('candidates')} clusters={esc.get('clusters_formed')} "
            f"ai_calls={esc.get('ai_calls')} ai_resolved={esc.get('ai_resolved')} "
            f"relay_calls={esc.get('relay_calls')} relay_resolved={esc.get('relay_resolved')} "
            f"engineer_confirm_required={esc.get('engineer_confirm_required')} "
            f"critical_bypass={snapshot.get('critical_items_bypassing_escalation')}"
        )

    written = {"trace_jsonl": "", "trace_txt": ""}
    payload_jsonl = "\n".join(lines_jsonl) + ("\n" if lines_jsonl else "")
    payload_txt = "\n".join(lines_txt) + "\n"
    for d in out_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            jp = d / TRACE_JSONL
            tp = d / TRACE_TXT
            jp.write_text(payload_jsonl, encoding="utf-8")
            tp.write_text(payload_txt, encoding="utf-8")
            if not written["trace_jsonl"]:
                written["trace_jsonl"] = str(jp)
                written["trace_txt"] = str(tp)
        except Exception:
            continue
    return written


def _summarize_ai(ai_result: Any) -> Any:
    if not isinstance(ai_result, dict):
        return ai_result
    # Keep classification/confidence/reason; drop bulky raw payloads if huge
    out = {
        k: ai_result.get(k)
        for k in (
            "ok",
            "classification",
            "confidence",
            "reason",
            "recommended_action",
            "candidate_resolution",
            "response",
        )
        if k in ai_result
    }
    return out or ai_result


def _summarize_relay(relay_result: Any) -> Any:
    if not isinstance(relay_result, dict):
        return relay_result
    out = {
        k: relay_result.get(k)
        for k in (
            "ok",
            "classification",
            "confidence",
            "reason",
            "recommended_action",
            "text",
            "response",
        )
        if k in relay_result
    }
    # Truncate freeform text
    if isinstance(out.get("text"), str) and len(out["text"]) > 2000:
        out["text"] = out["text"][:2000] + "…"
    return out or relay_result
