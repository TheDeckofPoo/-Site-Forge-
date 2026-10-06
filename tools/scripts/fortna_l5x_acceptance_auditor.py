#!/usr/bin/env python3
"""ORI-111 — Post-generation L5X Acceptance Auditor + autonomous repair loop.

Pipeline:
  resolved model → EXPECTED_ARTIFACT_MANIFEST
  → generate provisional L5X (STAGING)
  → audit expected vs actual
  → AUDIT_PASS → CURRENT
  → AUDIT_FAIL → REPAIR_TICKET → L0/AI/Relay → regenerate → re-audit

Only AUDIT_PASS may promote to exports/current.

Loop protection: every defect has a normalized FAILURE SIGNATURE. The same
signature may not be retried with the same material hash. After 3 materially
different failed repairs → GENERATOR_DEFECT (stop auto-rebuild).

Safety membership may never be invented by AI/Relay.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

STATE_STAGING = "STAGING"
STATE_AUDIT_FAIL = "AUDIT_FAIL"
STATE_REPAIRING = "REPAIRING"
STATE_AUDIT_PASS = "AUDIT_PASS"
STATE_CURRENT = "CURRENT"
STATE_GENERATOR_DEFECT = "GENERATOR_DEFECT"
STATE_ENGINEER_REQUIRED = "ENGINEER_REQUIRED"

MAX_ATTEMPTS_PER_SIGNATURE = 3
MAX_OUTER_REPAIR_CYCLES = 5

_NOP_ONLY_RE = re.compile(r"^\s*(?:NOP\s*\(\s*\)\s*;?\s*)+$", re.I)
_BLANK_OPERAND_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU|ONS|OSR|OSF)\s*\(\s*(?:\)|\?[,)]|,\s*[,)]|\"\"|''|_unnamed_)",
    re.I,
)
_QUESTION_OPERAND_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*\?[^\)]*\)",
    re.I,
)
_UNNAMED_TAG_RE = re.compile(r"\b_unnamed_|\bUNNAMED\b|Name=\"\"", re.I)
_JSR_RE = re.compile(r"\bJSR\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)", re.I)

FOREIGN_SITE_TOKENS = (
    "MSCRENOPICK",
    "MSCRENOPICK_Area",
    "MSCRENOPICK_ESZone1",
    "MSCRENOSHIP",
    "MSCRENOPACK",
    "TFCP1_ESZone1",
    "TFCP1_Area",
    "Area_Test1_ESZone1",
    "ORDENCP1_ESZone1",
    "ORDENCP1_Area",
    "ORINDYAC3_ESZone1",
    "ORINDYAC3_Area",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        import subprocess

        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
            )
            .strip()
        )
    except Exception:
        return ""


def auditor_enabled() -> bool:
    return (os.environ.get("SITEFORGE_L5X_AUDITOR") or "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
        "OFF",
    )


def failure_signature(
    code: str,
    *,
    program: str = "",
    routine: str = "",
    zone: str = "",
    extra: str = "",
) -> str:
    """Normalized FAILURE SIGNATURE for loop protection."""
    parts = [str(code or "UNKNOWN").strip().upper()]
    for p in (zone, program, routine, extra):
        s = str(p or "").strip()
        if s:
            parts.append(s)
    return ":".join(parts)


def material_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def sha256_file(path: Path | str) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


# ---------------------------------------------------------------------------
# L5X parse helpers
# ---------------------------------------------------------------------------


def parse_l5x_programs(l5x_text: str) -> dict[str, dict[str, Any]]:
    """program -> {routines: {name: {rungs, non_nop, texts, jsr_targets}}}."""
    out: dict[str, dict[str, Any]] = {}
    if not l5x_text:
        return out
    for pm in re.finditer(r"<Program\b([^>]*)>(.*?)</Program>", l5x_text, re.S):
        attrs, pbody = pm.group(1), pm.group(2)
        m = re.search(r'Name="([^"]+)"', attrs)
        if not m:
            continue
        pname = m.group(1)
        routines: dict[str, dict[str, Any]] = {}
        for rm in re.finditer(r"<Routine\b([^>]*)>(.*?)</Routine>", pbody, re.S):
            rattrs, rbody = rm.group(1), rm.group(2)
            rm2 = re.search(r'Name="([^"]+)"', rattrs)
            if not rm2:
                continue
            rname = rm2.group(1)
            texts = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody, re.S)
            jsr_targets: list[str] = []
            non_nop = 0
            for tx in texts:
                s = (tx or "").strip()
                if not s:
                    continue
                if _NOP_ONLY_RE.match(s) or s.upper().startswith("NOP"):
                    continue
                non_nop += 1
                jsr_targets.extend(_JSR_RE.findall(s))
            routines[rname] = {
                "rung_count": len(texts),
                "texts": texts,
                "non_nop": non_nop,
                "jsr_targets": jsr_targets,
                "populated": non_nop > 0,
            }
        out[pname] = {"routines": routines}
    return out


def _routine_populated(programs: dict, program: str, routine: str) -> bool:
    return bool(
        ((programs.get(program) or {}).get("routines") or {})
        .get(routine, {})
        .get("populated")
    )


def _find_program_ending(programs: dict, suffix: str) -> str | None:
    suf = suffix.lower()
    for p in programs:
        if p.lower().endswith(suf):
            return p
    return None


# ---------------------------------------------------------------------------
# EXPECTED_ARTIFACT_MANIFEST
# ---------------------------------------------------------------------------


def _zone_entries(inp: Any, report: dict[str, Any] | None) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    members_list = list(getattr(inp, "safety_zone_members", None) or [])
    if not members_list and isinstance(report, dict):
        sb = report.get("safety_build") or {}
        if isinstance(sb, dict):
            members_list = list(sb.get("zones") or [])
    for z in members_list:
        if not isinstance(z, dict):
            continue
        name = str(z.get("name") or z.get("engineering_name") or "").strip()
        if not name:
            continue
        status = str(z.get("status") or "").upper()
        operational = z.get("operational")
        origin = str(
            z.get("membersOrigin") or z.get("origin") or z.get("zoneOrigin") or ""
        ).upper()
        members = [str(m) for m in (z.get("members") or []) if m]
        ready = (
            status in ("READY", "OPERATIONAL")
            or operational is True
            or (
                members
                and (
                    "ENGINEER" in origin
                    or "PROVEN" in origin
                    or origin in ("ENGINEER_ASSIGNED", "ENGINEER_CREATED")
                )
            )
        )
        if not ready or not members:
            continue
        zones.append(
            {
                "name": name,
                "members": members,
                "area": z.get("area") or z.get("areaRef") or "",
                "require_safe_logic": f"{name}_Safe_Logic",
                "require_safe_pi": f"{name}_Safe_PI",
                "require_main_jsr": True,
                "members_origin": origin or "ENGINEER_ASSIGNED",
            }
        )
    return zones


def build_expected_artifact_manifest(
    inp: Any,
    *,
    report: dict[str, Any] | None = None,
    build_id: str = "",
    run_sha: str = "",
    git_sha: str = "",
) -> dict[str, Any]:
    """Build EXPECTED_ARTIFACT_MANIFEST from the resolved site model (pre-generation)."""
    report = report if isinstance(report, dict) else {}
    machine = str(
        getattr(inp, "machine", None)
        or getattr(inp, "project_name", None)
        or report.get("machine")
        or report.get("controller")
        or ""
    ).strip()
    areas = [a for a in (getattr(inp, "areas", None) or report.get("areas") or []) if a]
    if not areas and machine:
        areas = [f"{machine}_Area"]
    conveyor_count = int(
        report.get("conveyor_count")
        or len(getattr(inp, "conveyors", None) or [])
        or 0
    )
    include_io = bool(getattr(inp, "include_io_map", True))
    if "include_io_map" in report:
        include_io = bool(report.get("include_io_map"))

    # Equipment discovery — only require when discovered
    equip = report.get("equipment") or report.get("equipment_counts") or {}
    if not isinstance(equip, dict):
        equip = {}
    merges_n = int(
        equip.get("merges_table_usable")
        or equip.get("merges")
        or report.get("merge_count")
        or 0
    )
    sorters_n = int(
        equip.get("sorters_table_usable")
        or equip.get("sorters")
        or report.get("sorter_count")
        or 0
    )

    transport_programs: list[str] = []
    for area in areas:
        for suf in ("_Slow", "_Fast", "_L1", "_L2"):
            transport_programs.append(f"{area}{suf}" if not area.endswith(suf) else area)
        # Prefer canonical Area_Slow style: areas already named like MSCRENOPICK_Area
        # so MSCRENOPICK_Area_Slow etc. — fix if we double-suffixed
    # Normalize: if area already ends with _Area, suffixes append correctly.
    transport_programs = []
    for area in areas:
        base = area
        for suf in ("Slow", "Fast", "L1", "L2"):
            transport_programs.append(f"{base}_{suf}")
    if sorters_n > 0:
        for area in areas:
            transport_programs.append(f"{area}_L3")

    zones = _zone_entries(inp, report)
    safety_required = len(zones) > 0

    self_upper = machine.upper()
    foreign: list[str] = []
    for t in FOREIGN_SITE_TOKENS:
        tu = t.upper()
        if self_upper and (tu == self_upper or tu.startswith(self_upper + "_")):
            continue
        if self_upper and self_upper in tu:
            continue
        foreign.append(t)

    manifest: dict[str, Any] = {
        "version": 1,
        "ori": "ORI-111",
        "kind": "EXPECTED_ARTIFACT_MANIFEST",
        "created_at": _ts(),
        "controller": machine,
        "machine": machine,
        "areas": areas,
        "build_id": build_id,
        "run_sha": run_sha,
        "git_sha": git_sha or _git_sha(),
        "transportation": {
            "required": conveyor_count > 0,
            "min_conveyors": conveyor_count,
            "programs": transport_programs if conveyor_count > 0 else [],
            "core_routines_populated": conveyor_count > 0,
            "fast_program_suffix": "_Fast",
        },
        "io": {
            "required": include_io,
            "program": "IO_MAP" if include_io else None,
        },
        "safety": {
            "required": safety_required,
            "program": "ES" if safety_required else None,
            "require_main_routine": safety_required,
            "zones": zones,
        },
        "merges": {
            "required": merges_n > 0,
            "count": merges_n,
        },
        "sorters": {
            "required": sorters_n > 0,
            "count": sorters_n,
        },
        "foreign_site_forbid": foreign,
        "reject_blank_operands": True,
        "reject_unnamed_tags": True,
        "reject_question_operands": True,
    }
    return manifest


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@dataclass
class AuditFailure:
    code: str
    signature: str
    subsystem: str
    expected: str
    actual: str
    program: str = ""
    routine: str = ""
    zone: str = ""
    rung: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "signature": self.signature,
            "subsystem": self.subsystem,
            "expected": self.expected,
            "actual": self.actual,
            "program": self.program,
            "routine": self.routine,
            "zone": self.zone,
            "rung": self.rung,
            "detail": self.detail,
        }


def audit_l5x(
    l5x_path: Path | str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Compare actual L5X against EXPECTED_ARTIFACT_MANIFEST."""
    path = Path(l5x_path)
    failures: list[AuditFailure] = []
    machine = str(manifest.get("machine") or manifest.get("controller") or "")

    if not path.is_file():
        failures.append(
            AuditFailure(
                code="L5X_MISSING",
                signature=failure_signature("L5X:MISSING"),
                subsystem="POST_BUILD",
                expected="provisional L5X in STAGING",
                actual=f"missing: {path}",
            )
        )
        return {
            "status": STATE_AUDIT_FAIL,
            "ok": False,
            "failures": [f.to_dict() for f in failures],
            "l5x": str(path),
            "audited_at": _ts(),
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    programs = parse_l5x_programs(text)
    program_names = set(programs.keys())

    # --- Transportation ---
    transport = manifest.get("transportation") or {}
    if transport.get("required"):
        for pname in transport.get("programs") or []:
            # Accept either exact name or any program ending with same suffix
            suf = ""
            for s in ("_Slow", "_Fast", "_L1", "_L2", "_L3"):
                if pname.endswith(s):
                    suf = s
                    break
            hit = pname if pname in program_names else _find_program_ending(programs, suf)
            if not hit:
                failures.append(
                    AuditFailure(
                        code="TRANSPORT_MISSING_PROGRAM",
                        signature=failure_signature(
                            "TRANSPORT:MISSING_PROGRAM", extra=suf or pname
                        ),
                        subsystem="TRANSPORTATION",
                        expected=pname,
                        actual="absent",
                        program=pname,
                    )
                )
                continue
            # Core Fast must be populated when transport required
            if suf == "_Fast" or transport.get("core_routines_populated"):
                rt = (programs.get(hit) or {}).get("routines") or {}
                # Prefer Main_Routine / program body with any non-NOP routine
                populated_any = any(r.get("populated") for r in rt.values())
                main = rt.get("Main_Routine") or rt.get("Main") or {}
                if suf == "_Fast" and not (
                    main.get("populated") or populated_any
                ):
                    failures.append(
                        AuditFailure(
                            code="TRANSPORT_EMPTY_CORE",
                            signature=failure_signature(
                                "TRANSPORT:EMPTY_CORE", program=hit
                            ),
                            subsystem="TRANSPORTATION",
                            expected=f"{hit} populated core logic",
                            actual="empty/NOP-only",
                            program=hit,
                            routine="Main_Routine",
                        )
                    )

    # --- I/O ---
    io = manifest.get("io") or {}
    if io.get("required"):
        io_prog = str(io.get("program") or "IO_MAP")
        if io_prog not in program_names:
            failures.append(
                AuditFailure(
                    code="IO_MISSING_PROGRAM",
                    signature=failure_signature("IO:MISSING_PROGRAM", extra=io_prog),
                    subsystem="IO",
                    expected=io_prog,
                    actual="absent",
                    program=io_prog,
                )
            )

    # --- I/O SOURCE CONSERVATION (RUN ledger → canonical → L5X) ---
    # Denominator is upstream RUN evidence, never physical_io_map.csv alone.
    cons = io.get("source_conservation") if isinstance(io, dict) else None
    if not isinstance(cons, dict):
        cons = manifest.get("io_source_conservation")
    if isinstance(cons, dict) and cons.get("enforce", True):
        try:
            from fortna_run_io_source_ledger import (
                audit_source_conservation,
                build_run_io_source_ledger,
                reconcile_ledger,
            )

            if cons.get("reconciled"):
                reconciled = cons["reconciled"]
            else:
                run_dir = cons.get("run_dir") or manifest.get("run_dir")
                mach = str(cons.get("machine") or machine or "")
                if run_dir and mach:
                    ledger = build_run_io_source_ledger(run_dir, mach)
                    canon = cons.get("canonical_device_names")
                    canon_set = (
                        {str(x).upper() for x in canon}
                        if isinstance(canon, (list, set, tuple))
                        else None
                    )
                    reconciled = reconcile_ledger(
                        ledger,
                        physical_io_map_csv=cons.get("physical_io_map_csv"),
                        l5x_path=path,
                        machine=mach,
                        canonical_device_names=canon_set,
                    )
                else:
                    reconciled = {
                        "conservation_ok": False,
                        "ledger_complete": False,
                        "silently_missing": 0,
                        "failures": [
                            {
                                "code": "IO_SOURCE_LEDGER_NOT_PROVEN",
                                "signature": "IO:SOURCE_LEDGER_NOT_PROVEN",
                                "device": "",
                            }
                        ],
                    }
            for f in audit_source_conservation(reconciled):
                failures.append(
                    AuditFailure(
                        code=str(f.get("code") or "IO_SOURCE_CONSERVATION_FAILURE"),
                        signature=str(
                            f.get("signature")
                            or failure_signature(
                                "IO:SOURCE_CONSERVATION_FAILURE",
                                extra=str(f.get("device") or ""),
                            )
                        ),
                        subsystem="IO",
                        expected="source candidate accounted (MAPPED/SPARE/FOREIGN/ALIAS/REVIEW/UNSUPPORTED)",
                        actual=f"silently_missing device={f.get('device')}",
                        detail={
                            "silently_missing": reconciled.get("silently_missing"),
                            "source_physical_candidates": reconciled.get(
                                "source_physical_candidates"
                            ),
                            "coverage_status": reconciled.get("coverage_status"),
                        },
                    )
                )
        except Exception as _cons_ex:  # noqa: BLE001
            failures.append(
                AuditFailure(
                    code="IO_SOURCE_CONSERVATION_ERROR",
                    signature=failure_signature("IO:SOURCE_CONSERVATION_ERROR"),
                    subsystem="IO",
                    expected="RUN_IO_SOURCE_LEDGER reconcile",
                    actual=str(_cons_ex)[:300],
                )
            )

        # Engineering resolution (unique LOCAL devices) — separate from conservation.
        # REVIEW_REQUIRED is not success. Require threshold + zero critical residual
        # for AUDIT_PASS / CURRENT promotion when enforce_resolution is set.
        try:
            from fortna_run_io_source_ledger import (
                RESOLUTION_THRESHOLD_PCT,
                audit_device_resolution,
            )

            canon_block = None
            if isinstance(cons, dict):
                canon_block = cons.get("canonical") or cons.get("canonical_ledger")
            if not isinstance(canon_block, dict):
                canon_block = (
                    manifest.get("io_canonical_devices")
                    if isinstance(manifest.get("io_canonical_devices"), dict)
                    else None
                )
            enforce_res = True
            if isinstance(cons, dict) and "enforce_resolution" in cons:
                enforce_res = bool(cons.get("enforce_resolution"))
            if enforce_res and isinstance(canon_block, dict):
                thr = float(
                    cons.get("resolution_threshold_pct")
                    if isinstance(cons, dict) and cons.get("resolution_threshold_pct") is not None
                    else RESOLUTION_THRESHOLD_PCT
                )
                for f in audit_device_resolution(canon_block, threshold_pct=thr):
                    failures.append(
                        AuditFailure(
                            code=str(f.get("code") or "IO_DEVICE_RESOLUTION_FAILURE"),
                            signature=str(
                                f.get("signature")
                                or failure_signature(
                                    "IO:DEVICE_RESOLUTION_FAILURE",
                                    extra=str(f.get("device") or ""),
                                )
                            ),
                            subsystem="IO",
                            expected=(
                                f"unique LOCAL resolution>={thr}% and critical Safety/PB resolved"
                            ),
                            actual=str(f.get("detail") or f.get("device") or "")[:300],
                            detail={
                                "device_resolution_coverage_pct": canon_block.get(
                                    "device_resolution_coverage_pct"
                                ),
                                "critical_unresolved_count": canon_block.get(
                                    "critical_unresolved_count"
                                ),
                                "engineering_resolution_ok": canon_block.get(
                                    "engineering_resolution_ok"
                                ),
                            },
                        )
                    )
        except Exception as _res_ex:  # noqa: BLE001
            failures.append(
                AuditFailure(
                    code="IO_DEVICE_RESOLUTION_ERROR",
                    signature=failure_signature("IO:DEVICE_RESOLUTION_ERROR"),
                    subsystem="IO",
                    expected="canonical device resolution audit",
                    actual=str(_res_ex)[:300],
                )
            )

    # --- Safety ---
    safety = manifest.get("safety") or {}
    if safety.get("required"):
        if "ES" not in program_names:
            failures.append(
                AuditFailure(
                    code="SAFETY_MISSING_PROGRAM",
                    signature=failure_signature("SAFETY:MISSING_PROGRAM", extra="ES"),
                    subsystem="SAFETY",
                    expected="ES",
                    actual="absent",
                    program="ES",
                )
            )
        else:
            es_rt = (programs.get("ES") or {}).get("routines") or {}
            if safety.get("require_main_routine"):
                main = es_rt.get("Main_Routine") or {}
                if "Main_Routine" not in es_rt:
                    failures.append(
                        AuditFailure(
                            code="SAFETY_MISSING_MAIN_ROUTINE",
                            signature=failure_signature("SAFETY:MISSING_MAIN_ROUTINE"),
                            subsystem="SAFETY",
                            expected="ES/Main_Routine",
                            actual="absent",
                            program="ES",
                            routine="Main_Routine",
                        )
                    )
                elif not main.get("populated"):
                    failures.append(
                        AuditFailure(
                            code="SAFETY_BLANK_MAIN_ROUTINE",
                            signature=failure_signature("SAFETY:BLANK_MAIN_ROUTINE"),
                            subsystem="SAFETY",
                            expected="ES/Main_Routine populated with JSRs",
                            actual="empty/NOP-only",
                            program="ES",
                            routine="Main_Routine",
                        )
                    )
            zones = list(safety.get("zones") or [])
            if not zones and not any(
                k.endswith("_Safe_Logic") or k.endswith("_Safe_PI") for k in es_rt
            ):
                failures.append(
                    AuditFailure(
                        code="SAFETY_BLANK_ES_SHELL",
                        signature=failure_signature("SAFETY:BLANK_ES_SHELL"),
                        subsystem="SAFETY",
                        expected="operational Safe_Logic/Safe_PI",
                        actual="blank ES shell",
                        program="ES",
                    )
                )
            for z in zones:
                zname = str(z.get("name") or "")
                sl = str(z.get("require_safe_logic") or f"{zname}_Safe_Logic")
                sp = str(z.get("require_safe_pi") or f"{zname}_Safe_PI")
                if sl not in es_rt:
                    failures.append(
                        AuditFailure(
                            code="SAFETY_MISSING_SAFE_LOGIC",
                            signature=failure_signature(
                                "SAFETY:MISSING_SAFE_LOGIC", zone=zname
                            ),
                            subsystem="SAFETY",
                            expected=sl,
                            actual="absent",
                            program="ES",
                            routine=sl,
                            zone=zname,
                        )
                    )
                elif not (es_rt.get(sl) or {}).get("populated"):
                    failures.append(
                        AuditFailure(
                            code="SAFETY_EMPTY_SAFE_LOGIC",
                            signature=failure_signature(
                                "SAFETY:EMPTY_SAFE_LOGIC", zone=zname
                            ),
                            subsystem="SAFETY",
                            expected=f"{sl} populated",
                            actual="empty/NOP-only",
                            program="ES",
                            routine=sl,
                            zone=zname,
                        )
                    )
                if sp not in es_rt:
                    failures.append(
                        AuditFailure(
                            code="SAFETY_MISSING_SAFE_PI",
                            signature=failure_signature(
                                "SAFETY:MISSING_SAFE_PI", zone=zname
                            ),
                            subsystem="SAFETY",
                            expected=sp,
                            actual="absent",
                            program="ES",
                            routine=sp,
                            zone=zname,
                        )
                    )
                elif not (es_rt.get(sp) or {}).get("populated"):
                    failures.append(
                        AuditFailure(
                            code="SAFETY_EMPTY_SAFE_PI",
                            signature=failure_signature(
                                "SAFETY:EMPTY_SAFE_PI", zone=zname
                            ),
                            subsystem="SAFETY",
                            expected=f"{sp} populated",
                            actual="empty/NOP-only",
                            program="ES",
                            routine=sp,
                            zone=zname,
                        )
                    )
                # Main must JSR into Safe_Logic when zone expected
                if z.get("require_main_jsr", True) and "Main_Routine" in es_rt:
                    jsrs = (es_rt.get("Main_Routine") or {}).get("jsr_targets") or []
                    if sl in es_rt and sl not in jsrs:
                        failures.append(
                            AuditFailure(
                                code="SAFETY_MISSING_JSR",
                                signature=failure_signature(
                                    "JSR:MISSING", program="ES", extra=sl
                                ),
                                subsystem="SAFETY",
                                expected=f"JSR({sl})",
                                actual=f"JSRs={jsrs[:8]}",
                                program="ES",
                                routine="Main_Routine",
                                zone=zname,
                            )
                        )

    # --- Merges / Sorters (only if expected) ---
    if (manifest.get("merges") or {}).get("required"):
        # Soft structural check: at least one Merge-related tag or program content
        if not re.search(r"Merge|_Merge", text, re.I):
            failures.append(
                AuditFailure(
                    code="EQUIP_MISSING_MERGE",
                    signature=failure_signature("EQUIP:MISSING_MERGE"),
                    subsystem="TRANSPORTATION",
                    expected="merge architecture (discovered)",
                    actual="no Merge markers in L5X",
                )
            )
    if (manifest.get("sorters") or {}).get("required"):
        if "Sorter_Track" not in program_names and not re.search(
            r"Sorter", text, re.I
        ):
            failures.append(
                AuditFailure(
                    code="EQUIP_MISSING_SORTER",
                    signature=failure_signature("EQUIP:MISSING_SORTER"),
                    subsystem="TRANSPORTATION",
                    expected="sorter architecture (discovered)",
                    actual="no Sorter markers in L5X",
                )
            )

    # --- Blank / question operands ---
    if manifest.get("reject_blank_operands", True):
        for i, m in enumerate(_BLANK_OPERAND_RE.finditer(text)):
            if i >= 25:
                break
            failures.append(
                AuditFailure(
                    code="LOGIX_BLANK_OPERAND",
                    signature=failure_signature(
                        "LOGIX:BLANK_OPERAND", extra=m.group(0)[:40]
                    ),
                    subsystem="POST_BUILD",
                    expected="valid Logix operand",
                    actual=m.group(0)[:80],
                )
            )
    if manifest.get("reject_question_operands", True):
        for i, m in enumerate(_QUESTION_OPERAND_RE.finditer(text)):
            if i >= 15:
                break
            failures.append(
                AuditFailure(
                    code="LOGIX_QUESTION_OPERAND",
                    signature=failure_signature(
                        "LOGIX:QUESTION_OPERAND", extra=m.group(0)[:40]
                    ),
                    subsystem="POST_BUILD",
                    expected="resolved operand",
                    actual=m.group(0)[:80],
                )
            )
    if manifest.get("reject_unnamed_tags", True):
        for i, m in enumerate(_UNNAMED_TAG_RE.finditer(text)):
            if i >= 10:
                break
            failures.append(
                AuditFailure(
                    code="TAG_UNNAMED",
                    signature=failure_signature("TAG:UNNAMED", extra=str(i)),
                    subsystem="POST_BUILD",
                    expected="named tag",
                    actual=m.group(0)[:80],
                )
            )

    # --- Foreign-site residue ---
    for token in manifest.get("foreign_site_forbid") or []:
        # Hard-fail on Program/Routine/Tag names that embed the foreign token.
        prog_hits = len(re.findall(rf'<Program Name="[^"]*{re.escape(token)}[^"]*"', text))
        zone_hits = len(
            re.findall(rf'Routine Name="[^"]*{re.escape(token)}[^"]*"', text)
        )
        name_hits = len(re.findall(rf'\bName="[^"]*{re.escape(token)}[^"]*"', text))
        total = prog_hits + zone_hits + name_hits
        if total > 0:
            failures.append(
                AuditFailure(
                    code="RESIDUE_FOREIGN_SITE",
                    signature=failure_signature("RESIDUE:FOREIGN_SITE", extra=token),
                    subsystem="POST_BUILD",
                    expected=f"zero references to {token}",
                    actual=f"hits={total}",
                    detail={
                        "program_hits": prog_hits,
                        "zone_hits": zone_hits,
                        "name_hits": name_hits,
                    },
                )
            )

    status = STATE_AUDIT_PASS if not failures else STATE_AUDIT_FAIL
    return {
        "status": status,
        "ok": status == STATE_AUDIT_PASS,
        "failures": [f.to_dict() for f in failures],
        "failure_count": len(failures),
        "signatures": [f.signature for f in failures],
        "l5x": str(path.resolve()),
        "l5x_sha256": sha256_file(path),
        "machine": machine,
        "programs_found": sorted(program_names),
        "audited_at": _ts(),
    }


# ---------------------------------------------------------------------------
# Repair tickets + loop protection
# ---------------------------------------------------------------------------


@dataclass
class RepairAttempt:
    signature: str
    material_hash: str
    level: int
    disposition: str
    ts: str
    ai: dict[str, Any] | None = None
    relay: dict[str, Any] | None = None
    validator: dict[str, Any] | None = None
    l5x_sha256: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "material_hash": self.material_hash,
            "level": self.level,
            "disposition": self.disposition,
            "ts": self.ts,
            "ai": self.ai,
            "relay": self.relay,
            "validator": self.validator,
            "l5x_sha256": self.l5x_sha256,
            "note": self.note,
        }


class RepairLoopState:
    def __init__(self, max_per_signature: int = MAX_ATTEMPTS_PER_SIGNATURE) -> None:
        self.max_per_signature = max_per_signature
        self.attempts_by_signature: dict[str, list[RepairAttempt]] = {}
        self.tickets: list[dict[str, Any]] = []
        self.generator_defect_cases: list[dict[str, Any]] = []

    def can_retry(self, signature: str, mat_hash: str) -> tuple[bool, str]:
        attempts = self.attempts_by_signature.get(signature) or []
        for a in attempts:
            if a.material_hash == mat_hash:
                return False, "DUPLICATE_MATERIAL_HASH"
        distinct = {a.material_hash for a in attempts}
        if len(distinct) >= self.max_per_signature:
            return False, "MAX_MATERIAL_ATTEMPTS"
        return True, "OK"

    def record(self, attempt: RepairAttempt) -> None:
        self.attempts_by_signature.setdefault(attempt.signature, []).append(attempt)

    def exhausted(self, signature: str) -> bool:
        attempts = self.attempts_by_signature.get(signature) or []
        return len({a.material_hash for a in attempts}) >= self.max_per_signature

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_per_signature": self.max_per_signature,
            "tickets": self.tickets,
            "attempts_by_signature": {
                k: [a.to_dict() for a in v]
                for k, v in self.attempts_by_signature.items()
            },
            "generator_defect_cases": self.generator_defect_cases,
        }


def make_repair_ticket(
    failure: dict[str, Any],
    *,
    manifest: dict[str, Any],
    build_sha: str,
    run_sha: str,
    attempt_n: int,
) -> dict[str, Any]:
    return {
        "ori": "ORI-111",
        "kind": "REPAIR_TICKET",
        "created_at": _ts(),
        "failure_code": failure.get("code"),
        "signature": failure.get("signature"),
        "expected_object": failure.get("expected"),
        "actual_object": failure.get("actual"),
        "program": failure.get("program"),
        "routine": failure.get("routine"),
        "rung": failure.get("rung"),
        "zone": failure.get("zone"),
        "subsystem": failure.get("subsystem"),
        "build_sha": build_sha,
        "run_sha": run_sha,
        "previous_repair_attempts": attempt_n,
        "detail": failure.get("detail") or {},
        "manifest_machine": manifest.get("machine"),
    }


def write_generator_defect_case(
    out_dir: Path,
    *,
    manifest: dict[str, Any],
    signature: str,
    tickets: list[dict[str, Any]],
    attempts: list[RepairAttempt],
    l5x_paths: list[Path],
    ai_responses: list[Any],
    relay_responses: list[Any],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    case = {
        "ori": "ORI-111",
        "classification": "GENERATOR_DEFECT",
        "created_at": _ts(),
        "signature": signature,
        "message": (
            f"Same failure signature survived {len({a.material_hash for a in attempts})} "
            "materially different repair attempts. Stop auto-rebuild; fix generator."
        ),
        "expected_manifest": manifest,
        "tickets": tickets,
        "attempts": [a.to_dict() for a in attempts],
        "l5x_paths": [str(p) for p in l5x_paths],
        "l5x_sha256": [sha256_file(p) for p in l5x_paths if p.is_file()],
        "ai_responses": ai_responses,
        "relay_responses": relay_responses,
        "git_sha": _git_sha(),
    }
    # Diffs between consecutive L5Xs (size + simple hash delta)
    diffs = []
    for i in range(1, len(l5x_paths)):
        a, b = l5x_paths[i - 1], l5x_paths[i]
        diffs.append(
            {
                "from": str(a),
                "to": str(b),
                "from_sha": sha256_file(a) if a.is_file() else "",
                "to_sha": sha256_file(b) if b.is_file() else "",
                "from_bytes": a.stat().st_size if a.is_file() else 0,
                "to_bytes": b.stat().st_size if b.is_file() else 0,
            }
        )
    case["artifact_diffs"] = diffs
    path = out_dir / f"GENERATOR_DEFECT_{signature.replace(':', '_')[:80]}.json"
    path.write_text(json.dumps(case, indent=2, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Repair via ORI-111 escalation
# ---------------------------------------------------------------------------


def _subsystem_for_failure(failure: dict[str, Any]) -> str:
    return str(failure.get("subsystem") or "POST_BUILD").upper()


def repair_from_audit_ticket(
    ticket: dict[str, Any],
    *,
    case_file: Any | None = None,
    live: bool = True,
) -> dict[str, Any]:
    """Escalate one REPAIR_TICKET through deterministic → AI → Relay.

    Returns a proposal dict. Does NOT invent Safety membership.
    """
    from fortna_build_escalation import (
        BuildCaseFile,
        LEVEL_AI_API,
        LEVEL_DETERMINISTIC,
        LEVEL_ENGINEER,
        LEVEL_RELAY,
        call_ai_api_for_case,
        call_relay_freeform,
        evidence_signature,
    )

    if case_file is None:
        case_file = BuildCaseFile(
            site=str(ticket.get("manifest_machine") or "UNKNOWN"),
            machine=str(ticket.get("manifest_machine") or "UNKNOWN"),
            run_sha=str(ticket.get("run_sha") or ""),
            build_id=str(ticket.get("build_sha") or "audit-repair"),
        )

    evidence = {
        "subsystem": _subsystem_for_failure(ticket),
        "defect_kind": ticket.get("failure_code") or ticket.get("signature"),
        "device": ticket.get("zone") or ticket.get("program") or ticket.get("signature"),
        "program": ticket.get("program"),
        "routine": ticket.get("routine"),
        "why_uncertain": (
            f"AUDIT_FAIL {ticket.get('signature')}: expected={ticket.get('expected_object')} "
            f"actual={ticket.get('actual_object')}"
        ),
        "site_forge_attempt": "L5X acceptance auditor expected-vs-actual",
        "expected": ticket.get("expected_object"),
        "actual": ticket.get("actual_object"),
        "previous_repair_attempts": ticket.get("previous_repair_attempts"),
        "audit_ticket": ticket,
    }

    # LEVEL 0 — deterministic diagnosis
    code = str(ticket.get("failure_code") or "")
    proposal: dict[str, Any] = {
        "ok": False,
        "level": LEVEL_DETERMINISTIC,
        "disposition": "UNRESOLVED",
        "actions": [],
        "requires_generator_fix": False,
        "requires_engineer": False,
        "evidence": evidence,
    }

    # Deterministic classifications that are clearly generator defects
    if code in (
        "SAFETY_MISSING_SAFE_LOGIC",
        "SAFETY_MISSING_SAFE_PI",
        "SAFETY_EMPTY_SAFE_LOGIC",
        "SAFETY_EMPTY_SAFE_PI",
        "SAFETY_BLANK_MAIN_ROUTINE",
        "SAFETY_BLANK_ES_SHELL",
        "TRANSPORT_EMPTY_CORE",
        "TRANSPORT_MISSING_PROGRAM",
        "IO_MISSING_PROGRAM",
    ):
        proposal["actions"].append(
            {
                "type": "GENERATOR_OR_MODEL_REPAIR",
                "hint": (
                    "Expected object missing/empty in L5X despite resolved model. "
                    "Likely emitter skipped required routine or model not applied."
                ),
            }
        )
        proposal["requires_generator_fix"] = True
        proposal["disposition"] = "DIAGNOSED_GENERATOR_CANDIDATE"

    if not live:
        proposal["ok"] = False
        proposal["disposition"] = "LIVE_DISABLED"
        return proposal

    # LEVEL 1 — AI API
    ai = call_ai_api_for_case(evidence, case_file=case_file)
    proposal["ai"] = {
        "ok": ai.get("ok"),
        "response": ai.get("response"),
        "error": ai.get("error"),
    }
    proposal["level"] = LEVEL_AI_API
    ai_resp = ai.get("response") if isinstance(ai.get("response"), dict) else {}

    # Never accept invented Safety membership
    if "SAFETY" in code and ai_resp:
        members = ai_resp.get("proposed_members") or ai_resp.get("members")
        if members and not ticket.get("detail", {}).get("allow_invent_membership"):
            proposal["validator"] = {
                "ok": False,
                "reason": "AI proposed Safety membership — rejected (PROVEN/ENGINEER_ASSIGNED only)",
            }
            ai_resp = {}

    # LEVEL 2 — Relay if AI insufficient
    need_relay = (not ai.get("ok")) or not ai_resp or proposal.get("requires_generator_fix")
    relay_result = None
    if need_relay:
        relay_result = call_relay_freeform(
            evidence,
            case_file=case_file,
            ai_response=ai_resp or ai.get("response"),
            purpose="l5x_acceptance_audit_repair",
        )
        proposal["relay"] = {
            "ok": relay_result.get("ok"),
            "result": relay_result.get("result"),
            "error": relay_result.get("error"),
        }
        proposal["level"] = LEVEL_RELAY

    # Interpret advisory answers into actionable dispositions
    advisory = {}
    if isinstance(ai_resp, dict) and ai_resp:
        advisory = ai_resp
    relay_body = (relay_result or {}).get("result") if relay_result else None
    if isinstance(relay_body, dict) and relay_body:
        advisory = {**advisory, **relay_body}

    classification = str(
        advisory.get("classification")
        or advisory.get("root_cause")
        or advisory.get("candidate_resolution")
        or ""
    ).upper()

    if "GENERATOR" in classification or proposal.get("requires_generator_fix"):
        proposal["disposition"] = "GENERATOR_DEFECT_CANDIDATE"
        proposal["requires_generator_fix"] = True
        proposal["ok"] = False
    elif "ENGINEER" in classification or advisory.get("confidence") in (
        "REVIEW_REQUIRED",
        "INSUFFICIENT",
    ):
        proposal["disposition"] = "ENGINEER_REQUIRED"
        proposal["requires_engineer"] = True
        proposal["level"] = LEVEL_ENGINEER
        proposal["ok"] = False
    elif advisory.get("recommended_resolution") or advisory.get("candidate_resolution"):
        proposal["disposition"] = "ADVISORY_REPAIR"
        proposal["recommended_resolution"] = (
            advisory.get("recommended_resolution")
            or advisory.get("candidate_resolution")
        )
        # Advisory alone cannot mutate L5X — mark as needing model apply + regenerate
        proposal["actions"].append(
            {
                "type": "APPLY_MODEL_HINT_AND_REGENERATE",
                "resolution": proposal["recommended_resolution"],
            }
        )
        proposal["ok"] = False  # still requires regenerate+re-audit to prove
    else:
        proposal["disposition"] = "UNRESOLVED"
        proposal["ok"] = False

    proposal["evidence_signature"] = evidence_signature(evidence)
    return proposal


# ---------------------------------------------------------------------------
# Full acceptance + repair orchestration
# ---------------------------------------------------------------------------


def run_acceptance_and_repair(
    *,
    l5x_path: Path | str,
    manifest: dict[str, Any],
    report: dict[str, Any] | None = None,
    out_dir: Path | str | None = None,
    regenerate_fn: Callable[[dict[str, Any]], Path | None] | None = None,
    case_file: Any | None = None,
    live: bool | None = None,
    max_outer_cycles: int = MAX_OUTER_REPAIR_CYCLES,
) -> dict[str, Any]:
    """Audit staging L5X; on fail, escalate/repair/regenerate/re-audit.

    `regenerate_fn(repair_context) -> new_l5x_path | None`
    If regenerate_fn is None, repair proposals are recorded but no rebuild occurs
    (AUDIT_FAIL stands; useful for unit tests).
    """
    if not auditor_enabled():
        return {
            "status": STATE_AUDIT_PASS,
            "ok": True,
            "disabled": True,
            "note": "SITEFORGE_L5X_AUDITOR=0",
        }

    report = report if isinstance(report, dict) else {}
    path = Path(l5x_path)
    out = Path(out_dir) if out_dir else path.parent
    out.mkdir(parents=True, exist_ok=True)
    live_flag = (
        bool(live)
        if live is not None
        else (os.environ.get("SITEFORGE_ESCALATION") or "1").strip()
        not in ("0", "false", "OFF")
    )

    # Persist expected manifest
    man_path = out / "EXPECTED_ARTIFACT_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    loop = RepairLoopState()
    l5x_history: list[Path] = [path]
    ai_log: list[Any] = []
    relay_log: list[Any] = []
    initial_audit = audit_l5x(path, manifest)
    audits = [initial_audit]
    artifact_state = STATE_STAGING

    result: dict[str, Any] = {
        "ori": "ORI-111",
        "artifact_state": artifact_state,
        "initial_audit": initial_audit,
        "audits": audits,
        "manifest_path": str(man_path),
        "promoted": False,
        "ai_api_calls": 0,
        "relay_calls": 0,
        "estimated_cost_usd": 0.0,
        "generator_defect": False,
        "engineer_required": False,
        "loop": loop.to_dict(),
    }

    if initial_audit.get("ok"):
        result["status"] = STATE_AUDIT_PASS
        result["ok"] = True
        result["artifact_state"] = STATE_AUDIT_PASS
        result["final_audit"] = initial_audit
        (out / "l5x_acceptance_audit.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        return result

    result["status"] = STATE_AUDIT_FAIL
    result["ok"] = False
    result["artifact_state"] = STATE_AUDIT_FAIL

    # Repair cycles
    current_path = path
    for cycle in range(max_outer_cycles):
        audit = audits[-1]
        if audit.get("ok"):
            break
        result["artifact_state"] = STATE_REPAIRING
        failures = list(audit.get("failures") or [])
        cycle_progress = False
        pending_regen_hints: list[dict[str, Any]] = []

        for fail in failures:
            sig = str(fail.get("signature") or "")
            ticket = make_repair_ticket(
                fail,
                manifest=manifest,
                build_sha=str(manifest.get("git_sha") or _git_sha()),
                run_sha=str(manifest.get("run_sha") or ""),
                attempt_n=len(loop.attempts_by_signature.get(sig) or []),
            )
            loop.tickets.append(ticket)

            # Material context before calling AI
            pre_mat = material_hash(
                {
                    "signature": sig,
                    "cycle": cycle,
                    "expected": fail.get("expected"),
                    "actual": fail.get("actual"),
                    "l5x_sha": audit.get("l5x_sha256"),
                }
            )
            ok_retry, why = loop.can_retry(sig, pre_mat)
            if not ok_retry and why == "DUPLICATE_MATERIAL_HASH":
                continue
            if not ok_retry and why == "MAX_MATERIAL_ATTEMPTS":
                case_path = write_generator_defect_case(
                    out,
                    manifest=manifest,
                    signature=sig,
                    tickets=[t for t in loop.tickets if t.get("signature") == sig],
                    attempts=loop.attempts_by_signature.get(sig) or [],
                    l5x_paths=l5x_history,
                    ai_responses=ai_log,
                    relay_responses=relay_log,
                )
                loop.generator_defect_cases.append({"signature": sig, "path": str(case_path)})
                result["generator_defect"] = True
                result["status"] = STATE_GENERATOR_DEFECT
                result["artifact_state"] = STATE_GENERATOR_DEFECT
                result["generator_defect_case"] = str(case_path)
                result["loop"] = loop.to_dict()
                (out / "l5x_acceptance_audit.json").write_text(
                    json.dumps(result, indent=2, default=str), encoding="utf-8"
                )
                return result

            proposal = repair_from_audit_ticket(
                ticket, case_file=case_file, live=live_flag
            )
            if proposal.get("ai"):
                ai_log.append(proposal.get("ai"))
                result["ai_api_calls"] = int(result["ai_api_calls"]) + 1
            if proposal.get("relay"):
                relay_log.append(proposal.get("relay"))
                result["relay_calls"] = int(result["relay_calls"]) + 1

            mat = material_hash(
                {
                    "signature": sig,
                    "cycle": cycle,
                    "disposition": proposal.get("disposition"),
                    "ai": (proposal.get("ai") or {}).get("response"),
                    "relay": (proposal.get("relay") or {}).get("result"),
                    "actions": proposal.get("actions"),
                }
            )
            # If material collides with prior, bump with attempt index
            ok_retry2, why2 = loop.can_retry(sig, mat)
            if not ok_retry2 and why2 == "DUPLICATE_MATERIAL_HASH":
                mat = material_hash({**{"base": mat}, "n": len(loop.attempts_by_signature.get(sig) or [])})
                ok_retry2, why2 = loop.can_retry(sig, mat)
            if not ok_retry2 and why2 == "MAX_MATERIAL_ATTEMPTS":
                case_path = write_generator_defect_case(
                    out,
                    manifest=manifest,
                    signature=sig,
                    tickets=[t for t in loop.tickets if t.get("signature") == sig],
                    attempts=loop.attempts_by_signature.get(sig) or [],
                    l5x_paths=l5x_history,
                    ai_responses=ai_log,
                    relay_responses=relay_log,
                )
                loop.generator_defect_cases.append({"signature": sig, "path": str(case_path)})
                result["generator_defect"] = True
                result["status"] = STATE_GENERATOR_DEFECT
                result["artifact_state"] = STATE_GENERATOR_DEFECT
                result["generator_defect_case"] = str(case_path)
                result["loop"] = loop.to_dict()
                (out / "l5x_acceptance_audit.json").write_text(
                    json.dumps(result, indent=2, default=str), encoding="utf-8"
                )
                return result

            attempt = RepairAttempt(
                signature=sig,
                material_hash=mat,
                level=int(proposal.get("level") or 0),
                disposition=str(proposal.get("disposition") or ""),
                ts=_ts(),
                ai=proposal.get("ai"),
                relay=proposal.get("relay"),
                validator=proposal.get("validator"),
                l5x_sha256=str(audit.get("l5x_sha256") or ""),
                note=str(proposal.get("recommended_resolution") or "")[:300],
            )
            loop.record(attempt)

            if proposal.get("requires_engineer"):
                result["engineer_required"] = True

            if proposal.get("requires_generator_fix") and loop.exhausted(sig):
                case_path = write_generator_defect_case(
                    out,
                    manifest=manifest,
                    signature=sig,
                    tickets=[t for t in loop.tickets if t.get("signature") == sig],
                    attempts=loop.attempts_by_signature.get(sig) or [],
                    l5x_paths=l5x_history,
                    ai_responses=ai_log,
                    relay_responses=relay_log,
                )
                loop.generator_defect_cases.append({"signature": sig, "path": str(case_path)})
                result["generator_defect"] = True
                result["status"] = STATE_GENERATOR_DEFECT
                result["artifact_state"] = STATE_GENERATOR_DEFECT
                result["generator_defect_case"] = str(case_path)
                result["loop"] = loop.to_dict()
                (out / "l5x_acceptance_audit.json").write_text(
                    json.dumps(result, indent=2, default=str), encoding="utf-8"
                )
                return result

            pending_regen_hints.append(
                {"ticket": ticket, "proposal": proposal, "signature": sig}
            )
            cycle_progress = True

        if not cycle_progress or regenerate_fn is None:
            break

        # Attempt regenerate with repair context
        new_path = regenerate_fn(
            {
                "cycle": cycle,
                "hints": pending_regen_hints,
                "manifest": manifest,
                "prior_l5x": str(current_path),
            }
        )
        if not new_path:
            # No regenerate possible — stop with AUDIT_FAIL / possible engineer
            break
        new_path = Path(new_path)
        if new_path.is_file():
            # Keep history copy
            hist = out / f"staging_attempt_{cycle + 1}_{new_path.name}"
            try:
                shutil.copy2(new_path, hist)
                l5x_history.append(hist)
            except Exception:
                l5x_history.append(new_path)
            current_path = new_path
            re_audit = audit_l5x(current_path, manifest)
            audits.append(re_audit)
            if re_audit.get("ok"):
                result["status"] = STATE_AUDIT_PASS
                result["ok"] = True
                result["artifact_state"] = STATE_AUDIT_PASS
                result["final_audit"] = re_audit
                result["l5x"] = str(current_path.resolve())
                break
        else:
            break

    if result.get("status") != STATE_AUDIT_PASS:
        if result.get("engineer_required"):
            result["status"] = STATE_ENGINEER_REQUIRED
            result["artifact_state"] = STATE_ENGINEER_REQUIRED
        elif result.get("generator_defect"):
            result["status"] = STATE_GENERATOR_DEFECT
        else:
            result["status"] = STATE_AUDIT_FAIL
            result["artifact_state"] = STATE_AUDIT_FAIL
        result["ok"] = False
        result["final_audit"] = audits[-1]

    # Cost accounting (rough; mirrors escalation module defaults)
    result["estimated_cost_usd"] = round(
        float(result.get("ai_api_calls") or 0) * 0.15
        + float(result.get("relay_calls") or 0) * 0.25,
        4,
    )
    result["loop"] = loop.to_dict()
    result["repair_cycles"] = max(0, len(audits) - 1)
    result["l5x_history"] = [str(p) for p in l5x_history]
    (out / "l5x_acceptance_audit.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result
