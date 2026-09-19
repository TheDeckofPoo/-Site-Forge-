#!/usr/bin/env python3
"""Canonical machine-scoped RUN view — single consumer for all subsystems.

Explicit foreign Machine_Name always EXCLUDES the object.
N/A objects require a real MachineClosure relationship — not P-number family.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fortna_fortna_table_resolver import resolve_active_asc
from fortna_machine_closure import build_machine_closure, _row_binds_machine
from fortna_project_identity import normalize_machine_token
from fortna_site_model import normalize_name, row_identity_key

NA_TOKENS = frozenset({"", "N/A", "NA", "INVALID", "NONE", "ALL", "0", "~"})


def explicit_machine_name(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return ""
    for col in ("Machine_Name", "Owner", "Machine"):
        val = normalize_name(row.get(col) or "")
        if val and val not in NA_TOKENS:
            return val
    return ""


def is_explicit_foreign_machine(row: dict[str, Any] | None, target_machine: str) -> bool:
    """True when row has a non-empty Machine_Name that is not the target."""
    explicit = explicit_machine_name(row)
    if not explicit:
        return False
    return normalize_machine_token(explicit) != normalize_machine_token(target_machine)


def belongs_to_target_machine(
    row: dict[str, Any] | None,
    target_machine: str,
    *,
    closure_idents: set[str] | None = None,
    relationship_ok: bool = False,
) -> bool:
    """Canonical inclusion rule for site-specific equipment rows.

    1. Explicit foreign Machine_Name → False (never override)
    2. Explicit target Machine_Name → True
    3. N/A / blank → True only with relationship_ok or identity in closure
    """
    target = normalize_machine_token(target_machine)
    if not target:
        return False
    if is_explicit_foreign_machine(row, target):
        return False
    explicit = explicit_machine_name(row)
    if explicit and normalize_machine_token(explicit) == target:
        return True
    # N/A / blank — require relationship into closure
    if relationship_ok:
        return True
    if closure_idents is not None:
        ident = normalize_name(
            (row or {}).get("Conveyor_Name")
            or (row or {}).get("IO_Name")
            or (row or {}).get("Name")
            or ""
        )
        if ident and ident in closure_idents:
            return True
    return False


@dataclass
class MachineScopedRunView:
    machine: str
    project_name: str = ""
    run_dir: str = ""
    active_tables: dict[str, Any] = field(default_factory=dict)
    conveyor_ids: set[str] = field(default_factory=set)
    io_device_ids: set[str] = field(default_factory=set)
    machine_closure: set[str] = field(default_factory=set)
    lineage: dict[str, dict[str, Any]] = field(default_factory=dict)
    foreign_excluded: list[dict[str, Any]] = field(default_factory=list)
    closure_doc: dict[str, Any] = field(default_factory=dict)

    def belongs_to(self, identity: str) -> bool:
        tok = normalize_name(identity)
        if not tok:
            return False
        if tok in self.machine_closure or tok in self.conveyor_ids:
            return True
        # Accept Conveyor:P120C style source ids
        if f"CONVEYOR:{tok}" in {c.upper() for c in self.machine_closure}:
            return True
        return False

    def assert_generated_lineage(self, objects: list[str]) -> list[str]:
        """Return identities that violate current-machine lineage."""
        bad: list[str] = []
        for obj in objects:
            if not self.belongs_to(obj):
                # Allow non-equipment infrastructure tokens
                u = normalize_name(obj)
                if not u or u.startswith(("SYS", "NTP", "AOI_", "NO_")):
                    continue
                bad.append(obj)
        return bad


def build_machine_scoped_run_view(
    run_dir: Path | str,
    machine: str = "",
    *,
    fortna_subdir: str = "FORTNA",
) -> MachineScopedRunView:
    """Build the single machine-scoped view every subsystem should consume."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    from fortna_project_identity import identity_from_run

    ident = identity_from_run(run_dir)
    machine = normalize_machine_token(machine) or ident.machine
    fortna = run_dir / fortna_subdir

    closure_doc = build_machine_closure(run_dir, machine, fortna_subdir=fortna_subdir)
    closure_idents: set[str] = set()
    lineage: dict[str, dict[str, Any]] = {}
    for m in closure_doc.get("members") or []:
        iid = normalize_name(m.get("identity") or "")
        sid = normalize_name(m.get("source_id") or "")
        if iid:
            closure_idents.add(iid)
            lineage[iid] = {
                "source_table": m.get("source_table"),
                "source_id": m.get("source_id"),
                "relationship_path": m.get("relationship_path"),
                "provenance": m.get("provenance"),
                "machine": machine,
            }
        if sid:
            closure_idents.add(sid)

    conv = resolve_active_asc(fortna, "Conveyor", machine)
    conveyor_ids: set[str] = set()
    foreign_excluded: list[dict[str, Any]] = []
    for item in conv.get("merged_rows") or []:
        row = item.get("row") or {}
        iid = normalize_name(
            item.get("identity") or row_identity_key(row, conv.get("headers")) or ""
        )
        if not iid:
            continue
        if is_explicit_foreign_machine(row, machine):
            foreign_excluded.append(
                {
                    "identity": iid,
                    "machine_name": explicit_machine_name(row),
                    "reason": "EXPLICIT_FOREIGN_MACHINE_NAME",
                }
            )
            continue
        # Explicit target OR already in closure (relationship walk)
        if _row_binds_machine(row, machine) or iid in closure_idents:
            conveyor_ids.add(iid)
            lineage.setdefault(
                iid,
                {
                    "source_table": "Conveyor",
                    "source_id": f"Conveyor:{iid}",
                    "provenance": item.get("provenance") or "RUN_EXPLICIT",
                    "machine": machine,
                    "machine_name": explicit_machine_name(row) or "N/A",
                },
            )

    # Never let MACHINE_SPECIFIC take-all reintroduce explicit foreign rows
    for excl in foreign_excluded:
        conveyor_ids.discard(normalize_name(excl.get("identity")))
        closure_idents.discard(normalize_name(excl.get("identity")))

    return MachineScopedRunView(
        machine=machine,
        project_name=ident.project_name,
        run_dir=str(run_dir),
        active_tables={"Conveyor": {"kind": conv.get("kind"), "path": conv.get("path_name")}},
        conveyor_ids=conveyor_ids,
        io_device_ids=set(),
        machine_closure=closure_idents,
        lineage=lineage,
        foreign_excluded=foreign_excluded,
        closure_doc=closure_doc,
    )
