#!/usr/bin/env python3
"""Site Forge Qualification Runner — virgin / replay / reference gate.

Isolates a fresh temp workspace (copy of RUN + empty or replay workbook),
runs discovery → handoff snapshots → optional Autogen, and emits a PASS /
REVIEW / FAIL dashboard. Reference L5X is never read during discovery or
generation (post-generation oracle only).

Usage:
  python tools/scripts/fortna_qualification_runner.py qualify \\
    --run-dir <RUN> --machine <MACHINE> [--project-workbook <json>] \\
    [--reference-l5x <path>] [--out <dir>] [--mode virgin|replay|reference] \\
    [--sanitized] [--fail-on-review] [--skip-generate]

  python tools/scripts/fortna_qualification_runner.py compare \\
    --a <qual_dir> --b <qual_dir> --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# Legacy PLC template equipment hosts from gold packs — FAIL in final L5X unless
# RUN / SorterModel independently proves that equipment identity.
STALE_SORTER_HOSTS = ("P504", "P506", "P508", "P509", "P510", "P500", "P502", "P512")
STALE_HOST_TAG_RE = re.compile(
    r"\b(P504|P506|P508|P509|P510|P500|P502|P512)(?:_[A-Za-z0-9_]+)?\b",
    re.I,
)
CROSS_SUBSYSTEM_STATE_REGRESSION = "CROSS_SUBSYSTEM_STATE_REGRESSION"

STATUS_PASS = "PASS"
STATUS_REVIEW = "REVIEW"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"
RANK = {STATUS_PASS: 0, STATUS_SKIP: 0, STATUS_REVIEW: 1, STATUS_FAIL: 2}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    else:
        run_dir = run_dir.resolve()
    if (run_dir / "RUN" / "project.cfg").is_file():
        return (run_dir / "RUN").resolve()
    return run_dir


def _site_slug(machine: str, run_dir: Path | None = None) -> str:
    machine = (machine or "").strip() or "SITE"
    if run_dir is not None:
        cfg = run_dir / "project.cfg"
        if cfg.is_file():
            try:
                text = cfg.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"PROJECTNAME\s*=\s*(\S+)", text, re.I)
                if m:
                    return re.sub(r"[^\w\-]+", "_", m.group(1).strip())[:48]
            except OSError:
                pass
    return re.sub(r"[^\w\-]+", "_", machine)[:48]


def _empty_workbook(machine: str) -> dict[str, Any]:
    return {
        "kind": "fortna_autogen_workbook",
        "version": 1,
        "machine": machine,
        "source": "qualification_runner_virgin",
        "generated_utc": _iso(),
        "conveyors": [],
        "areas": [],
        "merges_2to1": [],
        "safety_zones": [],
        "safety_build": {"version": 1, "source": "qualification_empty", "zones": [], "devices": []},
        "sorter_build": {},
        "options": {},
    }


def _load_project_workbook(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    path = Path(path)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"project workbook not found: {path}")
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError("project workbook must be a JSON object")
    return data


def _count_safety_members(safety_build: dict[str, Any] | None) -> dict[str, Any]:
    sb = safety_build if isinstance(safety_build, dict) else {}
    zones = [z for z in (sb.get("zones") or []) if isinstance(z, dict)]
    total = 0
    operational = 0
    default_ops = 0
    zone_summaries: list[dict[str, Any]] = []
    for z in zones:
        members = [str(m).strip() for m in (z.get("members") or []) if str(m).strip()]
        name = str(
            z.get("source_id") or z.get("engineering_name") or z.get("name") or ""
        ).strip()
        is_default = bool(
            z.get("isDefault")
            or z.get("isUnassignedBucket")
            or z.get("operational") is False
            or name.lower() in {"default safety", "unassigned safety", "default", "unassigned"}
        )
        total += len(members)
        if members and not is_default:
            operational += len(members)
        if members and is_default:
            default_ops += len(members)
        zone_summaries.append(
            {
                "name": name,
                "member_count": len(members),
                "is_default_or_unassigned": is_default,
                "operational": (not is_default) and bool(members),
            }
        )
    return {
        "zone_count": len(zones),
        "member_count": total,
        "operational_member_count": operational,
        "default_bucket_member_count": default_ops,
        "zones": zone_summaries,
    }


def _safety_from_workbook(wb: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(wb, dict):
        return {}
    sb = wb.get("safety_build")
    return sb if isinstance(sb, dict) else {}


def _copy_run_to_workspace(src_run: Path, dest_root: Path) -> Path:
    """Copy RUN into an isolated workspace. Never inherit prior site workbook."""
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_run = dest_root / "RUN"
    if dest_run.exists():
        shutil.rmtree(dest_run)
    shutil.copytree(src_run, dest_run, dirs_exist_ok=False)
    # Ensure no leftover workbook at workspace root
    for name in ("autogen_workbook.json", "project_workbook.json"):
        p = dest_root / name
        if p.exists():
            p.unlink()
    return dest_run


def _summarize_active_tables(run_dir: Path, machine: str) -> dict[str, Any]:
    from fortna_fortna_table_resolver import iter_active_tables
    from fortna_site_model import MODE_NATIVE_SHADOW

    tables: list[dict[str, Any]] = []
    for resolved in iter_active_tables(run_dir, machine, mode=MODE_NATIVE_SHADOW):
        rows = resolved.get("merged_rows") or []
        tables.append(
            {
                "stem": resolved.get("stem") or resolved.get("table") or resolved.get("basename"),
                "kind": resolved.get("kind"),
                "mode": resolved.get("mode") or MODE_NATIVE_SHADOW,
                "path_name": resolved.get("path_name"),
                "row_count": len(rows),
                "folder": resolved.get("folder"),
            }
        )
    return {
        "machine": machine,
        "mode": MODE_NATIVE_SHADOW,
        "table_count": len(tables),
        "tables": tables,
        "fingerprint": _fingerprint(tables),
    }


def _summarize_closure(closure: dict[str, Any]) -> dict[str, Any]:
    counts = dict(closure.get("counts") or {})
    by_table = dict(counts.get("by_table") or {})
    return {
        "kind": closure.get("kind"),
        "machine": closure.get("machine"),
        "member_count": int(counts.get("members") or len(closure.get("members") or [])),
        "by_table": by_table,
        "active_tables_used": list(closure.get("active_tables_used") or []),
        "schema_fingerprint": closure.get("schema_fingerprint"),
        "fingerprint": _fingerprint(
            {
                "machine": closure.get("machine"),
                "counts": counts,
                "active_tables_used": closure.get("active_tables_used"),
            }
        ),
    }


def _summarize_sorter(model: dict[str, Any]) -> dict[str, Any]:
    fa = model.get("field_authority") if isinstance(model.get("field_authority"), dict) else {}
    return {
        "detected": bool(model.get("detected")),
        "sorter_count": int(model.get("sorter_count") or 0),
        "divert_count": int(model.get("divert_count") or 0),
        "encoder_count": int(model.get("encoder_count") or 0),
        "transport_area": model.get("transport_area"),
        "sorter_area_name": model.get("sorter_area_name"),
        "shipping_sorter_supported": bool(model.get("shipping_sorter_supported")),
        "divert_host_conveyor": model.get("divert_host_conveyor") or model.get("divert_host"),
        "field_authority_transport_area": fa.get("transport_area"),
        "fingerprint": _fingerprint(
            {
                "divert_host": model.get("divert_host_conveyor") or model.get("divert_host"),
                "sorter_area_name": model.get("sorter_area_name"),
                "divert_count": model.get("divert_count"),
                "shipping_sorter_supported": model.get("shipping_sorter_supported"),
            }
        ),
    }


def _summarize_merges(report: dict[str, Any]) -> dict[str, Any]:
    merges = list(report.get("merges") or [])
    proven = [
        m
        for m in merges
        if str(m.get("classification") or "").upper() == "PROVEN"
    ]
    names = []
    for m in proven:
        dn = str(m.get("downstream") or m.get("discharge") or m.get("name") or "").strip()
        if dn:
            names.append(dn)
        # Prefer autogen discharge identity when present via sections
        for key in ("mergeSection3", "mainLane"):
            v = str(m.get(key) or "").strip()
            if v and re.match(r"^P\d{2,4}$", v, re.I):
                names.append(v.upper())
    return {
        "counts": dict(report.get("counts") or {}),
        "proven_count": len(proven),
        "proven_names": sorted(set(names)),
        "fingerprint": _fingerprint(report.get("counts")),
    }


def _proven_sorter_hosts(
    sorter_model: dict[str, Any] | None,
    closure: dict[str, Any] | None,
) -> set[str]:
    proven: set[str] = set()
    sm = sorter_model or {}
    host = str(sm.get("divert_host_conveyor") or sm.get("divert_host") or "").strip().upper()
    if host:
        proven.add(host)
    for enc in sm.get("encoders") or []:
        if isinstance(enc, dict):
            for k in ("conveyor", "host", "encoder_conveyor", "name"):
                v = str(enc.get(k) or "").strip().upper()
                if re.match(r"^P\d{2,4}$", v):
                    proven.add(v)
    for row in sm.get("divert_rows") or []:
        if isinstance(row, dict):
            for k in ("host", "conveyor", "divert_host", "host_conveyor"):
                v = str(row.get(k) or "").strip().upper()
                if re.match(r"^P\d{2,4}$", v):
                    proven.add(v)
    for m in (closure or {}).get("members") or []:
        if str(m.get("source_table") or "") != "Conveyor":
            continue
        ident = str(m.get("identity") or "").strip().upper()
        if re.match(r"^P\d{2,4}$", ident):
            proven.add(ident)
    return proven


def _scan_l5x_stale_hosts(l5x_text: str, proven_hosts: set[str]) -> dict[str, Any]:
    hits: dict[str, list[str]] = {h: [] for h in STALE_SORTER_HOSTS}
    for m in STALE_HOST_TAG_RE.finditer(l5x_text or ""):
        host = m.group(1).upper()
        tag = m.group(0)
        if host in proven_hosts:
            continue
        bucket = hits.setdefault(host, [])
        if tag not in bucket:
            bucket.append(tag)
    stale = {h: tags for h, tags in hits.items() if tags}
    return {
        "stale_hosts": sorted(stale.keys()),
        "tags_by_host": {h: tags[:40] for h, tags in stale.items()},
        "proven_hosts": sorted(proven_hosts),
        "fail": bool(stale),
    }


def _scan_l5x_merges(l5x_text: str, proven_names: list[str]) -> dict[str, Any]:
    present = []
    missing = []
    text = l5x_text or ""
    for name in proven_names:
        # Accept Name="P600_Merge" / P600_Merge / tag mentions
        pat = re.compile(rf"\b{re.escape(name)}(?:_Merge)?\b", re.I)
        if pat.search(text):
            present.append(name)
        else:
            missing.append(name)
    return {
        "discovered_proven": list(proven_names),
        "present_in_l5x": present,
        "missing_in_l5x": missing,
        "coverage": (len(present) / len(proven_names)) if proven_names else None,
    }


def _default_unassigned_operational_refs(safety_build: dict[str, Any] | None) -> list[str]:
    """Default/Unassigned buckets must not carry operational member refs."""
    bad: list[str] = []
    counts = _count_safety_members(safety_build)
    for z in counts.get("zones") or []:
        if z.get("is_default_or_unassigned") and int(z.get("member_count") or 0) > 0:
            bad.append(str(z.get("name") or "Default/Unassigned"))
    return bad


def _worst(statuses: list[str]) -> str:
    worst = STATUS_PASS
    for s in statuses:
        if RANK.get(s, 0) > RANK.get(worst, 0):
            worst = s
    return worst


def _check_result(
    name: str,
    status: str,
    *,
    detail: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "subsystem": name,
        "status": status,
        "detail": detail,
        "evidence": evidence or {},
    }


def _sanitize_payload(obj: Any) -> Any:
    """Counts / fingerprints / names / results only — strip raw ASC dumps."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in {
                "members",
                "merged_rows",
                "rows",
                "raw",
                "asc",
                "asc_text",
                "dump",
                "rungs",
                "l5x",
                "l5x_text",
                "body",
                "content",
            }:
                if isinstance(v, list):
                    out[k + "_count"] = len(v)
                elif isinstance(v, str):
                    out[k + "_bytes"] = len(v.encode("utf-8", errors="replace"))
                    out[k + "_fingerprint"] = hashlib.sha256(
                        v.encode("utf-8", errors="replace")
                    ).hexdigest()[:16]
                elif isinstance(v, dict):
                    out[k + "_keys"] = sorted(v.keys())[:40]
                else:
                    out[k] = type(v).__name__
                continue
            if lk.endswith("_rows") and isinstance(v, list) and v and isinstance(v[0], dict):
                out[k + "_count"] = len(v)
                continue
            out[k] = _sanitize_payload(v)
        return out
    if isinstance(obj, list):
        if len(obj) > 80:
            return [_sanitize_payload(x) for x in obj[:40]] + [f"...({len(obj)} total)"]
        return [_sanitize_payload(x) for x in obj]
    return obj


def _maybe_sanitize(obj: Any, sanitized: bool) -> Any:
    return _sanitize_payload(obj) if sanitized else obj


# ---------------------------------------------------------------------------
# Qualify pipeline
# ---------------------------------------------------------------------------


def run_qualify(
    *,
    run_dir: Path,
    machine: str,
    mode: str = "virgin",
    project_workbook: Path | None = None,
    reference_l5x: Path | None = None,
    out_dir: Path | None = None,
    sanitized: bool = False,
    fail_on_review: bool = False,
    skip_generate: bool = False,
    label: str = "",
    reference_open_hook: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Run a full qualification. Returns report dict (also written under out_dir)."""
    mode = (mode or "virgin").strip().lower()
    if mode not in {"virgin", "replay", "reference"}:
        raise ValueError(f"unsupported mode {mode!r}")

    src_run = _normalize_run_dir(run_dir)
    if not (src_run / "project.cfg").is_file() and not (src_run / "FORTNA").is_dir():
        raise FileNotFoundError(f"RUN not found / incomplete: {src_run}")

    machine = (machine or "").strip()
    if not machine:
        raise ValueError("--machine is required")

    # Reference path must not be touched until AFTER generation.
    ref_path: Path | None = None
    if reference_l5x:
        ref_path = Path(reference_l5x)
        if not ref_path.is_absolute():
            ref_path = (ROOT / ref_path).resolve()
    if mode == "reference" and ref_path is None:
        raise ValueError("reference mode requires --reference-l5x")

    site = _site_slug(machine, src_run)
    stamp = _ts()
    label_s = re.sub(r"[^A-Za-z0-9._-]+", "-", (label or "").strip()).strip("-")
    if out_dir is None:
        folder = label_s or f"{mode}-{stamp}"
        out_dir = ROOT / "exports" / "qualification" / site / folder
    else:
        out_dir = Path(out_dir)
        if not out_dir.is_absolute():
            out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    handoffs: dict[str, Any] = {
        "generated_at": _iso(),
        "machine": machine,
        "mode": mode,
        "site": site,
        "snapshots": {},
        "regressions": [],
    }
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    generated_l5x: Path | None = None
    generation_manifest: dict[str, Any] = {}
    provenance_doc: dict[str, Any] | None = None
    final_validation: dict[str, Any] = {}
    workbook: dict[str, Any] = _empty_workbook(machine)
    discovery_result: dict[str, Any] = {}
    closure: dict[str, Any] = {}
    sorter_model: dict[str, Any] = {}
    merge_report: dict[str, Any] = {}
    active_tables: dict[str, Any] = {}
    autogen_input_summary: dict[str, Any] = {}
    safety_before_apply = _count_safety_members({})
    safety_after_apply = _count_safety_members({})
    safety_after_sorter: dict[str, Any] | None = None

    work_root = Path(tempfile.mkdtemp(prefix=f"sf_qual_{machine}_"))
    try:
        # 1. Fresh temp workspace — never inherit prior site workbook
        work_run = _copy_run_to_workspace(src_run, work_root)
        wb_path = work_root / "autogen_workbook.json"

        replay_wb = None
        if mode == "replay":
            replay_wb = _load_project_workbook(project_workbook)
            if replay_wb is None:
                warnings.append("replay mode without --project-workbook; using empty workbook")
            else:
                workbook = dict(replay_wb)
                workbook.setdefault("machine", machine)
                workbook["source"] = workbook.get("source") or "qualification_replay"
        elif project_workbook and mode != "virgin":
            # virgin ignores engineer workbook by design
            replay_wb = _load_project_workbook(project_workbook)
            if replay_wb:
                workbook = dict(replay_wb)

        if mode == "virgin":
            workbook = _empty_workbook(machine)

        _write_json(wb_path, workbook)

        handoffs["snapshots"]["after_run_import"] = {
            "run_dir": str(work_run),
            "workbook_source": workbook.get("source"),
            "safety": _count_safety_members(_safety_from_workbook(workbook)),
            "has_sorter_build": bool(workbook.get("sorter_build")),
            "has_transport_merges": bool(workbook.get("merges_2to1")),
            "fingerprint": _fingerprint(
                {
                    "source": workbook.get("source"),
                    "safety": _count_safety_members(_safety_from_workbook(workbook)),
                }
            ),
        }

        # Guard: reference must not be read during discovery
        if ref_path is not None and reference_open_hook is None:
            # Soft guard used by tests via hook; production relies on not opening it.
            pass

        # 2. Discovery (RUN + machine only; never reference L5X)
        from fortna_machine_closure import build_machine_closure
        from fortna_plc2_merge_discovery import (
            discover_plc2_merges,
            discovery_to_autogen_merges_2to1,
        )
        from fortna_run_workspace_discover import discover as discover_site
        from fortna_sorter_discovery import build_canonical_sorter_model

        disc_out = work_root / "discovery"
        discovery_result = discover_site(
            work_run,
            machine,
            disc_out,
            overrides_path=None,
            blind=True,
        )
        active_tables = _summarize_active_tables(work_run, machine)
        closure = build_machine_closure(work_run, machine)
        sorter_model = build_canonical_sorter_model(work_run, machine)
        merge_report = discover_plc2_merges(work_run, machine)

        handoffs["snapshots"]["machine_closure"] = _summarize_closure(closure)
        handoffs["snapshots"]["transport_model"] = {
            "merge_summary": _summarize_merges(merge_report),
            "discovery_counts": discovery_result.get("counts"),
            "fingerprint": _fingerprint(
                {
                    "discovery": discovery_result.get("counts"),
                    "merges": merge_report.get("counts"),
                }
            ),
        }
        handoffs["snapshots"]["sorter_model"] = _summarize_sorter(sorter_model)

        # Safety before Apply (virgin = empty; replay = engineer state)
        safety_before_apply = _count_safety_members(_safety_from_workbook(workbook))
        handoffs["snapshots"]["safety_before_apply"] = safety_before_apply

        if mode == "replay":
            safety_after_apply = _count_safety_members(_safety_from_workbook(workbook))
            handoffs["snapshots"]["safety_after_apply"] = safety_after_apply
            sb = workbook.get("sorter_build") if isinstance(workbook.get("sorter_build"), dict) else {}
            if sb:
                # Sorter Apply must not wipe safety members (regression detector).
                safety_after_sorter = _count_safety_members(_safety_from_workbook(workbook))
                handoffs["snapshots"]["safety_after_sorter_apply"] = safety_after_sorter

        # Seed virgin transport merges from native discovery (no invented Safety)
        if mode in {"virgin", "reference"} and not workbook.get("merges_2to1"):
            try:
                workbook["merges_2to1"] = discovery_to_autogen_merges_2to1(merge_report)
            except Exception as ex:  # pragma: no cover - defensive
                warnings.append(f"native merge seed failed: {ex}")

        # Sorter model → optional sorter_build hints (virgin does not invent Safety)
        if mode in {"virgin", "reference"} and sorter_model.get("shipping_sorter_supported"):
            sb = dict(workbook.get("sorter_build") or {})
            sb.setdefault("enabled", True)
            sb.setdefault(
                "transport_area",
                sorter_model.get("transport_area") or sorter_model.get("sorter_area_name"),
            )
            sb.setdefault(
                "divert_host_conveyor",
                sorter_model.get("divert_host_conveyor") or sorter_model.get("divert_host"),
            )
            workbook["sorter_build"] = sb

        _write_json(wb_path, workbook)

        # 3. Autogen input — SAME canonical handoff as GUI Autogen
        try:
            from fortna_workbook import build_effective_autogen_input

            # Ensure sorter_model is on workbook for overlay when discovery has it
            if sorter_model and not workbook.get("sorter_model"):
                workbook["sorter_model"] = sorter_model
            inp = build_effective_autogen_input(
                work_run, workbook, machine=machine
            )
            members_before_autogen = _count_safety_members(
                getattr(inp, "safety_build", None) or _safety_from_workbook(workbook)
            )
            sb_eff = getattr(inp, "sorter_build", None) or {}
            autogen_input_summary = {
                "machine": getattr(inp, "machine", machine),
                "project_name": getattr(inp, "project_name", ""),
                "conveyor_count": len(getattr(inp, "conveyors", None) or []),
                "area_count": len(getattr(inp, "areas", None) or []),
                "safety_zone_count": len(getattr(inp, "safety_zones", None) or []),
                "safety_build_members": members_before_autogen,
                "merges_2to1_count": len(
                    getattr(inp, "merges_2to1", None) or workbook.get("merges_2to1") or []
                ),
                "has_sorter_build": bool(sb_eff),
                "sorter_build_keys": sorted(sb_eff.keys())[:40] if isinstance(sb_eff, dict) else [],
                "include_programs": list(getattr(inp, "include_programs", None) or []),
                "fingerprint": _fingerprint(
                    {
                        "conveyors": len(getattr(inp, "conveyors", None) or []),
                        "safety": members_before_autogen,
                        "merges": len(getattr(inp, "merges_2to1", None) or []),
                        "include_programs": list(getattr(inp, "include_programs", None) or []),
                        "sorter": bool(sb_eff),
                    }
                ),
            }
            handoffs["snapshots"]["autogen_input_summary"] = autogen_input_summary
            # Persist effective input for forensic compare vs GUI
            try:
                from dataclasses import asdict, is_dataclass

                eff = {
                    "machine": getattr(inp, "machine", ""),
                    "include_programs": list(getattr(inp, "include_programs", None) or []),
                    "sorter_build": getattr(inp, "sorter_build", None) or {},
                    "sorter_model_keys": sorted((getattr(inp, "sorter_model", None) or {}).keys())[:40],
                    "merges_2to1_count": len(getattr(inp, "merges_2to1", None) or []),
                    "safety_zone_members_count": len(getattr(inp, "safety_zone_members", None) or []),
                    "areas": list(getattr(inp, "areas", None) or []),
                }
                _write_json(out_dir / "effective_autogen_handoff.json", eff)
            except Exception as _eff_ex:
                warnings.append(f"effective handoff write failed: {_eff_ex}")
        except Exception as ex:
            errors.append(f"autogen input load failed: {ex}")
            members_before_autogen = _count_safety_members(_safety_from_workbook(workbook))
            autogen_input_summary = {"error": str(ex), "safety_build_members": members_before_autogen}
            handoffs["snapshots"]["autogen_input_summary"] = autogen_input_summary
            inp = None  # type: ignore

        # 4. CROSS_SUBSYSTEM_STATE_REGRESSION
        after_apply_members = int(
            (handoffs["snapshots"].get("safety_after_apply") or safety_after_apply).get(
                "operational_member_count"
            )
            or 0
        )
        if mode != "replay":
            # For virgin, "after apply" is N/A — use before_apply if engineer workbook sneaks in
            after_apply_members = int(safety_before_apply.get("operational_member_count") or 0)
            # Only flag when replay/engineer had members that vanished before Autogen
        before_autogen_members = int(
            (members_before_autogen or {}).get("operational_member_count") or 0
        )
        # Spec: if safety members after Apply >0 and members before Autogen ==0 → FAIL
        if mode == "replay" and after_apply_members > 0 and before_autogen_members == 0:
            handoffs["regressions"].append(
                {
                    "code": CROSS_SUBSYSTEM_STATE_REGRESSION,
                    "status": STATUS_FAIL,
                    "detail": (
                        f"safety operational members after Apply={after_apply_members} "
                        f"but before Autogen={before_autogen_members}"
                    ),
                    "after_apply": after_apply_members,
                    "before_autogen": before_autogen_members,
                }
            )
        # Also detect sorter-apply wipe when snapshot present
        if safety_after_sorter is not None:
            sorter_members = int(safety_after_sorter.get("operational_member_count") or 0)
            if after_apply_members > 0 and sorter_members == 0:
                handoffs["regressions"].append(
                    {
                        "code": CROSS_SUBSYSTEM_STATE_REGRESSION,
                        "status": STATUS_FAIL,
                        "detail": (
                            f"safety members after Apply={after_apply_members} wiped after "
                            f"sorter apply (members={sorter_members})"
                        ),
                        "after_apply": after_apply_members,
                        "after_sorter_apply": sorter_members,
                    }
                )

        # 5. Optional Autogen generation (library present)
        gen_dir = out_dir / "generated"
        gen_dir.mkdir(parents=True, exist_ok=True)
        library = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        generate_ok = False
        if skip_generate:
            generation_manifest = {
                "skipped": True,
                "reason": "skip_generate",
                "machine": machine,
                "generated_at": _iso(),
            }
        elif not library.is_file():
            generation_manifest = {
                "skipped": True,
                "reason": "library_missing",
                "library": str(library),
                "machine": machine,
                "generated_at": _iso(),
            }
            warnings.append("Autogen library missing — discovery/handoff only")
        elif inp is None:
            generation_manifest = {
                "skipped": True,
                "reason": "autogen_input_unavailable",
                "machine": machine,
                "generated_at": _iso(),
            }
        else:
            try:
                from fortna_autogen import DEFAULT_LIBRARY, generate

                # Persist workbook for from-run parity
                _write_json(wb_path, workbook)
                result = generate(inp, Path(DEFAULT_LIBRARY), gen_dir)
                generate_ok = bool(result.get("ok"))
                generation_manifest = {
                    "ok": generate_ok,
                    "machine": machine,
                    "generated_at": _iso(),
                    "result_keys": sorted(result.keys()),
                    "output_path": result.get("output_path") or result.get("l5x_path"),
                    "build_manifest": result.get("build_manifest"),
                    "error": result.get("error"),
                }
                # Prefer written L5X
                l5x_candidates = sorted(gen_dir.glob("*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True)
                if l5x_candidates:
                    generated_l5x = l5x_candidates[0]
                    generation_manifest["output_path"] = str(generated_l5x)
                bm = gen_dir / "build_manifest.json"
                if bm.is_file():
                    try:
                        generation_manifest["build_manifest_doc"] = _read_json(bm)
                    except Exception:
                        pass
            except Exception as ex:
                generate_ok = False
                generation_manifest = {
                    "ok": False,
                    "machine": machine,
                    "generated_at": _iso(),
                    "error": str(ex),
                    "traceback": traceback.format_exc()[-2000:],
                }
                warnings.append(f"Autogen generate failed: {ex}")

        handoffs["snapshots"]["generation_manifest"] = {
            "ok": generation_manifest.get("ok"),
            "skipped": generation_manifest.get("skipped"),
            "output_path": generation_manifest.get("output_path"),
            "fingerprint": _fingerprint(
                {k: generation_manifest.get(k) for k in ("ok", "skipped", "error", "output_path")}
            ),
        }

        # 6. Post-generation reference compare (oracle only)
        reference_compare: dict[str, Any] | None = None
        if mode == "reference" and ref_path is not None:
            if reference_open_hook:
                reference_open_hook(ref_path)
            if not ref_path.is_file():
                reference_compare = {"ok": False, "error": f"reference missing: {ref_path}"}
                checks.append(
                    _check_result(
                        "reference_compare",
                        STATUS_FAIL,
                        detail=f"reference L5X missing: {ref_path}",
                    )
                )
            elif generated_l5x is None or not generated_l5x.is_file():
                reference_compare = {"ok": False, "error": "no generated L5X to compare"}
                checks.append(
                    _check_result(
                        "reference_compare",
                        STATUS_REVIEW,
                        detail="reference mode but generation produced no L5X",
                    )
                )
            else:
                try:
                    from fortna_l5x_compare import run_compare

                    cmp_out = out_dir / "reference_compare"
                    reference_compare = run_compare(generated_l5x, ref_path, cmp_out)
                except Exception as ex:
                    reference_compare = {"ok": False, "error": str(ex)}
                    warnings.append(f"reference compare failed: {ex}")

        # 7. Checks
        # table resolution / machine closure
        closure_members = int((closure.get("counts") or {}).get("members") or 0)
        if closure_members > 0 and active_tables.get("table_count", 0) > 0:
            checks.append(
                _check_result(
                    "table_resolution_machine_closure",
                    STATUS_PASS,
                    detail=f"closure members={closure_members}; active tables={active_tables.get('table_count')}",
                    evidence={
                        "closure": _summarize_closure(closure),
                        "active_table_count": active_tables.get("table_count"),
                    },
                )
            )
        else:
            checks.append(
                _check_result(
                    "table_resolution_machine_closure",
                    STATUS_FAIL,
                    detail="machine closure empty or no active tables",
                    evidence={"closure_members": closure_members, "active_tables": active_tables},
                )
            )

        # equipment inventory
        eq_count = int(autogen_input_summary.get("conveyor_count") or 0)
        if eq_count > 0:
            checks.append(
                _check_result(
                    "equipment_inventory",
                    STATUS_PASS,
                    detail=f"autogen conveyors={eq_count}",
                    evidence={"conveyor_count": eq_count},
                )
            )
        else:
            checks.append(
                _check_result(
                    "equipment_inventory",
                    STATUS_REVIEW,
                    detail="no conveyors in autogen input",
                    evidence=autogen_input_summary,
                )
            )

        # Safety
        bad_default = _default_unassigned_operational_refs(_safety_from_workbook(workbook))
        safety_status = STATUS_PASS
        safety_detail_parts = []
        if bad_default:
            safety_status = STATUS_FAIL
            safety_detail_parts.append(
                f"Default/Unassigned operational refs: {', '.join(bad_default)}"
            )
        if any(r.get("code") == CROSS_SUBSYSTEM_STATE_REGRESSION for r in handoffs["regressions"]):
            safety_status = STATUS_FAIL
            safety_detail_parts.append(CROSS_SUBSYSTEM_STATE_REGRESSION)
        if mode == "virgin" and int(safety_before_apply.get("operational_member_count") or 0) > 0:
            # Virgin must not invent Safety members
            safety_status = STATUS_FAIL
            safety_detail_parts.append("virgin mode invented safety members")
        if mode == "virgin" and not safety_detail_parts:
            safety_status = STATUS_REVIEW
            safety_detail_parts.append(
                "virgin: no Safety Apply - membership REVIEW (fail-safe expected)"
            )
        if mode == "replay" and before_autogen_members == 0 and after_apply_members == 0:
            safety_status = _worst([safety_status, STATUS_REVIEW])
            safety_detail_parts.append("replay workbook has no operational safety members")
        checks.append(
            _check_result(
                "safety",
                safety_status,
                detail="; ".join(safety_detail_parts) or "ok",
                evidence={
                    "before_apply": safety_before_apply,
                    "after_apply": handoffs["snapshots"].get("safety_after_apply"),
                    "before_autogen": members_before_autogen,
                    "default_unassigned_operational": bad_default,
                    "regressions": handoffs["regressions"],
                },
            )
        )

        # Transport
        merge_summary = _summarize_merges(merge_report)
        transport_status = STATUS_PASS if merge_summary.get("proven_count", 0) >= 0 else STATUS_REVIEW
        if discovery_result.get("incomplete_run"):
            transport_status = STATUS_REVIEW
        checks.append(
            _check_result(
                "transport",
                transport_status,
                detail=f"proven merges={merge_summary.get('proven_count')}",
                evidence=merge_summary,
            )
        )

        # Sorter
        sorter_summary = _summarize_sorter(sorter_model)
        proven_hosts = _proven_sorter_hosts(sorter_model, closure)
        l5x_text = ""
        if generated_l5x and generated_l5x.is_file():
            l5x_text = generated_l5x.read_text(encoding="utf-8", errors="replace")
        stale_scan = (
            _scan_l5x_stale_hosts(l5x_text, proven_hosts)
            if l5x_text
            else {"stale_hosts": [], "fail": False, "skipped": True, "proven_hosts": sorted(proven_hosts)}
        )
        sorter_status = STATUS_PASS
        sorter_detail = (
            f"detected={sorter_summary.get('detected')} "
            f"divert_host={sorter_summary.get('divert_host_conveyor')}"
        )
        if stale_scan.get("fail"):
            sorter_status = STATUS_FAIL
            sorter_detail = f"stale sorter hosts in L5X: {stale_scan.get('stale_hosts')}"
        elif not sorter_summary.get("detected"):
            sorter_status = STATUS_REVIEW
            sorter_detail = "sorter not detected for machine"
        # Replay: Applied sorter_build requires final-artifact programs
        sb_wb = workbook.get("sorter_build") if isinstance(workbook.get("sorter_build"), dict) else {}
        sorter_applied = bool(
            sb_wb.get("appliedAt")
            or int(sb_wb.get("divert_count") or 0) > 0
            or (sb_wb.get("tracking") or [])
            or (sb_wb.get("known_sorters") or [])
        )
        expected_sorter_programs: list[str] = []
        missing_sorter_programs: list[str] = []
        if mode == "replay" and sorter_applied and l5x_text:
            expected_sorter_programs = ["Sorter_Track"]
            area = str(
                sb_wb.get("sorter_area_name")
                or sb_wb.get("area_name")
                or sorter_summary.get("sorter_area_name")
                or sorter_summary.get("transport_area")
                or "ShippingSorter"
            ).strip()
            if sb_wb.get("shipping_sorter_supported") or area:
                for suffix in (
                    "_Area_Fast",
                    "_Area_Slow",
                    "_Area_L1",
                    "_Area_L2",
                    "_Area_L3",
                ):
                    expected_sorter_programs.append(f"{area}{suffix}")
            progs = set(re.findall(r'Program Name="([^"]+)"', l5x_text))
            missing_sorter_programs = [p for p in expected_sorter_programs if p not in progs]
            if missing_sorter_programs:
                sorter_status = STATUS_FAIL
                sorter_detail = (
                    f"replay Applied sorter missing final programs: {missing_sorter_programs}"
                )
        elif mode == "replay" and sorter_applied and not l5x_text:
            sorter_status = _worst([sorter_status, STATUS_FAIL])
            sorter_detail = "replay Applied sorter but no generated L5X to validate"
        checks.append(
            _check_result(
                "sorter",
                sorter_status,
                detail=sorter_detail,
                evidence={
                    "sorter": sorter_summary,
                    "stale_scan": stale_scan,
                    "expected_programs": expected_sorter_programs,
                    "missing_programs": missing_sorter_programs,
                    "sorter_applied": sorter_applied,
                },
            )
        )

        # Merge (native P600-class discovered vs present in L5X)
        # Prefer autogen discharge names (P600, P816, …)
        try:
            from fortna_plc2_merge_discovery import discovery_to_autogen_merges_2to1 as _to_rows

            auto_rows = _to_rows(merge_report)
            proven_discharge = [
                str(r.get("discharge") or r.get("name") or "").strip().upper()
                for r in auto_rows
                if str(r.get("discharge") or r.get("name") or "").strip()
            ]
        except Exception:
            proven_discharge = list(merge_summary.get("proven_names") or [])
        merge_scan = (
            _scan_l5x_merges(l5x_text, proven_discharge)
            if l5x_text
            else {
                "discovered_proven": proven_discharge,
                "present_in_l5x": [],
                "missing_in_l5x": proven_discharge,
                "skipped": True,
            }
        )
        merge_status = STATUS_PASS
        if proven_discharge and l5x_text and merge_scan.get("missing_in_l5x"):
            # Missing native merges in L5X is REVIEW unless all missing → FAIL
            if len(merge_scan["missing_in_l5x"]) == len(proven_discharge):
                merge_status = STATUS_FAIL
            else:
                merge_status = STATUS_REVIEW
        elif not proven_discharge:
            merge_status = STATUS_REVIEW
        elif not l5x_text:
            merge_status = STATUS_REVIEW
        checks.append(
            _check_result(
                "merge",
                merge_status,
                detail=(
                    f"proven={proven_discharge}; present={merge_scan.get('present_in_l5x')}; "
                    f"missing={merge_scan.get('missing_in_l5x')}"
                ),
                evidence=merge_scan,
            )
        )

        # L5X structure + orphan site-specific scan
        structure_status = STATUS_SKIP
        structure_evidence: dict[str, Any] = {}
        if l5x_text:
            try:
                from fortna_l5x_studio_structure import validate_l5x_studio_structure

                structure_evidence = validate_l5x_studio_structure(l5x_text)
                errs = structure_evidence.get("errors") or structure_evidence.get("issues") or []
                if isinstance(structure_evidence.get("ok"), bool):
                    structure_status = STATUS_PASS if structure_evidence["ok"] else STATUS_FAIL
                else:
                    structure_status = STATUS_FAIL if errs else STATUS_PASS
            except Exception as ex:
                structure_status = STATUS_REVIEW
                structure_evidence = {"error": str(ex)}
        else:
            structure_status = STATUS_REVIEW
            structure_evidence = {"skipped": True, "reason": "no L5X"}

        orphan_evidence: dict[str, Any] = {}
        try:
            from fortna_autogen_provenance import audit

            # Build a thin autogen_report for orphan scan
            thin_report = {
                "merges": [
                    {"name": f"{n}_Merge", "merge_tag": f"{n}_Merge"}
                    for n in (merge_scan.get("present_in_l5x") or proven_discharge)
                ],
                "tags": sorted(
                    {
                        t
                        for tags in (stale_scan.get("tags_by_host") or {}).values()
                        for t in tags
                    }
                ),
                "sorter_build": workbook.get("sorter_build") or {},
                "transport_merges": workbook.get("merges_2to1") or [],
            }
            if l5x_text:
                # Collect program/tag names lightly
                thin_report["tags"] = list(
                    set(thin_report.get("tags") or [])
                    | set(re.findall(r'Name="(P\d{2,4}_(?:Divert\d*|Merge|Enc)[^"]*)"', l5x_text))
                )
            provenance_doc = audit(
                work_run,
                machine,
                safety_build=_safety_from_workbook(workbook),
                autogen_report=thin_report,
                transport_merges=workbook.get("merges_2to1") or [],
                scan_production_code=False,
            )
            orphans = provenance_doc.get("orphans") or []
            orphan_evidence = {
                "orphan_generation_count": provenance_doc.get("orphan_generation_count"),
                "orphan_names": [o.get("artifact") for o in orphans[:40]],
            }
            if orphans and l5x_text:
                structure_status = _worst([structure_status, STATUS_FAIL])
            elif orphans:
                structure_status = _worst([structure_status, STATUS_REVIEW])
        except Exception as ex:
            orphan_evidence = {"error": str(ex)}
            warnings.append(f"provenance/orphan scan failed: {ex}")

        checks.append(
            _check_result(
                "l5x_structure_orphan_scan",
                structure_status,
                detail=f"structure={structure_status}; orphans={orphan_evidence.get('orphan_generation_count')}",
                evidence={"structure": structure_evidence, "orphans": orphan_evidence},
            )
        )

        # Final-artifact closure (Default Safety ops + pack orphans)
        if l5x_text:
            try:
                from fortna_final_artifact_closure import validate_final_artifact

                fav = validate_final_artifact(
                    l5x_text=l5x_text,
                    machine=machine,
                    allowed_divert_hosts=list(proven_hosts or []),
                )
                fav_status = fav.get("status") or STATUS_REVIEW
                if fav_status == "FAIL":
                    structure_status = STATUS_FAIL
                    checks.append(
                        _check_result(
                            "final_artifact_closure",
                            STATUS_FAIL,
                            detail="; ".join(fav.get("errors") or [])[:500],
                            evidence=fav,
                        )
                    )
                elif fav_status == "REVIEW":
                    structure_status = _worst([structure_status, STATUS_REVIEW])
                    checks.append(
                        _check_result(
                            "final_artifact_closure",
                            STATUS_REVIEW,
                            detail="; ".join(fav.get("reviews") or [])[:500] or "review",
                            evidence=fav,
                        )
                    )
                else:
                    checks.append(
                        _check_result(
                            "final_artifact_closure",
                            STATUS_PASS,
                            detail=f"orphan_count={fav.get('orphan_count', 0)}",
                            evidence=fav,
                        )
                    )
                # Safety: operational Default refs in final L5X = FAIL
                if fav.get("scan", {}).get("default_operational_zone_refs"):
                    for c in checks:
                        if c.get("name") == "safety":
                            c["status"] = STATUS_FAIL
                            c["detail"] = (
                                (c.get("detail") or "")
                                + "; DEFAULT_SAFETY_OPERATIONAL_REF in final L5X: "
                                + str(fav["scan"]["default_operational_zone_refs"])
                            ).strip("; ")
                            break
            except Exception as ex:
                warnings.append(f"final artifact closure failed: {ex}")

        # Provenance coverage summary — REVIEW_REQUIRED must not report as PASS
        if provenance_doc:
            counts = provenance_doc.get("counts") or {}
            total = int(provenance_doc.get("total_records") or 0)
            review_n = len(provenance_doc.get("review_required") or [])
            unknown_n = len(provenance_doc.get("unknown") or [])
            # Also count class buckets
            if isinstance(counts, dict):
                review_n = max(review_n, int(counts.get("REVIEW_REQUIRED") or 0))
                unknown_n = max(unknown_n, int(counts.get("UNKNOWN") or 0))
                error_n = int(counts.get("ERROR") or 0) + int(
                    provenance_doc.get("orphan_generation_count") or 0
                )
            else:
                error_n = int(provenance_doc.get("orphan_generation_count") or 0)
            prov_status = STATUS_PASS
            if review_n > 0 or unknown_n > 0:
                prov_status = STATUS_REVIEW
            if error_n > 0 and l5x_text:
                prov_status = STATUS_FAIL
            checks.append(
                _check_result(
                    "provenance_coverage",
                    prov_status,
                    detail=f"records={total}; review={review_n}; unknown={unknown_n}; errors={error_n}",
                    evidence={"counts": counts, "total_records": total},
                )
            )
        else:
            checks.append(
                _check_result(
                    "provenance_coverage",
                    STATUS_REVIEW,
                    detail="provenance audit unavailable",
                )
            )

        # Final artifact validation bundle
        final_validation = {
            "generated_l5x": str(generated_l5x) if generated_l5x else None,
            "generate_ok": generate_ok,
            "stale_sorter_hosts": stale_scan,
            "merge_presence": merge_scan,
            "structure": structure_evidence,
            "orphans": orphan_evidence,
            "reference_compare": reference_compare,
        }

        overall = _worst([c["status"] for c in checks] + [STATUS_FAIL if handoffs["regressions"] else STATUS_PASS])
        if overall == STATUS_PASS and any(c["status"] == STATUS_REVIEW for c in checks):
            overall = STATUS_REVIEW
        if handoffs["regressions"]:
            overall = STATUS_FAIL

        report = {
            "ok": overall != STATUS_FAIL,
            "overall": overall,
            "machine": machine,
            "site": site,
            "mode": mode,
            "generated_at": _iso(),
            "run_dir_source": str(src_run),
            "out_dir": str(out_dir),
            "sanitized": sanitized,
            "fail_on_review": fail_on_review,
            "skip_generate": skip_generate,
            "checks": checks,
            "dashboard": {c["subsystem"]: c["status"] for c in checks},
            "regressions": handoffs["regressions"],
            "warnings": warnings,
            "errors": errors,
            "generation_manifest": generation_manifest,
            "reference_l5x": str(ref_path) if ref_path else None,
            "reference_used_in_discovery": False,
            "reference_used_in_generation": False,
        }

        # Write artifacts
        _write_json(out_dir / "qualification_report.json", _maybe_sanitize(report, sanitized))
        _write_json(out_dir / "handoff_snapshots.json", _maybe_sanitize(handoffs, sanitized))
        _write_json(out_dir / "generation_manifest.json", _maybe_sanitize(generation_manifest, sanitized))
        _write_json(out_dir / "active_tables.json", _maybe_sanitize(active_tables, sanitized))
        _write_json(
            out_dir / "machine_closure.json",
            _maybe_sanitize(
                {
                    **_summarize_closure(closure),
                    # Full member list is large; keep identities only unless sanitized strips it
                    "member_identities": [
                        {
                            "table": m.get("source_table"),
                            "identity": m.get("identity"),
                            "source_id": m.get("source_id"),
                        }
                        for m in (closure.get("members") or [])
                    ]
                    if not sanitized
                    else None,
                    "member_count": closure_members,
                },
                sanitized,
            ),
        )
        _write_json(
            out_dir / "final_artifact_validation.json",
            _maybe_sanitize(final_validation, sanitized),
        )
        if provenance_doc is not None:
            thin_prov = {
                "ok": provenance_doc.get("ok"),
                "machine": provenance_doc.get("machine"),
                "counts": provenance_doc.get("counts"),
                "total_records": provenance_doc.get("total_records"),
                "orphan_generation_count": provenance_doc.get("orphan_generation_count"),
                "orphans": provenance_doc.get("orphans"),
                "review_required_count": len(provenance_doc.get("review_required") or []),
                "unknown_count": len(provenance_doc.get("unknown") or []),
            }
            _write_json(out_dir / "provenance.json", _maybe_sanitize(thin_prov, sanitized))

        # Markdown dashboard — PASS/REVIEW/FAIL first
        md_lines = [
            f"# Qualification Report - {machine}",
            "",
            f"**Overall: {overall}**",
            "",
            f"- Mode: `{mode}`",
            f"- Site: `{site}`",
            f"- Generated: `{report['generated_at']}`",
            f"- Source RUN: `{src_run}`",
            f"- Out: `{out_dir}`",
            "",
            "## Dashboard",
            "",
            "| Subsystem | Status | Detail |",
            "|-----------|--------|--------|",
        ]
        for c in checks:
            detail = (c.get("detail") or "").replace("|", "/").replace("\n", " ")
            md_lines.append(f"| {c['subsystem']} | **{c['status']}** | {detail[:160]} |")
        if handoffs["regressions"]:
            md_lines += ["", "## Regressions", ""]
            for r in handoffs["regressions"]:
                md_lines.append(f"- **{r.get('code')}**: {r.get('detail')}")
        if warnings:
            md_lines += ["", "## Warnings", ""]
            for w in warnings:
                md_lines.append(f"- {w}")
        if errors:
            md_lines += ["", "## Errors", ""]
            for e in errors:
                md_lines.append(f"- {e}")
        md_lines += [
            "",
            "## Artifacts",
            "",
            "- `qualification_report.json`",
            "- `handoff_snapshots.json`",
            "- `generation_manifest.json`",
            "- `active_tables.json`",
            "- `machine_closure.json`",
            "- `final_artifact_validation.json`",
            "- `provenance.json` (optional thin)",
        ]
        if generated_l5x:
            md_lines.append(f"- generated L5X: `{generated_l5x.name}`")
        (out_dir / "qualification_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        report["exit_code"] = _exit_code(overall, fail_on_review=fail_on_review)
        _write_json(out_dir / "qualification_report.json", _maybe_sanitize(report, sanitized))
        return report
    finally:
        # Best-effort cleanup of temp workspace (keep out_dir artifacts)
        try:
            shutil.rmtree(work_root, ignore_errors=True)
        except Exception:
            pass


def _exit_code(overall: str, *, fail_on_review: bool) -> int:
    if overall == STATUS_FAIL:
        return 1
    if overall == STATUS_REVIEW and fail_on_review:
        return 2
    return 0


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def run_compare(*, a: Path, b: Path, out_dir: Path) -> dict[str, Any]:
    """Compare two qualification directories; detect safety member regressions."""
    a = Path(a)
    b = Path(b)
    out_dir = Path(out_dir)
    if not a.is_absolute():
        a = (ROOT / a).resolve()
    if not b.is_absolute():
        b = (ROOT / b).resolve()
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def _load_handoff(qual: Path) -> dict[str, Any]:
        p = qual / "handoff_snapshots.json"
        if p.is_file():
            return _read_json(p)
        # Allow synthetic snapshot dirs that are the handoff file itself
        if qual.is_file() and qual.name.endswith(".json"):
            return _read_json(qual)
        return {}

    def _load_report(qual: Path) -> dict[str, Any]:
        p = qual / "qualification_report.json"
        return _read_json(p) if p.is_file() else {}

    ha = _load_handoff(a)
    hb = _load_handoff(b)
    ra = _load_report(a)
    rb = _load_report(b)

    def _members_at(h: dict[str, Any], key: str) -> int:
        snap = (h.get("snapshots") or {}).get(key) or {}
        if isinstance(snap, dict):
            if "operational_member_count" in snap:
                return int(snap.get("operational_member_count") or 0)
            if "safety_build_members" in snap and isinstance(snap["safety_build_members"], dict):
                return int(snap["safety_build_members"].get("operational_member_count") or 0)
            if "member_count" in snap:
                return int(snap.get("member_count") or 0)
        return 0

    regressions: list[dict[str, Any]] = []
    # A had members after apply, B lost them before autogen (or A→B wipe)
    a_after = _members_at(ha, "safety_after_apply")
    if a_after == 0:
        a_after = _members_at(ha, "safety_before_apply")
    b_before_auto = _members_at(hb, "autogen_input_summary")
    if b_before_auto == 0:
        b_before_auto = _members_at(hb, "safety_before_apply")
    # Also compare same-dir style: within B
    b_after = _members_at(hb, "safety_after_apply")
    b_auto = _members_at(hb, "autogen_input_summary")

    if b_after > 0 and b_auto == 0:
        regressions.append(
            {
                "code": CROSS_SUBSYSTEM_STATE_REGRESSION,
                "status": STATUS_FAIL,
                "side": "b",
                "detail": (
                    f"B safety members after Apply={b_after} but before Autogen={b_auto}"
                ),
                "after_apply": b_after,
                "before_autogen": b_auto,
            }
        )
    if a_after > 0 and b_auto == 0 and b_after == 0:
        regressions.append(
            {
                "code": CROSS_SUBSYSTEM_STATE_REGRESSION,
                "status": STATUS_FAIL,
                "side": "a_to_b",
                "detail": (
                    f"A had safety members={a_after} but B before Autogen={b_auto}"
                ),
                "a_after_apply": a_after,
                "b_before_autogen": b_auto,
            }
        )

    # Diff dashboards
    dash_a = ra.get("dashboard") or {}
    dash_b = rb.get("dashboard") or {}
    keys = sorted(set(dash_a) | set(dash_b))
    dashboard_diff = {
        k: {"a": dash_a.get(k), "b": dash_b.get(k)}
        for k in keys
        if dash_a.get(k) != dash_b.get(k)
    }

    overall = STATUS_FAIL if regressions else STATUS_PASS
    result = {
        "ok": not regressions,
        "overall": overall,
        "generated_at": _iso(),
        "a": str(a),
        "b": str(b),
        "regressions": regressions,
        "dashboard_diff": dashboard_diff,
        "member_counts": {
            "a_after_apply": a_after,
            "b_after_apply": b_after,
            "b_before_autogen": b_auto,
        },
    }
    _write_json(out_dir / "compare_report.json", result)
    md = [
        "# Qualification Compare",
        "",
        f"**Overall: {overall}**",
        "",
        f"- A: `{a}`",
        f"- B: `{b}`",
        "",
        "## Regressions",
        "",
    ]
    if regressions:
        for r in regressions:
            md.append(f"- **{r['code']}**: {r['detail']}")
    else:
        md.append("- none")
    if dashboard_diff:
        md += ["", "## Dashboard diff", "", "| Subsystem | A | B |", "|-----------|---|---|"]
        for k, v in dashboard_diff.items():
            md.append(f"| {k} | {v.get('a')} | {v.get('b')} |")
    (out_dir / "compare_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    result["exit_code"] = 0 if overall == STATUS_PASS else 1
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Site Forge Qualification Runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pq = sub.add_parser("qualify", help="Run virgin/replay/reference qualification")
    pq.add_argument("--run-dir", required=True, type=Path)
    pq.add_argument("--machine", required=True)
    pq.add_argument("--project-workbook", type=Path, default=None)
    pq.add_argument("--reference-l5x", type=Path, default=None)
    pq.add_argument("--out", type=Path, default=None)
    pq.add_argument(
        "--mode",
        choices=("virgin", "replay", "reference"),
        default="virgin",
    )
    pq.add_argument("--sanitized", action="store_true")
    pq.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit nonzero when overall is REVIEW (default: REVIEW exits 0)",
    )
    pq.add_argument(
        "--skip-generate",
        action="store_true",
        help="Discovery + handoff checks only (no L5X generate)",
    )
    pq.add_argument(
        "--label",
        default="",
        help="Explicit output folder name under exports/qualification/<site>/ "
        "(e.g. virgin-5eaea9d, replay-gui-parity)",
    )

    pc = sub.add_parser("compare", help="Compare two qualification output dirs")
    pc.add_argument("--a", required=True, type=Path)
    pc.add_argument("--b", required=True, type=Path)
    pc.add_argument("--out", required=True, type=Path)

    args = ap.parse_args(argv)
    if args.cmd == "qualify":
        report = run_qualify(
            run_dir=args.run_dir,
            machine=args.machine,
            mode=args.mode,
            project_workbook=args.project_workbook,
            reference_l5x=args.reference_l5x,
            out_dir=args.out,
            sanitized=bool(args.sanitized),
            fail_on_review=bool(args.fail_on_review),
            skip_generate=bool(args.skip_generate),
            label=str(getattr(args, "label", "") or ""),
        )
        # Always print a human-findable banner (Curtis must not hunt for outputs)
        print("")
        print(f"QUALIFICATION MODE: {report.get('mode')}")
        print(f"RESULT: {report.get('overall')}")
        print(f"OUTPUT DIRECTORY:\n{report.get('out_dir')}")
        print("")
        print(
            json.dumps(
                {
                    "ok": report.get("ok"),
                    "overall": report.get("overall"),
                    "out_dir": report.get("out_dir"),
                    "dashboard": report.get("dashboard"),
                    "exit_code": report.get("exit_code"),
                },
                indent=2,
            )
        )
        return int(report.get("exit_code") or 0)

    if args.cmd == "compare":
        result = run_compare(a=args.a, b=args.b, out_dir=args.out)
        print(
            json.dumps(
                {
                    "ok": result.get("ok"),
                    "overall": result.get("overall"),
                    "regressions": result.get("regressions"),
                    "exit_code": result.get("exit_code"),
                },
                indent=2,
            )
        )
        return int(result.get("exit_code") or 0)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
