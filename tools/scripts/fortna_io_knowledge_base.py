#!/usr/bin/env python3
"""Versioned persistent Fortna I/O knowledge registry.

Stores SEMANTIC nomenclature patterns only — never site-specific physical
addresses (e.g. AENTR1:I.Data[3].2). Engineer confirmations and accepted-site
devices can teach pattern → equipment_class / Fortna+ UDT bool targets.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_io_equipment_classifier import (
    classify_equipment,
    map_equipment_to_device_type,
)

KB_FILENAME = "fortna_io_knowledge_base.json"
KB_VERSION = 1

_PHYSICAL_ADDR_RE = re.compile(
    r"(?::[IO]\.|\.Data\[|:I\.|:O\.|Local:\d+|AENT\w*\d*:)",
    re.I,
)

_MATCH_RANK = {
    "exact": 0,
    "prefix": 1,
    "suffix": 2,
    "token": 3,
    "regex": 4,
}

_CONF_RANK = {
    "PROVEN": 0,
    "DERIVED": 1,
    "REVIEW_REQUIRED": 2,
    "UNKNOWN": 3,
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _looks_like_physical_endpoint(value: Any) -> bool:
    s = _norm(value)
    if not s:
        return False
    return bool(_PHYSICAL_ADDR_RE.search(s))


def default_kb_path(repo_or_workspace: Path | str | None = None) -> Path:
    """Resolve workspace/fortna_io_knowledge_base.json (repo or workspace root)."""
    if repo_or_workspace:
        root = Path(repo_or_workspace)
        if (root / "workspace").is_dir():
            return root / "workspace" / KB_FILENAME
        if root.name == "workspace":
            return root / KB_FILENAME
        # Treat as workspace-ish directory even if not named workspace
        if root.is_dir():
            ws = root / "workspace"
            if ws.is_dir():
                return ws / KB_FILENAME
            return root / KB_FILENAME
    cwd = Path.cwd()
    if (cwd / "workspace").is_dir():
        return cwd / "workspace" / KB_FILENAME
    if cwd.name == "workspace":
        return cwd / KB_FILENAME
    # Script lives in tools/scripts → repo root is parents[2]
    repo = Path(__file__).resolve().parents[2]
    if (repo / "workspace").is_dir():
        return repo / "workspace" / KB_FILENAME
    return cwd / KB_FILENAME


def _empty_kb(path: Path | None = None) -> dict[str, Any]:
    return {
        "version": KB_VERSION,
        "updated_at": _ts(),
        "patterns": {},
        "path": str(path or default_kb_path()),
    }


def load_knowledge_base(path: Path | str | None = None) -> dict:
    p = Path(path) if path else default_kb_path()
    if not p.is_file():
        kb = _empty_kb(p)
        return kb
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        kb = _empty_kb(p)
        kb["load_error"] = True
        return kb
    if not isinstance(data, dict):
        return _empty_kb(p)
    data.setdefault("version", KB_VERSION)
    data.setdefault("patterns", {})
    if not isinstance(data["patterns"], dict):
        data["patterns"] = {}
    data["path"] = str(p)
    return data


def save_knowledge_base(kb: dict, path: Path | str | None = None) -> Path:
    p = Path(path) if path else Path(kb.get("path") or default_kb_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    patterns = kb.get("patterns") or {}
    # Strip any accidentally stored physical addresses before write
    clean_patterns: dict[str, Any] = {}
    for key, row in patterns.items():
        if not isinstance(row, dict):
            continue
        out = dict(row)
        for addr_key in (
            "physical_endpoint",
            "endpoint",
            "module_data_ref",
            "logix_address",
            "address",
        ):
            if addr_key in out:
                if _looks_like_physical_endpoint(out.get(addr_key)):
                    out["mapping_behavior"] = out.get("mapping_behavior") or (
                        "engineer_assigned_endpoint"
                    )
                out.pop(addr_key, None)
        # Never persist address-like strings in freeform fields
        for fk in ("fortna_plus_udt_aoi_bool_target", "source_evidence_pattern", "pattern"):
            if _looks_like_physical_endpoint(out.get(fk)):
                out.pop(fk, None)
        clean_patterns[str(key)] = out
    payload = {
        "version": int(kb.get("version") or KB_VERSION),
        "updated_at": _ts(),
        "patterns": clean_patterns,
    }
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    kb["path"] = str(p)
    kb["updated_at"] = payload["updated_at"]
    kb["patterns"] = clean_patterns
    return p


def _seed_row(
    *,
    key: str,
    pattern: str,
    match_kind: str,
    equipment_class: str,
    fortna_hint: str = "",
    hardware_family: str = "",
    mapping_behavior: str = "semantic_nomenclature",
    ownership_heuristic: str = "name_pattern_only",
    source_evidence_pattern: str = "",
    confidence: str = "PROVEN",
) -> dict[str, Any]:
    return {
        "pattern": pattern,
        "match_kind": match_kind,
        "equipment_class": equipment_class,
        "source_evidence_pattern": source_evidence_pattern or pattern,
        "hardware_family": hardware_family or map_equipment_to_device_type(equipment_class),
        "mapping_behavior": mapping_behavior,
        "fortna_plus_udt_aoi_bool_target": fortna_hint,
        "ownership_heuristic": ownership_heuristic,
        "accepted_engineer_decision": "",
        "provenance": {
            "site": "",
            "confirmed_by": "seed",
            "confirmed_at": _ts(),
            "source": "seed",
        },
        "confidence": confidence,
        "hit_count": 0,
        "_key": key,
    }


def seed_builtin_patterns(kb: dict) -> dict:
    """Idempotent seed of strong nomenclature patterns (no addresses)."""
    patterns = dict(kb.get("patterns") or {})
    seeds = [
        _seed_row(
            key="PBSTART",
            pattern="PBSTART",
            match_kind="token",
            equipment_class="CONTROL_STATION_START_PB",
            fortna_hint="CPx_CS.I.Start_PB",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="*PBSTART",
        ),
        _seed_row(
            key="PBSTOP",
            pattern="PBSTOP",
            match_kind="token",
            equipment_class="CONTROL_STATION_STOP_PB",
            fortna_hint="CPx_CS.I.Stop_PB",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="*PBSTOP",
        ),
        _seed_row(
            key="PBRESET",
            pattern="PBRESET",
            match_kind="token",
            equipment_class="CONTROL_STATION_RESET_PB",
            fortna_hint="CPx_CS.I.Reset_PB",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="*PBRESET",
        ),
        _seed_row(
            key="PLT_SUFFIX",
            pattern="_PLT",
            match_kind="suffix",
            equipment_class="CONTROL_STATION_OUTPUT",
            fortna_hint="CPx_CS.O.*",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="*_PLT / *_PL / *.PLT",
        ),
        _seed_row(
            key="ESPB",
            pattern="ESPB",
            match_kind="prefix",
            equipment_class="SAFETY_ESTOP_PB",
            hardware_family="ESPB",
            source_evidence_pattern="ESPB*",
        ),
        _seed_row(
            key="ESLS",
            pattern="ESLS",
            match_kind="prefix",
            equipment_class="SAFETY_SWITCH",
            hardware_family="ESLS",
            source_evidence_pattern="ESLS*",
        ),
        _seed_row(
            key="ESR",
            pattern="ESR",
            match_kind="prefix",
            equipment_class="SAFETY_RELAY",
            hardware_family="ESR",
            source_evidence_pattern="ESR*",
            confidence="DERIVED",
        ),
        _seed_row(
            key="MCR",
            pattern="MCR",
            match_kind="prefix",
            equipment_class="MASTER_CONTROL_RELAY",
            hardware_family="MCR",
            source_evidence_pattern="MCR*",
            confidence="DERIVED",
        ),
        _seed_row(
            key="PE_DIGIT",
            pattern=r"^PE\d",
            match_kind="regex",
            equipment_class="PHOTOEYE",
            fortna_hint="PEx.I.PE_Clear",
            hardware_family="PHOTOEYE",
            source_evidence_pattern="^PE\\d",
        ),
        _seed_row(
            key="PHOTOEYE",
            pattern="PHOTOEYE",
            match_kind="token",
            equipment_class="PHOTOEYE",
            fortna_hint="PEx.I.PE_Clear",
            hardware_family="PHOTOEYE",
        ),
        _seed_row(
            key="VFD",
            pattern="VFD",
            match_kind="prefix",
            equipment_class="DRIVE",
            hardware_family="VFD",
            source_evidence_pattern="VFD*",
        ),
        _seed_row(
            key="MS_PREFIX",
            pattern="MS_",
            match_kind="prefix",
            equipment_class="MOTOR_EQUIPMENT",
            hardware_family="MOTOR",
            source_evidence_pattern="MS_*",
            confidence="DERIVED",
        ),
        _seed_row(
            key="MTR",
            pattern="MTR",
            match_kind="token",
            equipment_class="MOTOR_EQUIPMENT",
            hardware_family="MOTOR",
            confidence="DERIVED",
        ),
        _seed_row(
            key="STARTER",
            pattern="STARTER",
            match_kind="token",
            equipment_class="MOTOR_EQUIPMENT",
            hardware_family="MOTOR",
            confidence="DERIVED",
        ),
        _seed_row(
            key="PB_DIGIT",
            pattern=r"(?:^|[^A-Z0-9])PB\d",
            match_kind="regex",
            equipment_class="PUSHBUTTON_CONTROL",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="PB#",
        ),
        _seed_row(
            key="SS_DIGIT",
            pattern=r"(?:^|_)SS\d",
            match_kind="regex",
            equipment_class="PUSHBUTTON_CONTROL",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="SS#",
        ),
        _seed_row(
            key="RS_DIGIT",
            pattern=r"(?:^|_)RS\d",
            match_kind="regex",
            equipment_class="PUSHBUTTON_CONTROL",
            hardware_family="PUSHBUTTON_CONTROL",
            source_evidence_pattern="RS#",
        ),
        _seed_row(
            key="MEM_PREFIX",
            pattern="MEM_",
            match_kind="prefix",
            equipment_class="INTERNAL_LOGICAL",
            hardware_family="INTERNAL_LOGICAL",
            mapping_behavior="internal_logical_skip_physical",
            ownership_heuristic="never_physical_endpoint",
        ),
        _seed_row(
            key="ES_PE_COMPOUND",
            pattern="ES_PE_",
            match_kind="prefix",
            equipment_class="AMBIGUOUS",
            hardware_family="IO",
            mapping_behavior="review_required",
            ownership_heuristic="compound_safety_pe",
            confidence="REVIEW_REQUIRED",
        ),
        _seed_row(
            key="SPARE",
            pattern="SPARE",
            match_kind="exact",
            equipment_class="PHYSICAL_CHANNEL",
            hardware_family="PHYSICAL_CHANNEL",
            mapping_behavior="physical_unused_channel",
            ownership_heuristic="explicit_spare_token",
        ),
        _seed_row(
            key="STATUS_SUFFIX",
            pattern="_STATUS",
            match_kind="suffix",
            equipment_class="INTERNAL_LOGICAL",
            hardware_family="INTERNAL_LOGICAL",
            mapping_behavior="internal_logical_skip_physical",
            confidence="DERIVED",
        ),
        _seed_row(
            key="ENABLE_SUFFIX",
            pattern="_ENABLE",
            match_kind="suffix",
            equipment_class="INTERNAL_LOGICAL",
            hardware_family="INTERNAL_LOGICAL",
            mapping_behavior="internal_logical_skip_physical",
            confidence="DERIVED",
        ),
    ]
    added = 0
    for row in seeds:
        key = row.pop("_key")
        if key in patterns:
            # Idempotent: keep existing, do not overwrite engineer-confirmed rows
            continue
        patterns[key] = row
        added += 1
    kb["patterns"] = patterns
    kb["version"] = int(kb.get("version") or KB_VERSION)
    kb["seed_added"] = added
    kb["seed_total"] = len(seeds)
    return kb


def _pattern_matches(name: str, row: dict[str, Any]) -> bool:
    n = _norm(name)
    u = n.upper()
    pat = _norm(row.get("pattern"))
    if not pat:
        return False
    kind = _norm(row.get("match_kind") or "token").lower()
    pu = pat.upper()
    if kind == "exact":
        return u == pu
    if kind == "prefix":
        return u.startswith(pu) or f"_{pu}" in u
    if kind == "suffix":
        return u.endswith(pu)
    if kind == "regex":
        try:
            return bool(re.search(pat, n, re.I))
        except re.error:
            return False
    # token (default): substring token boundary-ish
    if pu in u:
        return True
    return False


def match_knowledge(name: str, kb: dict | None = None) -> list[dict]:
    """Return ranked knowledge matches for a device name."""
    store = kb if kb is not None else load_knowledge_base()
    patterns = store.get("patterns") or {}
    hits: list[dict[str, Any]] = []
    for key, row in patterns.items():
        if not isinstance(row, dict):
            continue
        if not _pattern_matches(name, row):
            continue
        hit = dict(row)
        hit["pattern_key"] = key
        hit["_match_rank"] = _MATCH_RANK.get(
            _norm(row.get("match_kind") or "token").lower(), 9
        )
        hit["_conf_rank"] = _CONF_RANK.get(
            _norm(row.get("confidence") or "UNKNOWN").upper(), 9
        )
        hits.append(hit)
    hits.sort(
        key=lambda h: (
            h.get("_match_rank", 9),
            h.get("_conf_rank", 9),
            -int(h.get("hit_count") or 0),
            _norm(h.get("pattern_key")),
        )
    )
    for h in hits:
        h.pop("_match_rank", None)
        h.pop("_conf_rank", None)
    return hits


def _pattern_key_from_name(name: str, equipment_class: str) -> str:
    u = _norm(name).upper()
    # Prefer stable semantic stems over full site-specific instance names
    for token in (
        "PBSTART",
        "PBSTOP",
        "PBRESET",
        "ESPB",
        "ESLS",
        "ESR",
        "MCR",
        "PHOTOEYE",
        "VFD",
        "STARTER",
        "MEM_",
        "ES_PE_",
        "SPARE",
    ):
        if token in u or u.startswith(token.rstrip("_")):
            return f"LEARNED_{token.rstrip('_')}"
    m = re.match(r"^([A-Z]+)", u)
    stem = m.group(1) if m else re.sub(r"[^A-Z0-9]+", "_", u)[:32]
    ec = _norm(equipment_class).upper() or "UNKNOWN"
    return f"LEARNED_{stem}_{ec}"


def learn_from_engineer_confirmation(
    confirmation: dict,
    *,
    site: str = "",
    kb: dict | None = None,
    path: Path | str | None = None,
) -> dict:
    """Learn SEMANTIC pattern from engineer confirmation.

    Strips/rejects physical_endpoint values that look like Logix module addresses.
    """
    store = kb if kb is not None else load_knowledge_base(path)
    store = seed_builtin_patterns(store)
    patterns = dict(store.get("patterns") or {})

    name = _norm(
        confirmation.get("canonical_device")
        or confirmation.get("canonical_name")
        or confirmation.get("name")
        or confirmation.get("device_name")
    )
    if not name:
        return {"ok": False, "error": "name required", "kb": store}

    equipment_class = _norm(
        confirmation.get("equipment_class")
        or confirmation.get("device_class")
        or ""
    ).upper()
    fortna_hint = _norm(
        confirmation.get("fortna_plus_hint")
        or confirmation.get("fortna_plus_udt_aoi_bool_target")
        or confirmation.get("semantic_target")
        or ""
    )
    if _looks_like_physical_endpoint(fortna_hint):
        fortna_hint = ""

    if not equipment_class:
        classified = classify_equipment(
            name,
            highlight=_norm(confirmation.get("highlight")),
            extra=confirmation if isinstance(confirmation, dict) else None,
        )
        equipment_class = classified.get("equipment_class") or "UNKNOWN"
        fortna_hint = fortna_hint or classified.get("fortna_plus_hint") or ""

    physical = _norm(
        confirmation.get("physical_endpoint")
        or confirmation.get("endpoint")
        or confirmation.get("module_data_ref")
        or ""
    )
    mapping_behavior = _norm(confirmation.get("mapping_behavior")) or "semantic_nomenclature"
    if physical and _looks_like_physical_endpoint(physical):
        mapping_behavior = "engineer_assigned_endpoint"
        # Intentionally do NOT store the address string
        physical = ""

    key = _norm(confirmation.get("pattern_key")) or _pattern_key_from_name(
        name, equipment_class
    )
    match_kind = _norm(confirmation.get("match_kind")) or "token"
    # Derive a stable pattern token from the name when possible
    pattern = _norm(confirmation.get("pattern"))
    if not pattern:
        for token in (
            "PBSTART",
            "PBSTOP",
            "PBRESET",
            "ESPB",
            "ESLS",
            "ESR",
            "MCR",
            "VFD",
            "MEM_",
            "ES_PE_",
            "SPARE",
        ):
            if token in name.upper():
                pattern = token
                match_kind = "prefix" if token.endswith("_") or token in {
                    "ESPB",
                    "ESLS",
                    "ESR",
                    "MCR",
                    "VFD",
                } else "token"
                break
        if not pattern:
            pattern = re.sub(r"\d+", "", name.upper())[:24] or name.upper()
            match_kind = "token"

    prev = patterns.get(key) if isinstance(patterns.get(key), dict) else {}
    hit_count = int(prev.get("hit_count") or 0) + 1
    row = {
        "pattern": pattern,
        "match_kind": match_kind,
        "equipment_class": equipment_class,
        "source_evidence_pattern": _norm(confirmation.get("source_evidence_pattern"))
        or pattern,
        "hardware_family": _norm(confirmation.get("hardware_family"))
        or map_equipment_to_device_type(equipment_class),
        "mapping_behavior": mapping_behavior,
        "fortna_plus_udt_aoi_bool_target": fortna_hint,
        "ownership_heuristic": _norm(confirmation.get("ownership_heuristic"))
        or "engineer_confirmed_semantic",
        "accepted_engineer_decision": _norm(
            confirmation.get("classification")
            or confirmation.get("final_status")
            or confirmation.get("accepted_engineer_decision")
            or "ENGINEER_CONFIRMED"
        ),
        "provenance": {
            "site": _norm(site or confirmation.get("site")),
            "confirmed_by": _norm(confirmation.get("confirmed_by") or "engineer"),
            "confirmed_at": _norm(confirmation.get("confirmed_at")) or _ts(),
            "source": "engineer_confirm",
        },
        "confidence": _norm(confirmation.get("confidence") or "PROVEN").upper(),
        "hit_count": hit_count,
    }
    patterns[key] = row
    store["patterns"] = patterns
    out_path = save_knowledge_base(store, path)
    return {
        "ok": True,
        "pattern_key": key,
        "pattern": row,
        "rejected_physical_endpoint": bool(
            _looks_like_physical_endpoint(
                confirmation.get("physical_endpoint")
                or confirmation.get("endpoint")
                or confirmation.get("module_data_ref")
                or ""
            )
        ),
        "path": str(out_path),
        "kb": store,
    }


def learn_from_accepted_site(
    devices: list[dict],
    *,
    site: str = "",
    kb: dict | None = None,
    path: Path | str | None = None,
) -> dict:
    """Learn from ENGINEER_CONFIRMED / MAPPED devices with clear nomenclature."""
    store = kb if kb is not None else load_knowledge_base(path)
    store = seed_builtin_patterns(store)
    learned = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    accepted = {"ENGINEER_CONFIRMED", "MAPPED"}

    for d in devices or []:
        if not isinstance(d, dict):
            skipped += 1
            continue
        status = _norm(
            d.get("final_status") or d.get("status") or d.get("mapping_status")
        ).upper()
        if status not in accepted:
            skipped += 1
            continue
        name = _norm(
            d.get("canonical_name")
            or d.get("canonical_device")
            or d.get("name")
            or d.get("fortna_name")
            or d.get("source_signal")
        )
        if not name:
            skipped += 1
            continue
        # Require clear nomenclature — classifier must not be UNKNOWN/AMBIGUOUS
        # unless engineer supplied equipment_class explicitly.
        ec = _norm(d.get("equipment_class") or d.get("device_class")).upper()
        classified = classify_equipment(
            name,
            highlight=_norm(d.get("highlight") or d.get("device_type")),
            extra=d,
        )
        if not ec:
            ec = classified.get("equipment_class") or ""
        if ec in {"", "UNKNOWN", "AMBIGUOUS"} and not d.get("equipment_class"):
            skipped += 1
            continue
        conf = {
            "canonical_device": name,
            "equipment_class": ec,
            "fortna_plus_hint": _norm(
                d.get("fortna_plus_hint")
                or d.get("fortna_plus_udt_aoi_bool_target")
                or classified.get("fortna_plus_hint")
            ),
            "physical_endpoint": _norm(
                d.get("physical_endpoint") or d.get("endpoint") or d.get("module_data_ref")
            ),
            "highlight": _norm(d.get("highlight")),
            "final_status": status,
            "confirmed_by": _norm(d.get("confirmed_by") or "accepted_site"),
            "confidence": "PROVEN" if status == "ENGINEER_CONFIRMED" else "DERIVED",
        }
        res = learn_from_engineer_confirmation(
            conf, site=site, kb=store, path=path
        )
        # learn_from_engineer_confirmation already saved; keep store in sync
        if res.get("ok"):
            store = res.get("kb") or store
            # Retag provenance source as accepted_site
            pk = res.get("pattern_key")
            if pk and pk in (store.get("patterns") or {}):
                prov = dict(store["patterns"][pk].get("provenance") or {})
                prov["source"] = "accepted_site"
                prov["site"] = _norm(site) or prov.get("site") or ""
                store["patterns"][pk]["provenance"] = prov
            learned += 1
            results.append(res)
        else:
            skipped += 1

    out_path = save_knowledge_base(store, path)
    return {
        "ok": True,
        "learned": learned,
        "skipped": skipped,
        "results": results,
        "pattern_count": len(store.get("patterns") or {}),
        "path": str(out_path),
        "kb": store,
    }


if __name__ == "__main__":
    kb = seed_builtin_patterns(load_knowledge_base())
    # Don't persist seed during self-check unless workspace write is desired;
    # operate in-memory and report counts.
    print(f"kb_path={default_kb_path()}")
    print(f"seed_pattern_count={len(kb.get('patterns') or {})}")
    for name in (
        "PBSTART",
        "PB6_JR",
        "ESPB22",
        "MEM_FOO",
        "ES_PE_X",
        "SPARE",
        "VFD1",
    ):
        hits = match_knowledge(name, kb)
        top = hits[0] if hits else None
        if top:
            print(
                f"{name:12} matches={len(hits)} "
                f"top={top.get('pattern_key')}→{top.get('equipment_class')} "
                f"hint={top.get('fortna_plus_udt_aoi_bool_target')!r}"
            )
        else:
            print(f"{name:12} matches=0")

    # Physical address must not be stored
    learned = learn_from_engineer_confirmation(
        {
            "canonical_device": "3PBSTART",
            "equipment_class": "CONTROL_STATION_START_PB",
            "fortna_plus_hint": "CP3_CS.I.Start_PB",
            "physical_endpoint": "AENTR1:I.Data[3].2",
            "classification": "ENGINEER_CONFIRMED",
        },
        site="SELFCHECK",
        kb=dict(kb),
        path=Path(kb.get("path") or default_kb_path()).with_name(
            "_selfcheck_fortna_io_knowledge_base.json"
        ),
    )
    row = (learned.get("pattern") or {})
    dumped = json.dumps(row)
    assert "AENTR1" not in dumped, "physical address leaked into KB pattern"
    assert row.get("mapping_behavior") == "engineer_assigned_endpoint"
    assert learned.get("rejected_physical_endpoint") is True
    print(
        f"learn_ok rejected_physical={learned.get('rejected_physical_endpoint')} "
        f"mapping_behavior={row.get('mapping_behavior')} hint={row.get('fortna_plus_udt_aoi_bool_target')!r}"
    )
    # Cleanup self-check file
    p = Path(learned.get("path") or "")
    if p.is_file() and p.name.startswith("_selfcheck_"):
        p.unlink()
        print(f"cleaned {p}")
