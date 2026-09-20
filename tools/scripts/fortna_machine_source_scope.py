#!/usr/bin/env python3
"""Active-machine source scoping for RUN artifacts.

A RUN archive may contain configuration for multiple controllers.
Physical decoding must use ACTIVE_MACHINE_SOURCE only.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCOPE_ACTIVE = "ACTIVE_MACHINE_SOURCE"
SCOPE_SIBLING = "SIBLING_MACHINE_SOURCE"
SCOPE_AMBIGUOUS = "AMBIGUOUS_MACHINE_SOURCE"
SCOPE_GLOBAL = "GLOBAL_PROJECT_SOURCE"


@dataclass
class MachineScopedSource:
    project: str
    active_machine: str
    source_file: str
    source_machine_inferred: str
    scope_status: str
    kind: str = ""  # eipcfg | configio | eipmodules | eipadapters | other
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_machine_name(run_dir: Path) -> str:
    cfg = run_dir / "project.cfg"
    if not cfg.is_file():
        return ""
    text = cfg.read_text(encoding="utf-8", errors="replace")
    for key in ("MACHINENAME", "MACHINE_NAME", "Machine_Name", "machine"):
        m = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*(.+)\s*$", text)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def read_project_name(run_dir: Path) -> str:
    cfg = run_dir / "project.cfg"
    if not cfg.is_file():
        return ""
    text = cfg.read_text(encoding="utf-8", errors="replace")
    for key in ("PROJECTNAME", "PROJECT_NAME", "Project_Name", "project"):
        m = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*(.+)\s*$", text)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def _infer_machine_from_eipcfg_name(name: str) -> str:
    # RESPICK-RTA-eipcfg.xml / MSCRENOPICK-RTA1-eipcfg.xml / CPEIP-RTA1-eipcfg.xml
    base = Path(name).name
    # Generic shared Fortna eipcfg names — not a sibling controller identity
    if base.upper().startswith("CPEIP"):
        return ""
    m = re.match(r"^(?P<mach>.+?)-RTA\d*-eipcfg", base, re.I)
    if m:
        mach = m.group("mach")
        if mach.upper() == "CPEIP":
            return ""
        return mach
    m = re.match(r"^(?P<mach>.+?)eipcfg", base, re.I)
    if m:
        return m.group("mach").rstrip("-_")
    return ""


def classify_eipcfg_files(run_dir: Path, active_machine: str = "") -> list[MachineScopedSource]:
    fortna = run_dir / "FORTNA"
    if not fortna.is_dir():
        return []
    active = (active_machine or read_machine_name(run_dir) or "").strip()
    project = read_project_name(run_dir)
    out: list[MachineScopedSource] = []
    for p in sorted(fortna.glob("*eipcfg*.xml")):
        # skip .OLD / backup extensions already filtered by glob on xml
        inferred = _infer_machine_from_eipcfg_name(p.name)
        notes: list[str] = []
        if not active:
            scope = SCOPE_AMBIGUOUS
            notes.append("active_machine_unknown")
        elif inferred and inferred.upper() == active.upper():
            scope = SCOPE_ACTIVE
        elif inferred and inferred.upper() != active.upper():
            scope = SCOPE_SIBLING
            notes.append(f"sibling_machine={inferred}")
        elif not inferred:
            # CPEIP-RTA1 etc. — global/ambiguous, not active unless only file
            scope = SCOPE_GLOBAL
            notes.append("generic_or_unscoped_eipcfg_name")
        else:
            scope = SCOPE_AMBIGUOUS
        out.append(
            MachineScopedSource(
                project=project,
                active_machine=active,
                source_file=str(p.relative_to(run_dir)).replace("\\", "/"),
                source_machine_inferred=inferred,
                scope_status=scope,
                kind="eipcfg",
                notes=notes,
            )
        )
    return out


def select_active_eipcfg(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Select ACTIVE_MACHINE_SOURCE eipcfg; never silently use sibling."""
    active = (machine or read_machine_name(run_dir) or "").strip()
    classified = classify_eipcfg_files(run_dir, active)
    actives = [c for c in classified if c.scope_status == SCOPE_ACTIVE]
    siblings = [c for c in classified if c.scope_status == SCOPE_SIBLING]
    globals_ = [c for c in classified if c.scope_status == SCOPE_GLOBAL]
    ambiguous = [c for c in classified if c.scope_status == SCOPE_AMBIGUOUS]

    selected: Path | None = None
    selection_reason = ""
    if actives:
        # Prefer exact {mach}-RTA-eipcfg.xml
        fortna = run_dir / "FORTNA"
        exact = fortna / f"{active}-RTA-eipcfg.xml"
        if exact.is_file():
            selected = exact
            selection_reason = "exact_active_machine_rta_eipcfg"
        else:
            # first active by name
            selected = run_dir / actives[0].source_file
            selection_reason = "active_machine_glob_match"
    elif globals_ and not siblings:
        # Only generic file(s) present — allow with explicit scope note
        selected = run_dir / globals_[0].source_file
        selection_reason = "only_global_eipcfg_available"
    else:
        selected = None
        selection_reason = "no_active_machine_eipcfg_refusing_sibling_fallback"

    return {
        "active_machine": active,
        "selected_eipcfg": str(selected) if selected else None,
        "selection_reason": selection_reason,
        "classified": [c.to_dict() for c in classified],
        "siblings": [c.to_dict() for c in siblings],
        "refused_sibling_fallback": bool(siblings and not actives),
    }
