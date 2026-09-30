#!/usr/bin/env python3
"""ORI-075 CURRENT-RUN equipment fidelity classes.

Distinguish plant RUN evidence from active local generation membership.

Classes (mutually exclusive primary label):
  RAW_EVIDENCE_ROW          — retained plant row without stronger class
  LOCAL_ACTIVE_EQUIPMENT    — current-machine ownership + active proof
  FOREIGN_EQUIPMENT         — explicit other-controller ownership
  UNKNOWN_OWNER             — mechanical/candidate without proven owner
  TEMPLATE_GRAPHICAL_ONLY   — HMI TITLE/IMAGE (not active equipment)

Rules:
  - Never delete raw RUN rows to clean counts — classify + retain.
  - HMI graphical presence is NOT active equipment proof.
  - Active membership requires Machine_Name match, MergeBoss Owner,
    topology / physical I/O / machine-local config linkage.
  - Do NOT hardcode site conveyor names; use controller/machine ownership.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from fortna_asc import CONVEYOR_TYPES, read_asc
from fortna_io_extract import row_machine_matches
from fortna_machine_scoped_run import (
    NA_TOKENS,
    explicit_machine_name,
    is_explicit_foreign_machine,
)
from fortna_project_identity import normalize_machine_token
from fortna_site_model import normalize_name

RAW_EVIDENCE_ROW = "RAW_EVIDENCE_ROW"
LOCAL_ACTIVE_EQUIPMENT = "LOCAL_ACTIVE_EQUIPMENT"
FOREIGN_EQUIPMENT = "FOREIGN_EQUIPMENT"
UNKNOWN_OWNER = "UNKNOWN_OWNER"
TEMPLATE_GRAPHICAL_ONLY = "TEMPLATE_GRAPHICAL_ONLY"

FIDELITY_CLASSES = (
    RAW_EVIDENCE_ROW,
    LOCAL_ACTIVE_EQUIPMENT,
    FOREIGN_EQUIPMENT,
    UNKNOWN_OWNER,
    TEMPLATE_GRAPHICAL_ONLY,
)

# HMI / drawing-only Conveyor.asc types — never generation membership.
GRAPHICAL_TYPES = frozenset({"TITLE", "IMAGE", "LOGIN", "LOGOUT", "USER", "SYSTEM"})
MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {
    "ZEROPRESSURE",
    "ACCUMULATOR",
    "MDR",
    "BELT",
    "CURVE",
    "SPUR",
    "STRAIGHT",
    "TRIANG",
    "MERGE",
    "SKEW",
    "ACCUM",
}
P_TAG_RE = re.compile(r"^P\d{2,4}[A-Z0-9_]*$", re.I)
DEVICE_TO_P = (
    re.compile(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I),
    re.compile(r"^VFD[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I),
    re.compile(r"^M[\s\-_]*(\d{2,4}[A-Za-z]?)", re.I),
)
MOTOR_STATUS_SUFFIX = re.compile(r"(_AUX|_OL|_FLT|_RUN|_OK)$", re.I)


def may_generate(fidelity_class: str) -> bool:
    """Only LOCAL_ACTIVE_EQUIPMENT enters Area / Safety / PLC generation."""
    return (fidelity_class or "").strip().upper() == LOCAL_ACTIVE_EQUIPMENT


def is_graphical_type(typ: str) -> bool:
    t = (typ or "").strip().upper()
    if not t:
        return False
    if t in GRAPHICAL_TYPES:
        return True
    # Prefix forms seen in junk catalogs (USER / SYSTEM banners)
    return any(t.startswith(g + " ") for g in GRAPHICAL_TYPES)


def _p_from_device(name: str) -> str:
    n = name or ""
    for rx in DEVICE_TO_P:
        m = rx.match(n)
        if m:
            return ("P" + m.group(1)).upper()
    return ""


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _fortna_dir(run_dir: Path) -> Path:
    run_dir = _normalize_run_dir(run_dir)
    for c in (run_dir / "FORTNA", run_dir):
        if c.is_dir() and (
            (c / "Conveyor.asc").is_file() or any(c.glob("Conveyor.asc*"))
        ):
            return c
    return run_dir / "FORTNA"


def _load_merge_boss_owners(fortna: Path, machine: str) -> dict[str, set[str]]:
    """Map conveyor P-tag → MergeBoss Owner set (controller tokens).

    MergeBoss Name often encodes lane pairs like P15-P72; Owner is the
    controlling machine. Used as machine-local config proof, not HMI proof.
    """
    out: dict[str, set[str]] = {}
    paths: list[Path] = []
    overlay = fortna / f"MergeBoss.asc.{machine}"
    base = fortna / "MergeBoss.asc"
    if overlay.is_file():
        paths.append(overlay)
    elif base.is_file():
        paths.append(base)
    for path in paths:
        try:
            _h, rows = read_asc(path)
        except Exception:
            continue
        for r in rows:
            name = normalize_name(r.get("Name") or "")
            owner = explicit_machine_name(r) or normalize_name(r.get("Owner") or "")
            if not name or name in NA_TOKENS:
                continue
            if not owner or owner in NA_TOKENS:
                continue
            for tok in re.findall(r"P\d{2,4}[A-Za-z]?", name, flags=re.I):
                key = tok.upper()
                out.setdefault(key, set()).add(owner)
    return out


def _linked_local_tags(rows: list[dict[str, str]], machine: str) -> set[str]:
    """P-tags proven local via PE / VFD / motor Machine_Name on this controller."""
    linked: set[str] = set()
    for r in rows:
        name = normalize_name(r.get("IO_Name") or r.get("Name") or "")
        if not name:
            continue
        if is_explicit_foreign_machine(r, machine):
            continue
        explicit = explicit_machine_name(r)
        if not explicit or not row_machine_matches(explicit, machine):
            continue
        if MOTOR_STATUS_SUFFIX.search(name):
            name = MOTOR_STATUS_SUFFIX.sub("", name)
        p = _p_from_device(name)
        if p:
            linked.add(p)
            parent = re.match(r"^(P\d{2,4})[A-Z]$", p)
            if parent:
                linked.add(parent.group(1))
    return linked


def classify_conveyor_fidelity_row(
    row: dict[str, Any],
    machine: str,
    *,
    linked_local: set[str] | None = None,
    merge_owners: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Classify one Conveyor.asc row for ORI-075 fidelity."""
    machine = normalize_machine_token(machine)
    name = normalize_name(row.get("IO_Name") or row.get("Name") or "")
    typ = normalize_name(row.get("Type") or "")
    explicit = explicit_machine_name(row)
    reasons: list[str] = []
    retained = True  # never delete raw RUN evidence to clean counts

    if not name or name in {"INVALID", "SPARE", "ALWAYSON", "NEVERON"}:
        return {
            "identity": name or None,
            "fidelity_class": RAW_EVIDENCE_ROW,
            "retained_as_evidence": retained,
            "may_generate": False,
            "machine_name": explicit or "",
            "type": typ,
            "reasons": ["placeholder_or_absent_identity"],
        }

    if is_graphical_type(typ):
        reasons.append(f"graphical_type:{typ}")
        return {
            "identity": name,
            "fidelity_class": TEMPLATE_GRAPHICAL_ONLY,
            "retained_as_evidence": retained,
            "may_generate": False,
            "machine_name": explicit or "",
            "type": typ,
            "reasons": reasons,
        }

    if explicit and is_explicit_foreign_machine(row, machine):
        reasons.append(f"explicit_foreign_machine:{explicit}")
        return {
            "identity": name,
            "fidelity_class": FOREIGN_EQUIPMENT,
            "retained_as_evidence": retained,
            "may_generate": False,
            "machine_name": explicit,
            "type": typ,
            "reasons": reasons,
        }

    local_proof = False
    if explicit and row_machine_matches(explicit, machine):
        local_proof = True
        reasons.append(f"explicit_machine_name:{explicit}")

    linked_local = linked_local or set()
    if name in linked_local or (
        P_TAG_RE.match(name) and name.upper() in {t.upper() for t in linked_local}
    ):
        local_proof = True
        reasons.append("linked_local_device_io")

    merge_owners = merge_owners or {}
    owners = merge_owners.get(name.upper()) or merge_owners.get(name) or set()
    if owners:
        if any(row_machine_matches(o, machine) for o in owners):
            local_proof = True
            reasons.append(f"mergeboss_owner:{sorted(owners)}")
        elif all(
            o and normalize_name(o) not in NA_TOKENS and not row_machine_matches(o, machine)
            for o in owners
        ):
            reasons.append(f"mergeboss_foreign_owner:{sorted(owners)}")
            return {
                "identity": name,
                "fidelity_class": FOREIGN_EQUIPMENT,
                "retained_as_evidence": retained,
                "may_generate": False,
                "machine_name": explicit or sorted(owners)[0],
                "type": typ,
                "reasons": reasons,
            }

    is_mech = typ in MECH_TYPES and bool(P_TAG_RE.match(name))
    if local_proof and (is_mech or typ in MECH_TYPES or P_TAG_RE.match(name)):
        return {
            "identity": name,
            "fidelity_class": LOCAL_ACTIVE_EQUIPMENT,
            "retained_as_evidence": retained,
            "may_generate": True,
            "machine_name": explicit or machine,
            "type": typ,
            "reasons": reasons,
        }

    if is_mech or (P_TAG_RE.match(name) and typ not in GRAPHICAL_TYPES):
        reasons.append("mechanical_or_ptag_without_owner_proof")
        return {
            "identity": name,
            "fidelity_class": UNKNOWN_OWNER,
            "retained_as_evidence": retained,
            "may_generate": False,
            "machine_name": explicit or "",
            "type": typ,
            "reasons": reasons,
        }

    reasons.append("raw_catalog_row")
    return {
        "identity": name,
        "fidelity_class": RAW_EVIDENCE_ROW,
        "retained_as_evidence": retained,
        "may_generate": False,
        "machine_name": explicit or "",
        "type": typ,
        "reasons": reasons,
    }


def classify_run_equipment_fidelity(
    run_dir: Path | str,
    machine: str = "",
) -> dict[str, Any]:
    """Classify every Conveyor.asc row for the target machine. RUN-only."""
    run_dir = _normalize_run_dir(Path(run_dir))
    if not machine:
        try:
            from fortna_project_identity import identity_from_run

            machine = identity_from_run(run_dir).machine
        except Exception:
            machine = ""
    machine = normalize_machine_token(machine)
    fortna = _fortna_dir(run_dir)
    conv_path = next(iter(sorted(fortna.glob("Conveyor.asc*"))), fortna / "Conveyor.asc")
    if not conv_path.is_file():
        return {
            "machine": machine,
            "run_dir": str(run_dir),
            "counts": {c: 0 for c in FIDELITY_CLASSES},
            "rows": [],
            "by_class": {c: [] for c in FIDELITY_CLASSES},
            "error": f"missing {conv_path}",
        }

    _h, rows = read_asc(conv_path)
    linked = _linked_local_tags(rows, machine) if machine else set()
    merge_owners = _load_merge_boss_owners(fortna, machine) if machine else {}

    classified: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    by_class: dict[str, list[str]] = {c: [] for c in FIDELITY_CLASSES}
    seen: set[str] = set()

    for r in rows:
        info = classify_conveyor_fidelity_row(
            r,
            machine,
            linked_local=linked,
            merge_owners=merge_owners,
        )
        ident = info.get("identity")
        if not ident:
            continue
        key = str(ident).upper()
        # Prefer first geometric / catalog occurrence; still count as retained.
        if key in seen:
            continue
        seen.add(key)
        cls = info["fidelity_class"]
        counts[cls] += 1
        by_class.setdefault(cls, []).append(str(ident))
        classified.append(info)

    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "CURRENT RUN (Conveyor.asc + MergeBoss Owner + device Machine_Name)",
        "policy": {
            "ori": "ORI-075",
            "retain_raw_rows": True,
            "graphical_not_active": True,
            "no_site_name_hardcode": True,
            "generation_requires_local_active": True,
        },
        "counts": {c: int(counts.get(c, 0)) for c in FIDELITY_CLASSES},
        "counts_total_retained": len(classified),
        "by_class": by_class,
        "local_active_tags": list(by_class.get(LOCAL_ACTIVE_EQUIPMENT) or []),
        "foreign_tags": list(by_class.get(FOREIGN_EQUIPMENT) or []),
        "graphical_tags": list(by_class.get(TEMPLATE_GRAPHICAL_ONLY) or []),
        "rows": classified,
    }


def fidelity_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """identity.upper() → classification row."""
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        ident = normalize_name(row.get("identity") or "")
        if ident:
            out[ident] = row
    return out


def annotate_workbook_conveyors(
    workbook: dict[str, Any],
    fidelity: dict[str, Any] | None = None,
    *,
    run_dir: Path | str | None = None,
    machine: str = "",
) -> dict[str, Any]:
    """Stamp fidelity_class on workbook conveyors; demote non-local from generation.

    Foreign / graphical / unknown rows are retained (not deleted) with
    include=False so they cannot enter Area / Safety / PLC emission.
    """
    wb = workbook
    machine = normalize_machine_token(
        machine or str(wb.get("machine") or wb.get("controller") or "")
    )
    if fidelity is None:
        rd = run_dir or wb.get("run_dir") or wb.get("runDir")
        if rd and machine:
            fidelity = classify_run_equipment_fidelity(rd, machine)
        else:
            fidelity = {"rows": [], "by_class": {}}
    lookup = fidelity_lookup(fidelity)
    demoted: list[str] = []
    for row in wb.get("conveyors") or []:
        tag = normalize_name(row.get("conveyor") or "")
        if not tag:
            continue
        info = lookup.get(tag)
        # Explicit foreign Machine_Name on the workbook row itself
        if not info and is_explicit_foreign_machine(row, machine):
            info = {
                "fidelity_class": FOREIGN_EQUIPMENT,
                "may_generate": False,
                "retained_as_evidence": True,
                "reasons": ["workbook_explicit_foreign_machine"],
            }
        if not info:
            # Graphical type on workbook row
            if is_graphical_type(str(row.get("type") or row.get("asc_type") or "")):
                info = {
                    "fidelity_class": TEMPLATE_GRAPHICAL_ONLY,
                    "may_generate": False,
                    "retained_as_evidence": True,
                    "reasons": ["workbook_graphical_type"],
                }
        if not info:
            continue
        cls = info.get("fidelity_class") or RAW_EVIDENCE_ROW
        row["fidelity_class"] = cls
        row["retained_as_evidence"] = bool(info.get("retained_as_evidence", True))
        row["ownership_provenance"] = list(info.get("reasons") or [])
        if not may_generate(cls):
            if row.get("include", True) not in (False, 0, "0", "false", "False"):
                demoted.append(tag)
            row["include"] = False
            # Do not park foreign/graphical into the local Pick Area as active members.
            if cls in (FOREIGN_EQUIPMENT, TEMPLATE_GRAPHICAL_ONLY):
                row["generation_membership"] = "EXCLUDED"
                # Preserve evidence area label when already foreign-tagged; else blank.
                if cls == FOREIGN_EQUIPMENT and not row.get("evidence_machine"):
                    row["evidence_machine"] = (
                        info.get("machine_name")
                        or explicit_machine_name(row)
                        or ""
                    )
    wb["equipment_fidelity"] = {
        "machine": machine,
        "counts": fidelity.get("counts") or {},
        "demoted_from_generation": demoted,
        "policy": (fidelity.get("policy") or {"ori": "ORI-075"}),
    }
    return wb
