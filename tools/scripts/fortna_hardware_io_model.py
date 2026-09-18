#!/usr/bin/env python3
"""Hardware / I/O workspace model — thin wrapper over PhysicalWordResolver.

The graphical Hardware view MUST consume this tree (or PhysicalWordResolver
directly). Do NOT rediscover adapters/modules/slots/channels independently.
If Hardware UI and IO_MAP disagree, that is a model defect — fix the resolver.

Physical endpoint identity (Gate C) is separate from engineering owner (Gate D).
Owner states: ASSIGNED | UNRESOLVED_OWNER | ENGINEER_SPARE | PROVEN_SPARE | UNKNOWN.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_hardware_family import (  # noqa: E402
    adapter_family_from_modules,
    channel_capacity_for_catalog,
    detect_family_from_catalog,
    family_scheme_description,
    renderer_for_family,
)
from fortna_hardware_io_overrides import (  # noqa: E402
    apply_overrides_to_hardware_model,
    is_clear_sentinel,
    load_overrides,
)
from fortna_io_extract import extract_io_points, read_project_meta  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

# Gate D — engineering owner resolution states (never collapse into SPARE alone).
OWNER_ASSIGNED = "ASSIGNED"
OWNER_UNRESOLVED = "UNRESOLVED_OWNER"
OWNER_ENGINEER_SPARE = "ENGINEER_SPARE"
OWNER_PROVEN_SPARE = "PROVEN_SPARE"
OWNER_UNKNOWN = "UNKNOWN"

OWNER_STATES = (
    OWNER_ASSIGNED,
    OWNER_UNRESOLVED,
    OWNER_ENGINEER_SPARE,
    OWNER_PROVEN_SPARE,
    OWNER_UNKNOWN,
)

# UNRESOLVED_OWNER rejection reasons (enum — every unresolved channel must set one).
REJECTION_PANEL_NODE_NOT_RESOLVED = "PANEL_NODE_NOT_RESOLVED"
REJECTION_EIP_BANK_NOT_FOUND = "EIP_BANK_NOT_FOUND"
REJECTION_SLOT_MISMATCH = "SLOT_MISMATCH"
REJECTION_BIT_OUT_OF_RANGE = "BIT_OUT_OF_RANGE"
REJECTION_CONFIGIO_ROW_NOT_LOADED = "CONFIGIO_ROW_NOT_LOADED"
REJECTION_MODULE_TYPE_MISMATCH = "MODULE_TYPE_MISMATCH"
REJECTION_OWNER_REFERENCE_TARGET_MISSING = "OWNER_REFERENCE_TARGET_MISSING"
REJECTION_MULTIPLE_ENDPOINT_CANDIDATES = "MULTIPLE_ENDPOINT_CANDIDATES"
REJECTION_DIRECTION_CONFLICT = "DIRECTION_CONFLICT"
REJECTION_OWNER_CONFLICT = "OWNER_CONFLICT"
REJECTION_CONVEYOR_RESOLVE_FAILED = "CONVEYOR_RESOLVE_FAILED"
REJECTION_CONFIGIO_SIGNAL_UNBOUND = "CONFIGIO_SIGNAL_UNBOUND"
REJECTION_OWNER_RESOLUTION_FAILED = "OWNER_RESOLUTION_FAILED"

REJECTION_REASONS = (
    REJECTION_PANEL_NODE_NOT_RESOLVED,
    REJECTION_EIP_BANK_NOT_FOUND,
    REJECTION_SLOT_MISMATCH,
    REJECTION_BIT_OUT_OF_RANGE,
    REJECTION_CONFIGIO_ROW_NOT_LOADED,
    REJECTION_MODULE_TYPE_MISMATCH,
    REJECTION_OWNER_REFERENCE_TARGET_MISSING,
    REJECTION_MULTIPLE_ENDPOINT_CANDIDATES,
    REJECTION_DIRECTION_CONFLICT,
    REJECTION_OWNER_CONFLICT,
    REJECTION_CONVEYOR_RESOLVE_FAILED,
    REJECTION_CONFIGIO_SIGNAL_UNBOUND,
    REJECTION_OWNER_RESOLUTION_FAILED,
)

_SPARE_NAME_TOKENS = frozenset(
    {"", "SPARE", "INVALID", "N/A", "NONE", "NULL", "—", "-", "(SPARE)", "(CLEARED)"}
)


def _module_channel_capacity(mod_type: str, connection: str = "") -> int:
    """Digital channel capacity from catalog type (family-aware bounds)."""
    return channel_capacity_for_catalog(mod_type, connection=connection)


def make_physical_endpoint(
    *,
    machine: str = "",
    panel: str = "",
    node: Any = None,
    adapter: str = "",
    rio_name: str = "",
    module_slot: Any = None,
    data_index: Any = None,
    bank_word: Any = None,
    bit: Any = None,
    direction: str = "",
    module_type: str = "",
    module_name: str = "",
    channel: str = "",
    family: str = "",
) -> dict[str, Any]:
    """Canonical physical endpoint — proven Fortna dimensions only (Gate C).

    Equality is exact dimension equality (see physical_endpoints_equal).
    No string-similarity ownership; no prefix collapse (P220/P220A lesson).
    """
    dir_u = (direction or "").strip().upper()
    if dir_u in ("IN", "INPUT"):
        dir_u = "I"
    elif dir_u in ("OUT", "OUTPUT"):
        dir_u = "O"
    try:
        slot_i = int(module_slot) if module_slot is not None and str(module_slot) != "" else None
    except (TypeError, ValueError):
        slot_i = None
    try:
        di = int(data_index) if data_index is not None and str(data_index) != "" else None
    except (TypeError, ValueError):
        di = None
    try:
        word_i = int(bank_word) if bank_word is not None and str(bank_word) != "" else None
    except (TypeError, ValueError):
        word_i = None
    try:
        bit_i = int(bit) if bit is not None and str(bit) != "" else None
    except (TypeError, ValueError):
        bit_i = None
    try:
        node_i = int(node) if node is not None and str(node) != "" else None
    except (TypeError, ValueError):
        node_i = None

    rio = (rio_name or adapter or "").strip()
    ch = (channel or "").strip()
    if not ch and rio and dir_u in ("I", "O") and di is not None and bit_i is not None:
        ch = f"{rio}:{dir_u}.Data[{di}].{bit_i}"

    return {
        "machine": (machine or "").strip() or None,
        "panel": (panel or "").strip() or None,
        "node": node_i,
        "adapter": (adapter or rio or "").strip() or None,
        "rio_name": rio or None,
        "module_slot": slot_i,
        "data_index": di,
        "bank_word": word_i,
        "bit": bit_i,
        "direction": dir_u or None,
        "module_type": (module_type or "").strip() or None,
        "module_name": (module_name or "").strip() or None,
        "family": (family or "").strip() or None,
        "channel": ch or None,
        # Stable identity key — exact fields only (never a fuzzy/prefix key)
        "endpoint_id": _endpoint_id(
            machine=(machine or "").strip(),
            rio=rio,
            direction=dir_u,
            data_index=di,
            bit=bit_i,
            module_slot=slot_i,
            bank_word=word_i,
            module_type=(module_type or "").strip(),
        ),
    }


def _endpoint_id(
    *,
    machine: str,
    rio: str,
    direction: str,
    data_index: int | None,
    bit: int | None,
    module_slot: int | None,
    bank_word: int | None,
    module_type: str,
) -> str | None:
    if not rio or direction not in ("I", "O") or data_index is None or bit is None:
        return None
    parts = [
        machine or "-",
        rio,
        direction,
        f"Data[{data_index}]",
        f"b{bit}",
        f"slot{module_slot if module_slot is not None else '-'}",
        f"w{bank_word if bank_word is not None else '-'}",
        module_type or "-",
    ]
    return "|".join(parts)


def physical_endpoints_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """True only when proven endpoint dimensions match exactly (Gate C).

    Rejects name-prefix / string-similarity ownership (P220 vs P220A).
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    # Prefer canonical endpoint_id when both present
    id_a = (a.get("endpoint_id") or "").strip()
    id_b = (b.get("endpoint_id") or "").strip()
    if id_a and id_b:
        return id_a == id_b
    keys = (
        "machine",
        "rio_name",
        "direction",
        "data_index",
        "bit",
        "module_slot",
        "bank_word",
        "module_type",
    )
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va is None and vb is None:
            continue
        if va != vb:
            return False
    # Channel string equality is corroboration only when both present
    ca = (a.get("channel") or "").strip()
    cb = (b.get("channel") or "").strip()
    if ca and cb and ca != cb:
        return False
    return True


def _is_spare_token(name: str | None) -> bool:
    return str(name or "").strip().upper() in _SPARE_NAME_TOKENS


def _configio_desc_claim(desc: str | None) -> str:
    """Classify a Configio Desc as spare | occupied | topology | none (Gate D).

    PANEL-NODE / PANEL-CATALOG Desc forms (e.g. CP5-NODE51-1A, CP2-1794-IA16-3)
    are module topology addressing only — not engineering owner names and not
    proof that every bit on the word is an occupied signal waiting for an owner.
    """
    d = str(desc or "").strip()
    if not d:
        return "none"
    if _is_spare_token(d):
        return "spare"
    try:
        from fortna_physical_word_resolver import configio_desc_evidence

        ev = configio_desc_evidence(d)
        if ev and ev.get("form") in ("panel_node", "panel_catalog"):
            return "topology"
    except Exception:
        pass
    # Non-topology Desc (signal / name claim) → occupancy evidence
    return "occupied"


def _channel_configio_claim(ch: dict[str, Any] | None) -> tuple[bool, bool, bool]:
    """Return (configio_occupied, configio_spare, configio_topology) from Desc evidence.

    Prefer the bit_half-appropriate Desc (low_desc / high_desc); fall back to any
    Desc stamped on the channel or its provenance.

    Topology forms never count as occupancy. Occupied is reserved for non-topology
    signal/name claims that could not bind to a Conveyor owner.
    """
    if not isinstance(ch, dict):
        return False, False, False
    bit_half = str(ch.get("bit_half") or "").strip().lower()
    prov = ch.get("provenance") if isinstance(ch.get("provenance"), dict) else {}
    ordered: list[Any] = []
    if bit_half == "high":
        ordered.extend([ch.get("high_desc"), prov.get("high_desc"), ch.get("low_desc")])
    else:
        ordered.extend([ch.get("low_desc"), prov.get("low_desc"), ch.get("high_desc")])
    ordered.extend(
        [
            ch.get("configio_desc"),
            prov.get("configio_desc"),
            prov.get("high_desc"),
            ch.get("high_desc"),
            ch.get("low_desc"),
        ]
    )
    saw_topology = False
    for raw in ordered:
        claim = _configio_desc_claim(raw)
        if claim == "spare":
            return False, True, False
        if claim == "occupied":
            return True, False, False
        if claim == "topology":
            saw_topology = True
    return False, False, saw_topology


def resolve_owner_state(
    *,
    physical_endpoint: dict[str, Any] | None,
    engineering_owner: str | None,
    owner_source: str | None = None,
    spare_claim: bool = False,
    engineer_spare: bool = False,
    owner_conflict: bool = False,
    topology_known: bool = False,
    owner_resolution_failed: bool = False,
    configio_occupied: bool = False,
    configio_spare: bool = False,
) -> str:
    """Classify engineering owner relative to a physical endpoint (Gate D).

    PROVEN_SPARE when:
      - positive spare token (Conveyor SPARE / Configio Desc spare), or
      - mapped physical endpoint + no Conveyor owner + no non-topology Configio
        signal claim (unused point on an installed module).

    UNRESOLVED_OWNER only for conflict, failed named resolve, non-topology
    Configio signal claim that could not bind, or explicit owner_resolution_failed.
    Topology-only Configio Desc is never occupancy.
    """
    ep = physical_endpoint if isinstance(physical_endpoint, dict) else None
    ep_ok = bool(ep and (ep.get("endpoint_id") or ep.get("channel")))
    topo = topology_known or ep_ok
    owner = (engineering_owner or "").strip()
    if engineer_spare or (owner_source or "").upper() == "ENGINEER_SPARE":
        return OWNER_ENGINEER_SPARE
    if owner and not _is_spare_token(owner):
        return OWNER_ASSIGNED
    if owner_conflict or owner_resolution_failed:
        # Topology known but owner could not be bound uniquely / at all
        return OWNER_UNRESOLVED if topo else OWNER_UNKNOWN
    # Positive spare token evidence
    if spare_claim or (owner and _is_spare_token(owner)) or configio_spare:
        return OWNER_PROVEN_SPARE if topo else OWNER_UNKNOWN
    # Non-topology Configio signal/name claim + no resolvable owner → UNRESOLVED
    if topo and configio_occupied and not owner:
        return OWNER_UNRESOLVED
    # Mapped endpoint + no owner + topology-only / empty Desc → unused module bit
    if topo and not owner:
        return OWNER_PROVEN_SPARE
    if not topo and not owner:
        return OWNER_UNKNOWN
    return OWNER_UNKNOWN


def _rejection_reason_for_unresolved(
    *,
    owner_conflict: bool = False,
    owner_resolution_failed: bool = False,
    configio_occupied: bool = False,
    explicit_reason: str | None = None,
) -> str:
    """Pick a rejection_reason enum value for an UNRESOLVED_OWNER channel."""
    raw = str(explicit_reason or "").strip().upper()
    if raw in REJECTION_REASONS:
        return raw
    if owner_conflict:
        return REJECTION_OWNER_CONFLICT
    if raw in {"PHYSICAL_RESOLVE_FAILED", "CONVEYOR_RESOLVE_FAILED", "EMPTY_CHANNEL"}:
        return REJECTION_CONVEYOR_RESOLVE_FAILED
    if owner_resolution_failed:
        return REJECTION_OWNER_RESOLUTION_FAILED
    if configio_occupied:
        return REJECTION_CONFIGIO_SIGNAL_UNBOUND
    return REJECTION_OWNER_REFERENCE_TARGET_MISSING


def module_ownership_audit_pass(module: dict[str, Any] | None) -> dict[str, Any]:
    """Audit helper: module with RUN/Conveyor claims cannot PASS if all ownership absent.

    Returns {ok, reason, expected_occupied, assigned, unresolved, spare}.
    """
    mod = module if isinstance(module, dict) else {}
    channels = list(mod.get("channels") or [])
    assigned = sum(1 for c in channels if c.get("owner_state") == OWNER_ASSIGNED)
    unresolved = sum(1 for c in channels if c.get("owner_state") == OWNER_UNRESOLVED)
    spare = sum(
        1
        for c in channels
        if c.get("owner_state") in (OWNER_PROVEN_SPARE, OWNER_ENGINEER_SPARE)
    )
    # Expected occupied = Conveyor-named claims on this module's channels
    expected = 0
    for c in channels:
        le = c.get("logical_endpoint") if isinstance(c.get("logical_endpoint"), dict) else None
        name = ""
        if le:
            name = str(le.get("name") or "").strip()
        if not name:
            name = str(c.get("engineering_owner") or c.get("sourceName") or "").strip()
        if name and not _is_spare_token(name):
            expected += 1
        elif c.get("owner_source") == "RUN_CONVEYOR":
            expected += 1
    # Explicit module-level claim count when stamped by builder
    if mod.get("expected_occupied") is not None:
        try:
            expected = max(expected, int(mod.get("expected_occupied") or 0))
        except (TypeError, ValueError):
            pass
    ok = True
    reason = ""
    if expected > 0 and assigned == 0 and unresolved == 0 and spare >= expected:
        # All claimed points classified spare / absent ownership — fail audit
        ok = False
        reason = "RUN_CLAIMS_PRESENT_BUT_NO_ASSIGNED_OR_UNRESOLVED_OWNERSHIP"
    elif expected > 0 and assigned == 0 and unresolved == 0:
        ok = False
        reason = "RUN_CLAIMS_PRESENT_BUT_OWNERSHIP_ABSENT"
    return {
        "ok": ok,
        "reason": reason,
        "expected_occupied": expected,
        "assigned": assigned,
        "unresolved": unresolved,
        "spare": spare,
    }

def _index_conveyor_claims(resolver: PhysicalWordResolver) -> dict[str, Any]:
    """Index Conveyor.asc claims by physical channel — owners, spares, conflicts.

    Ownership is never inferred by name prefix. Conflicting distinct owners on the
    same exact endpoint → UNRESOLVED_OWNER (not silent first-wins SPARE).
    """
    owners: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[str]] = {}
    spare_channels: set[str] = set()
    unresolved_named: list[dict[str, Any]] = []

    # Named points (non-SPARE) via extract_io_points
    try:
        points = extract_io_points(resolver.run_dir)
    except Exception:
        points = []
    for p in points:
        word = p.get("fortna_bank")
        bit = p.get("fortna_bit")
        if word in (None, "") or bit in (None, ""):
            continue
        name = (p.get("fortna_name") or p.get("io_name") or p.get("tag") or "").strip()
        if not name or _is_spare_token(name):
            continue
        hit = resolver.resolve(word, bit)
        if not hit:
            unresolved_named.append(
                {
                    "name": name,
                    "fortna_word": word,
                    "fortna_bit": bit,
                    "reason": "physical_resolve_failed",
                }
            )
            continue
        ch = (hit.get("channel") or "").strip()
        if not ch:
            unresolved_named.append(
                {
                    "name": name,
                    "fortna_word": word,
                    "fortna_bit": bit,
                    "reason": "empty_channel",
                }
            )
            continue
        claim = {
            "name": name,
            "tag": (p.get("tag") or "").strip() or None,
            "device_class": p.get("device_class"),
            "equipment_kind": p.get("equipment_kind"),
            "fortna_address": p.get("fortna_address"),
            "source_table": p.get("source_table") or "FORTNA/Conveyor.asc",
        }
        existing = owners.get(ch)
        if existing is None:
            owners[ch] = claim
        elif (existing.get("name") or "").strip() != name:
            # Exact endpoint collision of distinct logical owners — do not prefix-merge
            conflicts.setdefault(ch, []).append(name)
            if existing.get("name") and existing["name"] not in conflicts[ch]:
                conflicts[ch].insert(0, existing["name"])

    # Explicit SPARE / INVALID rows at word.bit (not returned by extract_io_points)
    try:
        from fortna_asc import read_asc

        conv = Path(resolver.run_dir) / "FORTNA" / "Conveyor.asc"
        if conv.is_file():
            _, rows = read_asc(conv)
            for row in rows:
                io_name = (row.get("IO_Name") or "").strip()
                if not _is_spare_token(io_name) and (row.get("Type") or "").strip().upper() != "SPARE":
                    # Only track explicit spare/invalid identity rows here
                    if io_name.upper() not in {"SPARE", "INVALID", "N/A"}:
                        continue
                word = (row.get("IO_Address_Word") or "").strip()
                bit = (row.get("IO_Address_Bit") or "").strip()
                if not word or not bit:
                    continue
                hit = resolver.resolve(word, bit)
                if not hit:
                    continue
                ch = (hit.get("channel") or "").strip()
                if ch:
                    spare_channels.add(ch)
    except Exception:
        pass

    return {
        "owners": owners,
        "conflicts": conflicts,
        "spare_channels": spare_channels,
        "unresolved_named": unresolved_named,
    }


def _logical_by_channel(resolver: PhysicalWordResolver) -> dict[str, dict[str, Any]]:
    """Map physical channel → proven logical endpoint from Conveyor.asc (no invented names)."""
    return dict(_index_conveyor_claims(resolver).get("owners") or {})


def enrich_channel_ownership(
    ch: dict[str, Any],
    *,
    machine: str = "",
    claims: dict[str, Any] | None = None,
    adapter: dict[str, Any] | None = None,
    module: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp physical_endpoint + engineering owner fields onto a channel (in place)."""
    ad = adapter or {}
    mod = module or {}
    claims = claims or {}
    owners = claims.get("owners") or {}
    conflicts = claims.get("conflicts") or {}
    spare_channels = claims.get("spare_channels") or set()

    addr = (ch.get("physical_address") or "").strip()
    prov = ch.get("provenance") if isinstance(ch.get("provenance"), dict) else {}
    node = prov.get("configio_node")
    ep = make_physical_endpoint(
        machine=machine or "",
        panel=ch.get("panel") or ad.get("panel") or "",
        node=node,
        adapter=ad.get("eipcfg_name") or ad.get("name") or "",
        rio_name=ad.get("rio_name") or (addr.split(":", 1)[0] if addr else ""),
        module_slot=mod.get("slot") if mod.get("slot") is not None else prov.get("eipcfg_slot"),
        data_index=mod.get("data_index") if mod.get("data_index") is not None else ch.get("data_index"),
        bank_word=ch.get("fortna_word"),
        bit=ch.get("fortna_bit"),
        direction=ch.get("direction") or mod.get("direction") or "",
        module_type=ch.get("type") or mod.get("type") or mod.get("catalog") or "",
        module_name=ch.get("module_name") or mod.get("name") or "",
        channel=addr,
        family=mod.get("family") or ad.get("family") or "",
    )
    # Prefer hit data_index from channel address when module index missing
    if ep.get("data_index") is None and addr:
        import re as _re

        m = _re.search(r"\.Data\[(\d+)\]\.(\d+)$", addr)
        if m:
            ep["data_index"] = int(m.group(1))
            if ep.get("bit") is None:
                ep["bit"] = int(m.group(2))
            ep["endpoint_id"] = _endpoint_id(
                machine=ep.get("machine") or "",
                rio=ep.get("rio_name") or "",
                direction=ep.get("direction") or "",
                data_index=ep.get("data_index"),
                bit=ep.get("bit"),
                module_slot=ep.get("module_slot"),
                bank_word=ep.get("bank_word"),
                module_type=ep.get("module_type") or "",
            )

    ch["physical_endpoint"] = ep

    eng = str(ch.get("engineerName") or "").strip() or None
    if eng and is_clear_sentinel(eng):
        eng = None
    le = ch.get("logical_endpoint") if isinstance(ch.get("logical_endpoint"), dict) else None
    run_owner = ""
    if le and not le.get("engineer_override"):
        run_owner = str(le.get("name") or "").strip()
    elif addr and addr in owners:
        run_owner = str((owners[addr] or {}).get("name") or "").strip()
        if run_owner and not le:
            ch["logical_endpoint"] = dict(owners[addr])
            le = ch["logical_endpoint"]

    owner_conflict = bool(addr and addr in conflicts and len(conflicts[addr]) > 1)
    spare_claim = bool(addr and addr in spare_channels)
    configio_occupied, configio_spare, configio_topology = _channel_configio_claim(ch)
    # Explicit caller overrides (synthetic / known-site tests)
    if ch.get("configio_occupied") is True:
        configio_occupied = True
        configio_spare = False
        configio_topology = False
    if ch.get("configio_spare") is True or ch.get("configio_spare_claim") is True:
        configio_spare = True
        configio_occupied = False
    if ch.get("configio_topology") is True:
        configio_topology = True
        configio_occupied = False

    # Engineer explicit spare / clear
    engineer_spare = False
    if ch.get("engineer_spare") is True:
        engineer_spare = True
    elif eng is None and ch.get("engineerName") == "" and ch.get("generate") is not False:
        # cleared override with no RUN owner → engineer spare only when source was cleared
        if ch.get("cleared_to_spare"):
            engineer_spare = True

    if eng and not _is_spare_token(eng):
        engineering_owner = eng
        owner_source = "ENGINEER_OVERRIDE"
    elif run_owner and not _is_spare_token(run_owner):
        engineering_owner = run_owner
        owner_source = "RUN_CONVEYOR"
    else:
        engineering_owner = None
        owner_source = "NONE"

    if owner_conflict:
        owner_source = "OWNER_CONFLICT"
        engineering_owner = None
        ch["owner_candidates"] = list(conflicts.get(addr) or [])

    # Explicit unresolved markers (conflict, failed bind, or caller flag)
    owner_resolution_failed = bool(
        ch.get("owner_resolution_failed")
        or ch.get("unresolved_owner")
        or (owner_source or "").upper() == "OWNER_RESOLUTION_FAILED"
    )

    state = resolve_owner_state(
        physical_endpoint=ep,
        engineering_owner=engineering_owner,
        owner_source=owner_source,
        spare_claim=(spare_claim or configio_spare) and not engineering_owner,
        engineer_spare=engineer_spare,
        owner_conflict=owner_conflict,
        owner_resolution_failed=owner_resolution_failed,
        topology_known=bool(ep.get("endpoint_id") or ep.get("channel")),
        configio_occupied=configio_occupied and not configio_spare,
        configio_spare=configio_spare,
    )
    if state == OWNER_PROVEN_SPARE and not engineering_owner:
        if spare_claim:
            owner_source = "RUN_SPARE"
        elif configio_spare:
            owner_source = "CONFIGIO_SPARE"
        else:
            # Unused bit on installed / topology-mapped module
            owner_source = "CONFIGIO_MAPPED_UNUSED_BIT"
    elif state == OWNER_UNRESOLVED and not engineering_owner and owner_source == "NONE":
        owner_source = (
            "CONFIGIO_SIGNAL_UNBOUND" if configio_occupied else "OWNER_UNRESOLVED"
        )

    ch["engineering_owner"] = engineering_owner
    ch["owner_source"] = owner_source
    ch["owner_state"] = state
    ch["resolution_status"] = state
    ch["configio_occupied"] = bool(configio_occupied and not configio_spare)
    ch["configio_spare"] = bool(configio_spare)
    ch["configio_topology"] = bool(configio_topology and not configio_occupied and not configio_spare)
    # Flags consumed by Hardware UI / FlexRack
    ch["unresolved"] = state == OWNER_UNRESOLVED
    ch["is_unresolved"] = state == OWNER_UNRESOLVED
    ch["is_spare"] = state in (OWNER_PROVEN_SPARE, OWNER_ENGINEER_SPARE)
    if state == OWNER_UNRESOLVED:
        ch["rejection_reason"] = _rejection_reason_for_unresolved(
            owner_conflict=owner_conflict,
            owner_resolution_failed=owner_resolution_failed,
            configio_occupied=bool(configio_occupied and not configio_spare),
            explicit_reason=ch.get("rejection_reason") or ch.get("resolve_fail_reason"),
        )
    else:
        ch.pop("rejection_reason", None)
    if not ch.get("sourceName"):
        ch["sourceName"] = run_owner or (
            "SPARE"
            if (spare_claim or configio_spare or state == OWNER_PROVEN_SPARE)
            else ""
        )
    if ch.get("effectiveName") is None:
        ch["effectiveName"] = engineering_owner
    ch["run_source"] = "FORTNA/Conveyor.asc" if (run_owner or spare_claim) else (
        "Configio/eipcfg" if ep.get("channel") else None
    )
    return ch


def _channels_for_module(
    by_word_bit: dict[str, dict[str, Any]],
    *,
    rio_name: str,
    data_index: int | None,
    direction: str,
    logical_by_ch: dict[str, dict[str, Any]],
    claims: dict[str, Any] | None = None,
    machine: str = "",
    adapter: dict[str, Any] | None = None,
    module: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Channels from by_word_bit filtered by rio_name + data_index (flex_slot) + direction."""
    if data_index is None or not direction:
        return []
    want_rio = (rio_name or "").strip()
    want_dir = (direction or "").strip().upper()
    rows: list[dict[str, Any]] = []
    # Dedup by physical channel — Configio may fan multiple words; keep first word key
    seen_addr: set[str] = set()
    for key, hit in (by_word_bit or {}).items():
        if (hit.get("rio_name") or "").strip() != want_rio:
            continue
        if (hit.get("direction") or "").strip().upper() != want_dir:
            continue
        flex = hit.get("flex_slot")
        if flex is None:
            flex = hit.get("data_index")
        try:
            if int(flex) != int(data_index):
                continue
        except (TypeError, ValueError):
            continue
        parts = str(key).split(":", 1)
        try:
            fortna_word = int(parts[0])
            fortna_bit = int(parts[1]) if len(parts) > 1 else int(hit.get("bit") or 0)
        except (TypeError, ValueError):
            fortna_word = hit.get("octal_word")
            fortna_bit = hit.get("bit")
        physical_address = hit.get("channel")  # same string IO_MAP uses
        if physical_address and physical_address in seen_addr:
            continue
        if physical_address:
            seen_addr.add(physical_address)
        logical = logical_by_ch.get(physical_address) if physical_address else None
        prov = dict(hit.get("provenance") or {}) if isinstance(hit.get("provenance"), dict) else {}
        if hit.get("low_desc") and "low_desc" not in prov:
            prov["low_desc"] = hit.get("low_desc")
        if hit.get("high_desc") and "high_desc" not in prov:
            prov["high_desc"] = hit.get("high_desc")
        row = {
            "fortna_word": fortna_word,
            "fortna_bit": fortna_bit,
            "word_bit_key": key,
            "physical_address": physical_address,
            "direction": hit.get("direction"),
            "bit_half": hit.get("bit_half"),
            "logical_endpoint": logical,
            "provenance": prov or hit.get("provenance"),
            "assign_how": hit.get("assign_how"),
            "resolve_how": hit.get("resolve_how"),
            "panel": hit.get("panel"),
            "module_name": hit.get("module_name"),
            "type": hit.get("type"),
            "data_index": hit.get("data_index") if hit.get("data_index") is not None else flex,
            # Configio Desc evidence for Gate D spare vs occupied
            "low_desc": hit.get("low_desc"),
            "high_desc": hit.get("high_desc"),
            "configio_desc": (
                hit.get("high_desc")
                if str(hit.get("bit_half") or "").lower() == "high"
                else hit.get("low_desc")
            )
            or hit.get("low_desc")
            or hit.get("high_desc"),
        }
        enrich_channel_ownership(
            row,
            machine=machine,
            claims=claims,
            adapter=adapter,
            module=module or {
                "slot": hit.get("eip_slot"),
                "data_index": flex,
                "direction": hit.get("direction"),
                "type": hit.get("type"),
                "name": hit.get("module_name"),
                "family": hit.get("family"),
            },
        )
        rows.append(row)
    rows.sort(
        key=lambda r: (
            int(r.get("fortna_bit") or 0),
            int(r.get("fortna_word") or 0),
        )
    )
    return rows


def build_hardware_io_model(run_dir: Path | str, machine: str = "") -> dict[str, Any]:
    """Build Hardware/I/O JSON tree exclusively from PhysicalWordResolver."""
    run_dir = Path(run_dir)
    mach = (machine or "").strip()
    if not mach:
        try:
            mach = (read_project_meta(run_dir).get("machine_name") or "").strip()
        except Exception:
            mach = ""

    resolver = PhysicalWordResolver(run_dir, mach)
    pm = resolver.physical_map
    topo = resolver.topology
    panel_order = list(topo.get("panel_order") or [])
    by_word_bit = dict(pm.get("by_word_bit") or {})
    claims = _index_conveyor_claims(resolver)
    logical_by_ch = dict(claims.get("owners") or {})
    machine_name = pm.get("machine") or mach

    adapters_out: list[dict[str, Any]] = []
    adapters_by_panel: dict[str, list[dict[str, Any]]] = {p: [] for p in panel_order}

    for ad in pm.get("adapters") or []:
        rio = ad.get("rio_name") or ""
        panel = ad.get("panel")
        ad_stub = {
            "rio_name": rio,
            "eipcfg_name": ad.get("name") or "",
            "name": ad.get("name") or "",
            "panel": panel,
            "family": ad.get("family"),
            "targetip": ad.get("targetip") or "",
        }
        modules_out: list[dict[str, Any]] = []
        for mod in sorted(ad.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
            mtype = mod.get("type") or ""
            conn = mod.get("connection") or ""
            direction = mod.get("direction") or ""
            data_index = mod.get("data_index")
            mod_family = (
                mod.get("family")
                or detect_family_from_catalog(mtype)
            )
            # Drive devices are never Flex/POINT adapter cards (even if HEADNODE-tagged).
            is_drive = str(mod_family or "") == "ETHERNET_DRIVE"
            is_head = (not is_drive) and (
                (conn or "").upper() == "HEADNODE" or "AENT" in (mtype or "").upper()
            )
            mod_stub = {
                "slot": mod.get("slot"),
                "name": mod.get("name") or "",
                "type": mtype,
                "catalog": mtype,
                "direction": direction,
                "data_index": data_index,
                "family": mod_family,
            }
            channels = []
            if not is_head and direction:
                channels = _channels_for_module(
                    by_word_bit,
                    rio_name=rio,
                    data_index=data_index,
                    direction=direction,
                    logical_by_ch=logical_by_ch,
                    claims=claims,
                    machine=machine_name,
                    adapter=ad_stub,
                    module=mod_stub,
                )
            capacity = _module_channel_capacity(mtype, conn)
            used = sum(1 for c in channels if c.get("owner_state") == OWNER_ASSIGNED)
            unresolved_ch = sum(1 for c in channels if c.get("owner_state") == OWNER_UNRESOLVED)
            spare_ch = sum(
                1
                for c in channels
                if c.get("owner_state") in (OWNER_PROVEN_SPARE, OWNER_ENGINEER_SPARE)
            )
            mod_row = {
                "slot": mod.get("slot"),
                "name": mod.get("name") or "",
                "type": mtype,
                "catalog": mtype,
                "direction": direction,
                "connection": conn,
                "family": mod_family,
                "data_index": data_index,
                "is_adapter_card": bool(is_head),
                "channel_capacity": capacity,
                "channels_used": used,
                "channels_unresolved": unresolved_ch,
                "channels_spare": spare_ch,
                "channels": channels,
                "visual_support": (
                    "modeled"
                    if mod_family in ("1794", "1734") and capacity >= 0
                    else ("ethernet_drive" if is_drive else "generic")
                ),
            }
            mod_row["ownership_audit"] = module_ownership_audit_pass(mod_row)
            modules_out.append(mod_row)
        ad_family = (
            ad.get("family")
            or adapter_family_from_modules(modules_out)
        )
        adapter_tree = {
            "rio_name": rio,
            "eipcfg_name": ad.get("name") or "",
            "name": ad.get("name") or "",
            "targetip": ad.get("targetip") or "",
            "naming_how": ad.get("naming_how"),
            "panel": panel,
            "input_address": ad.get("input_address"),
            "output_address": ad.get("output_address"),
            "adapter_index": ad.get("adapter_index"),
            "family": ad_family,
            "renderer": renderer_for_family(ad_family),
            "modules": modules_out,
        }
        adapters_out.append(adapter_tree)
        if panel and panel in adapters_by_panel:
            adapters_by_panel[panel].append(adapter_tree)
        elif panel:
            adapters_by_panel.setdefault(panel, []).append(adapter_tree)

    families_present = sorted(
        {
            str(a.get("family") or "")
            for a in adapters_out
            if a.get("family") and a.get("family") != "UNKNOWN"
        }
    )
    scheme = pm.get("data_index_scheme") or topo.get("data_index_scheme")
    if len(families_present) == 1:
        scheme = family_scheme_description(families_present[0])
    elif families_present:
        scheme = "; ".join(family_scheme_description(f) for f in families_present)

    owner_counts = {s: 0 for s in OWNER_STATES}
    for a in adapters_out:
        for m in a.get("modules") or []:
            for c in m.get("channels") or []:
                st = c.get("owner_state") or OWNER_UNKNOWN
                owner_counts[st] = owner_counts.get(st, 0) + 1

    model = {
        "ok": True,
        "controller": {
            "machine": machine_name,
            "eipcfg_path": pm.get("eipcfg_path") or topo.get("eipcfg_path"),
            "data_index_scheme": scheme,
            "hardware_families": families_present,
        },
        "control_panels": {
            # Configio Desc evidence only — UI adds "All Panels"; never invent CPs
            "panels": panel_order,
            "all_panels_label": "All Panels",
            "adapters_by_panel": adapters_by_panel,
        },
        "adapters": adapters_out,
        "unresolved_words": list(pm.get("unresolved") or []),
        "owner_claim_conflicts": dict(claims.get("conflicts") or {}),
        "unresolved_named_points": list(claims.get("unresolved_named") or []),
        "stats": {
            **dict(pm.get("stats") or {}),
            "owner_states": owner_counts,
            "unresolved_owner_count": owner_counts.get(OWNER_UNRESOLVED, 0),
            "assigned_owner_count": owner_counts.get(OWNER_ASSIGNED, 0),
            "proven_spare_count": owner_counts.get(OWNER_PROVEN_SPARE, 0),
        },
        "io_word_map": resolver.io_word_map(),
        "provenance": {
            "source": "PhysicalWordResolver",
            "source_tables": ["Configio.asc", "eipcfg", "EIPModules", "Conveyor.asc"],
            "configio_row_count": topo.get("configio_row_count"),
            "panel_order": panel_order,
            "ownership_model": "physical_endpoint_separate_from_engineering_owner",
            "owner_states": list(OWNER_STATES),
        },
    }
    # Engineer overrides (name / Generate) — do not wipe RUN evidence
    try:
        apply_overrides_to_hardware_model(model, load_overrides())
    except Exception:
        pass
    # Re-stamp owner_state after overrides (engineer name / spare clear)
    _restamp_owner_states_after_overrides(model, claims, machine_name)
    return model


def _restamp_owner_states_after_overrides(
    model: dict[str, Any],
    claims: dict[str, Any],
    machine: str,
) -> None:
    """Re-apply Gate D owner classification after engineer override mutation."""
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for ch in mod.get("channels") or []:
                eng = str(ch.get("engineerName") or "").strip() or None
                if eng and is_clear_sentinel(eng):
                    eng = None
                    ch["engineerName"] = None
                # Engineer cleared to spare sentinel while physical endpoint remains
                if ch.get("cleared") or (
                    ch.get("generate") is not False
                    and eng is None
                    and not (ch.get("sourceName") or "").strip()
                    and ch.get("logical_endpoint") is None
                    and ch.get("engineer_synthesized")
                ):
                    ch["cleared_to_spare"] = True
                enrich_channel_ownership(
                    ch, machine=machine, claims=claims, adapter=ad, module=mod
                )
            # Refresh module counters
            channels = mod.get("channels") or []
            mod["channels_used"] = sum(
                1 for c in channels if c.get("owner_state") == OWNER_ASSIGNED
            )
            mod["channels_unresolved"] = sum(
                1 for c in channels if c.get("owner_state") == OWNER_UNRESOLVED
            )
            mod["channels_spare"] = sum(
                1
                for c in channels
                if c.get("owner_state") in (OWNER_PROVEN_SPARE, OWNER_ENGINEER_SPARE)
            )
    owner_counts = {s: 0 for s in OWNER_STATES}
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for c in mod.get("channels") or []:
                st = c.get("owner_state") or OWNER_UNKNOWN
                owner_counts[st] = owner_counts.get(st, 0) + 1
    stats = model.setdefault("stats", {})
    stats["owner_states"] = owner_counts
    stats["unresolved_owner_count"] = owner_counts.get(OWNER_UNRESOLVED, 0)
    stats["assigned_owner_count"] = owner_counts.get(OWNER_ASSIGNED, 0)
    stats["proven_spare_count"] = owner_counts.get(OWNER_PROVEN_SPARE, 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hardware/I/O model from PhysicalWordResolver")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--save-override",
        action="store_true",
        help="Upsert one channel override from --address / --name / --generate",
    )
    ap.add_argument("--address", default="", help="physical_address for --save-override")
    ap.add_argument("--name", default=None, help="engineer logical name (empty clears)")
    ap.add_argument("--source-name", default="", help="RUN-discovered source name")
    ap.add_argument("--generate", default=None, help="true/false — include in IO_MAP")
    ap.add_argument("--clear-overrides", action="store_true", help="Wipe engineer overrides")
    ap.add_argument("--project-identity", default="", help="JSON identity stamp")
    args = ap.parse_args(argv)

    if args.clear_overrides:
        from fortna_hardware_io_overrides import clear_overrides, empty_overrides, save_overrides

        clear_overrides()
        ident = {}
        if args.project_identity:
            try:
                ident = json.loads(args.project_identity)
            except Exception:
                ident = {}
        save_overrides(empty_overrides(ident))
        print(json.dumps({"ok": True, "cleared": True}))
        return 0

    if args.save_override:
        from fortna_hardware_io_overrides import (
            load_overrides,
            prune_inactive_overrides,
            save_overrides,
            should_clear_engineer,
            upsert_channel_override,
            validate_logical_name,
        )

        ov = load_overrides()
        if args.project_identity:
            try:
                ov["projectIdentity"] = json.loads(args.project_identity)
            except Exception:
                pass
        gen = None
        if args.generate is not None and str(args.generate).strip() != "":
            gen = str(args.generate).strip().lower() in ("1", "true", "yes", "y")
        name = args.name
        clear_eng = False
        if name is not None:
            ok, err = validate_logical_name(name)
            if not ok:
                print(json.dumps({"ok": False, "error": err}))
                return 1
            # Empty / SPARE / restore-to-source → purge engineer override (no stale names)
            if should_clear_engineer(name, args.source_name or ""):
                clear_eng = True
                name = ""
        try:
            cur = upsert_channel_override(
                ov,
                physical_address=args.address,
                source_name=args.source_name or "",
                engineer_name=None if clear_eng else name,
                generate=gen,
                clear_engineer=clear_eng,
            )
            prune_inactive_overrides(ov)
            save_overrides(ov)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "override": cur,
                        "address": args.address,
                        "cleared": bool(cur.get("cleared") or clear_eng),
                    }
                )
            )
            return 0
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1

    run_dir = args.run_dir
    if run_dir is None:
        for cand in (
            REPO_ROOT / "workspace" / "active" / "RUN",
            REPO_ROOT / "workspace" / "active_work" / "RUN",
        ):
            if (cand / "project.cfg").is_file():
                run_dir = cand
                break
    if run_dir is None or not Path(run_dir).exists():
        err = {"ok": False, "error": "No RUN directory (pass --run-dir or load active RUN)"}
        print(json.dumps(err))
        return 1

    try:
        model = build_hardware_io_model(run_dir, args.machine)
    except Exception as e:
        err = {"ok": False, "error": str(e)}
        print(json.dumps(err))
        return 1

    # Gate 7 — summary line into exports/logs (best-effort)
    try:
        from fortna_site_forge_log import append_log

        stats = model.get("stats") or {}
        adapters = model.get("adapters") or []
        mod_n = sum(len(a.get("modules") or []) for a in adapters)
        ch_n = sum(
            len(m.get("channels") or [])
            for a in adapters
            for m in (a.get("modules") or [])
        )
        append_log(
            "hardware_io_model_build",
            {
                "ok": True,
                "machine": (model.get("controller") or {}).get("machine"),
                "run_dir": str(run_dir),
                "adapters": len(adapters),
                "modules": mod_n,
                "channels": ch_n,
                "owner_states": (stats.get("owner_states") or {}),
                "unresolved_owner_count": stats.get("unresolved_owner_count"),
                "assigned_owner_count": stats.get("assigned_owner_count"),
            },
        )
    except Exception:
        pass

    text = json.dumps(model, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
