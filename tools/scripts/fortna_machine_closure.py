#!/usr/bin/env python3
"""MachineClosure — walk schema edges over native-shadow active tables.

Start from Machine_Name / target machine; follow schema SELECTION edges
(Conveyor.Machine_Name, EStop.Part→Conveyor, MergeBoss.Owner, MergeInputs,
MergeRoute, Mtrchain, SawLane, …) using ACTIVE rows from the native resolver.

Each closure row records:
  source_table, source_file, row_index, machine, relationship_path,
  provenance, source_id
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fortna_fortna_table_resolver import resolve_active_asc
from fortna_schema_ir import build_schema_ir, selection_edge_index
from fortna_site_model import PROV_RUN_EXPLICIT, normalize_name, row_identity_key

# Closure walk seeds / primary ownership edges (GATE 4).
CLOSURE_SEED_TABLES = ("Machine",)
CLOSURE_WALK_TABLES = (
    "Conveyor",
    "EStop",
    "MergeBoss",
    "MergeInputs",
    "MergeRoute",
    "Mtrchain",
    "SawLane",
    "SawMerge",
)

# Field names that bind a row to a machine / owner controller.
MACHINE_BIND_FIELDS = ("Machine_Name", "Owner", "Machine")


def _source_id(table: str, identity: str | None, row_index: int) -> str:
    if identity:
        return f"{table}:{identity}"
    return f"{table}#{row_index}"


def _row_binds_machine(row: dict[str, str], machine: str) -> bool:
    m = normalize_name(machine)
    for col in MACHINE_BIND_FIELDS:
        val = normalize_name(row.get(col) or "")
        if val and val == m:
            return True
    return False


def _load_active(
    fortna: Path,
    stem: str,
    machine: str,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if stem not in cache:
        cache[stem] = resolve_active_asc(fortna, stem, machine)
    return cache[stem]


def _index_by_identity(resolved: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    headers = resolved.get("headers") or []
    for item in resolved.get("merged_rows") or []:
        row = item.get("row") or {}
        ident = item.get("identity") or row_identity_key(row, headers)
        if not ident:
            continue
        out.setdefault(ident, item)
    return out


def build_machine_closure(
    run_dir: Path | str,
    machine: str,
    *,
    fortna_subdir: str = "FORTNA",
) -> dict[str, Any]:
    """Build MachineClosure for ``machine`` from native active tables + schema IR."""
    run_dir = Path(run_dir)
    fortna = run_dir / fortna_subdir
    machine = str(machine or "").strip()
    ir = build_schema_ir(run_dir)
    edges_by_table = selection_edge_index(ir)
    cache: dict[str, dict[str, Any]] = {}

    members: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Seed: Machine table row(s) for this machine
    machine_resolved = _load_active(fortna, "Machine", machine, cache)
    machine_index = _index_by_identity(machine_resolved)
    seed_ident = normalize_name(machine)
    seed_item = machine_index.get(seed_ident)
    if seed_item is None:
        # Some Machine.asc overlays use Machine_Name as identity column
        for ident, item in machine_index.items():
            row = item.get("row") or {}
            if normalize_name(row.get("Machine_Name") or ident) == seed_ident:
                seed_item = item
                seed_ident = ident
                break

    if seed_item is not None:
        sid = _source_id("Machine", seed_ident, int(seed_item.get("source_row") or 0))
        members.append(
            {
                "source_table": "Machine",
                "source_file": seed_item.get("source_path")
                or machine_resolved.get("path_name"),
                "row_index": seed_item.get("source_row"),
                "machine": machine,
                "relationship_path": ["Machine"],
                "provenance": seed_item.get("provenance") or PROV_RUN_EXPLICIT,
                "source_id": sid,
                "identity": seed_ident,
                "source_scope": seed_item.get("source_scope"),
            }
        )
        seen_ids.add(sid)

    # Seed conveyors owned by this machine (Machine_Name bind).
    # Explicit foreign Machine_Name ALWAYS excludes — even on MACHINE_SPECIFIC overlays.
    conv = _load_active(fortna, "Conveyor", machine, cache)
    for item in conv.get("merged_rows") or []:
        row = item.get("row") or {}
        # Explicit non-empty Machine_Name that is not the target → never include.
        explicit_mach = ""
        for col in MACHINE_BIND_FIELDS:
            explicit_mach = normalize_name(row.get(col) or "")
            if explicit_mach and explicit_mach not in ("N/A", "NA", "INVALID", "NONE", "ALL", "0"):
                break
            explicit_mach = ""
        if explicit_mach and explicit_mach != normalize_name(machine):
            continue
        if not _row_binds_machine(row, machine):
            # Overlay take-all only for rows without an explicit foreign machine.
            # N/A rows still require a later relationship walk — do not seed them here.
            continue
        ident = item.get("identity") or row_identity_key(row, conv.get("headers"))
        if not ident:
            continue
        path = ("Machine", "Conveyor.Machine_Name", f"Conveyor:{ident}")
        sid = _source_id("Conveyor", ident, int(item.get("source_row") or 0))
        if sid in seen_ids:
            continue
        members.append(
            {
                "source_table": "Conveyor",
                "source_file": item.get("source_path") or conv.get("path_name"),
                "row_index": item.get("source_row"),
                "machine": machine,
                "relationship_path": list(path),
                "provenance": item.get("provenance") or PROV_RUN_EXPLICIT,
                "source_id": sid,
                "identity": ident,
                "source_scope": item.get("source_scope"),
            }
        )
        seen_ids.add(sid)

    # Seed MergeBoss rows owned by this machine
    mb = _load_active(fortna, "MergeBoss", machine, cache)
    for item in mb.get("merged_rows") or []:
        row = item.get("row") or {}
        if mb.get("kind") != "MACHINE_SPECIFIC_ASC" and not _row_binds_machine(row, machine):
            continue
        ident = item.get("identity") or row_identity_key(row, mb.get("headers"))
        if not ident:
            continue
        path = ("Machine", "MergeBoss.Owner", f"MergeBoss:{ident}")
        sid = _source_id("MergeBoss", ident, int(item.get("source_row") or 0))
        if sid in seen_ids:
            continue
        members.append(
            {
                "source_table": "MergeBoss",
                "source_file": item.get("source_path") or mb.get("path_name"),
                "row_index": item.get("source_row"),
                "machine": machine,
                "relationship_path": list(path),
                "provenance": item.get("provenance") or PROV_RUN_EXPLICIT,
                "source_id": sid,
                "identity": ident,
                "source_scope": item.get("source_scope"),
            }
        )
        seen_ids.add(sid)

    identity_sets: dict[str, set[str]] = {
        "Conveyor": {
            m["identity"] for m in members if m["source_table"] == "Conveyor" and m.get("identity")
        },
        "MergeBoss": {
            m["identity"] for m in members if m["source_table"] == "MergeBoss" and m.get("identity")
        },
        "Machine": {seed_ident} if seed_item is not None else set(),
    }

    def _consider(
        table: str,
        item: dict[str, Any],
        *,
        via: str,
        parent_path: tuple[str, ...],
        resolved: dict[str, Any],
    ) -> None:
        row = item.get("row") or {}
        ident = item.get("identity") or row_identity_key(row, resolved.get("headers"))
        if not ident:
            return
        sid = _source_id(table, ident, int(item.get("source_row") or 0))
        if sid in seen_ids:
            return
        path = parent_path + (via, f"{table}:{ident}")
        members.append(
            {
                "source_table": table,
                "source_file": item.get("source_path") or resolved.get("path_name"),
                "row_index": item.get("source_row"),
                "machine": machine,
                "relationship_path": list(path),
                "provenance": item.get("provenance") or PROV_RUN_EXPLICIT,
                "source_id": sid,
                "identity": ident,
                "source_scope": item.get("source_scope"),
            }
        )
        seen_ids.add(sid)
        identity_sets.setdefault(table, set()).add(ident)

    # Walk dependent tables that reference Conveyor / MergeBoss / Machine
    dependent_specs: list[tuple[str, str, str, set[str]]] = [
        # table, field, target_table_name, identity_set_key
        ("EStop", "Part", "Conveyor", "Conveyor"),
        ("MergeInputs", "MergeBoss", "MergeBoss", "MergeBoss"),
        ("MergeRoute", "MergeInputs", "MergeInputs", "MergeInputs"),
        ("Mtrchain", "Motor_Ndx", "Conveyor", "Conveyor"),
        ("SawLane", "PhotoEyeIO", "Conveyor", "Conveyor"),
        ("SawLane", "DisableIO", "Conveyor", "Conveyor"),
        ("SawLane", "AllowedInput", "Conveyor", "Conveyor"),
    ]

    # Also follow schema edges dynamically for walk tables
    for table in CLOSURE_WALK_TABLES:
        for edge in edges_by_table.get(table) or []:
            target = edge.get("target_table")
            field = edge.get("field")
            if not target or not field:
                continue
            if target not in ("Conveyor", "MergeBoss", "MergeInputs", "MergeRoute", "Machine", "SawMerge"):
                continue
            dependent_specs.append((table, field, target, target))

    # Deduplicate specs
    seen_specs: set[tuple[str, str, str]] = set()
    uniq_specs: list[tuple[str, str, str, set[str]]] = []
    for table, field, target, key in dependent_specs:
        sk = (table, field, target)
        if sk in seen_specs:
            continue
        seen_specs.add(sk)
        uniq_specs.append((table, field, target, key))

    # Multi-pass: newly discovered identities can unlock more rows
    for _ in range(4):
        progressed = False
        for table, field, _target, key in uniq_specs:
            resolved = _load_active(fortna, table, machine, cache)
            if resolved.get("kind") == "MISSING":
                continue
            allowed = identity_sets.get(key) or set()
            # Machine-specific overlay of dependent table: include all rows
            take_all = resolved.get("kind") == "MACHINE_SPECIFIC_ASC" and table in {
                "MergeInputs",
                "MergeRoute",
                "SawLane",
                "SawMerge",
                "Mtrchain",
                "EStop",
            }
            for item in resolved.get("merged_rows") or []:
                row = item.get("row") or {}
                ref = normalize_name(row.get(field) or "")
                if take_all or (ref and ref in allowed) or _row_binds_machine(row, machine):
                    before = len(seen_ids)
                    _consider(
                        table,
                        item,
                        via=f"{table}.{field}",
                        parent_path=("Machine",),
                        resolved=resolved,
                    )
                    if len(seen_ids) > before:
                        progressed = True
                        ident = item.get("identity") or row_identity_key(
                            row, resolved.get("headers")
                        )
                        if ident:
                            identity_sets.setdefault(table, set()).add(ident)
        if not progressed:
            break

    by_table: dict[str, int] = {}
    for m in members:
        by_table[m["source_table"]] = by_table.get(m["source_table"], 0) + 1

    return {
        "kind": "MachineClosure",
        "version": 1,
        "machine": machine,
        "run_dir": str(run_dir),
        "schema_fingerprint": ir.fingerprint,
        "members": members,
        "counts": {"members": len(members), "by_table": by_table},
        "active_tables_used": sorted(cache),
        "notes": [
            "Active rows resolved via fortna_fortna_table_resolver (native_shadow).",
            "Schema edges from fortna_schema_ir (RUN fortna.mnu / project.mnu).",
        ],
    }


__all__ = [
    "CLOSURE_SEED_TABLES",
    "CLOSURE_WALK_TABLES",
    "build_machine_closure",
]
