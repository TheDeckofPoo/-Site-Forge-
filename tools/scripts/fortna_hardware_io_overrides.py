#!/usr/bin/env python3
"""Engineer overrides for Hardware/I/O channels.

Preserves RUN-discovered source names. Engineer name is a LOGICAL identity only.

Physical address / module (e.g. CP2RIO0:O.Data[6].6 / CP2RIO0) is IMMUTABLE
from Name edits. generate=False mutes the channel from IO_MAP without deleting
evidence.

Cleared / SPARE / restore-to-source MUST remove engineerName from persistence
so stale logical names cannot re-enter Autogen / IO_MAP / preflight.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_OVERRIDES_PATH = REPO_ROOT / "workspace" / "hardware_io_overrides.json"

# Rockwell tag / member path: Tag or Tag.Member.SubMember (no spaces, leading digit ok for UDT members)
_LOGICAL_NAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)

# Names that mean "no engineer override" — never persist as active logical identity
_CLEAR_SENTINELS = frozenset(
    {"", "SPARE", "—", "-", "N/A", "NONE", "NULL", "(CLEARED)", "(SPARE)"}
)


def overrides_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else DEFAULT_OVERRIDES_PATH


def empty_overrides(project_identity: dict | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "projectIdentity": project_identity or {},
        "channels": {},  # physical_address → override
    }


def load_overrides(path: Path | str | None = None) -> dict[str, Any]:
    p = overrides_path(path)
    if not p.is_file():
        return empty_overrides()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return empty_overrides()
    if not isinstance(data, dict):
        return empty_overrides()
    data.setdefault("version", 1)
    data.setdefault("projectIdentity", {})
    data.setdefault("channels", {})
    if not isinstance(data["channels"], dict):
        data["channels"] = {}
    return data


def save_overrides(data: dict[str, Any], path: Path | str | None = None) -> Path:
    p = overrides_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": int(data.get("version") or 1),
        "projectIdentity": data.get("projectIdentity") or {},
        "channels": data.get("channels") or {},
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def clear_overrides(path: Path | str | None = None) -> None:
    p = overrides_path(path)
    try:
        if p.is_file():
            p.unlink()
    except Exception:
        pass


def is_clear_sentinel(name: str | None) -> bool:
    """True when the Name field means 'no engineer override'."""
    return str(name or "").strip().upper() in _CLEAR_SENTINELS


def should_clear_engineer(engineer_name: str | None, source_name: str = "") -> bool:
    """Clear when empty/SPARE/sentinel OR when engineer restored the RUN source name."""
    eng = str(engineer_name or "").strip()
    if is_clear_sentinel(eng):
        return True
    src = str(source_name or "").strip()
    if src and eng.lower() == src.lower():
        return True
    return False


def validate_logical_name(name: str) -> tuple[bool, str]:
    """Validate Rockwell-style identifier or member path. Empty/SPARE = clear override."""
    s = (name or "").strip()
    if not s or is_clear_sentinel(s):
        return True, ""
    if not _LOGICAL_NAME_RE.match(s):
        return (
            False,
            "Invalid logical name — use Tag or Tag.Member (letters/digits/underscore, "
            "no spaces). Example: P402_Conv.O.Run or Fan_Starter",
        )
    if len(s) > 80:
        return False, "Logical name too long (max 80 characters)"
    return True, ""


def effective_name(source_name: str, engineer_name: str | None) -> str:
    eng = (engineer_name or "").strip()
    if eng and not is_clear_sentinel(eng):
        return eng
    return (source_name or "").strip()


def channel_override(overrides: dict[str, Any], physical_address: str) -> dict[str, Any]:
    ch = (overrides.get("channels") or {}).get(physical_address) or {}
    eng = str(ch.get("engineerName") or "").strip() or None
    if eng and is_clear_sentinel(eng):
        eng = None
    return {
        "sourceName": str(ch.get("sourceName") or "").strip(),
        "engineerName": eng,
        "generate": True if ch.get("generate") is None else bool(ch.get("generate")),
        "muted": False if ch.get("generate") is None else (not bool(ch.get("generate"))),
        "updatedAt": ch.get("updatedAt"),
    }


def _channel_entry_is_default(cur: dict[str, Any]) -> bool:
    """True when entry has no active engineer name and Generate is default ON."""
    eng = str(cur.get("engineerName") or "").strip()
    if eng and not is_clear_sentinel(eng):
        return False
    gen = cur.get("generate")
    if gen is False:
        return False  # explicit mute — keep evidence
    return True


def prune_inactive_overrides(overrides: dict[str, Any]) -> int:
    """Remove channel entries that no longer carry engineer name or mute.

    Prevents stale logical names from surviving a revert into Autogen.
    Returns number of pruned addresses.
    """
    channels = overrides.get("channels") or {}
    drop: list[str] = []
    for addr, cur in list(channels.items()):
        if not isinstance(cur, dict) or _channel_entry_is_default(cur):
            drop.append(addr)
    for addr in drop:
        channels.pop(addr, None)
    return len(drop)


def upsert_channel_override(
    overrides: dict[str, Any],
    *,
    physical_address: str,
    source_name: str = "",
    engineer_name: str | None = None,
    generate: bool | None = None,
    clear_engineer: bool = False,
) -> dict[str, Any]:
    addr = (physical_address or "").strip()
    if not addr:
        raise ValueError("physical_address required")
    channels = overrides.setdefault("channels", {})
    cur = dict(channels.get(addr) or {})
    if source_name and not cur.get("sourceName"):
        cur["sourceName"] = source_name
    elif source_name:
        # Keep original RUN discovery; only set if empty
        cur.setdefault("sourceName", source_name)

    src_for_clear = str(cur.get("sourceName") or source_name or "").strip()
    if clear_engineer or (
        engineer_name is not None and should_clear_engineer(engineer_name, src_for_clear)
    ):
        cur.pop("engineerName", None)
        clear_engineer = True
    elif engineer_name is not None:
        ok, err = validate_logical_name(engineer_name)
        if not ok:
            raise ValueError(err)
        cleaned = (engineer_name or "").strip()
        if cleaned:
            cur["engineerName"] = cleaned
        else:
            cur.pop("engineerName", None)
            clear_engineer = True

    if generate is not None:
        cur["generate"] = bool(generate)
    elif "generate" not in cur:
        cur["generate"] = True
    from datetime import datetime, timezone

    cur["updatedAt"] = datetime.now(timezone.utc).isoformat()

    # Drop entirely when no engineer identity and Generate left at default
    if _channel_entry_is_default(cur):
        channels.pop(addr, None)
        return {
            "sourceName": src_for_clear,
            "engineerName": None,
            "generate": True,
            "muted": False,
            "cleared": True,
            "updatedAt": cur.get("updatedAt"),
        }

    channels[addr] = cur
    return cur


def _parse_channel_addr(addr: str) -> tuple[str, str, int, int] | None:
    m = re.match(
        r"^([A-Za-z0-9_]+):(I|O)\.Data\[(\d+)\]\.(\d+)$",
        str(addr or "").strip(),
        re.I,
    )
    if not m:
        return None
    return m.group(1), m.group(2).upper(), int(m.group(3)), int(m.group(4))


def _apply_one_channel(ch: dict[str, Any], o: dict[str, Any]) -> None:
    """Stamp engineer override fields onto one channel dict (in place).

    Override file is authoritative for engineerName. Do NOT resurrect a stale
    in-memory engineerName when the persisted override was cleared.
    """
    le = ch.get("logical_endpoint") or {}
    src = ""
    if isinstance(le, dict):
        if le.get("engineer_override") and le.get("source_name"):
            src = str(le.get("source_name") or "").strip()
        else:
            src = str(le.get("name") or "").strip()
    source_name = str(o.get("sourceName") or ch.get("sourceName") or src or "").strip()
    raw_eng = str(o.get("engineerName") or "").strip() or None
    if raw_eng and is_clear_sentinel(raw_eng):
        raw_eng = None
    if raw_eng and should_clear_engineer(raw_eng, source_name):
        raw_eng = None
    engineer_name = raw_eng
    generate = True if o.get("generate") is None else bool(o.get("generate"))
    # NOTE: do not fall back to ch['engineerName'] — that reintroduces stale names
    # after a clear/revert when the override dict no longer lists the address.
    eff = effective_name(source_name, engineer_name)
    ch["sourceName"] = source_name
    ch["engineerName"] = engineer_name
    ch["effectiveName"] = eff or None
    ch["generate"] = generate
    ch["muted"] = not generate
    if engineer_name:
        ch["logical_endpoint"] = {
            **(le if isinstance(le, dict) else {}),
            "name": engineer_name,
            "source_name": source_name or None,
            "engineer_override": True,
        }
    elif isinstance(le, dict):
        # Restore RUN source as logical endpoint display; drop override flag
        restored = {
            **le,
            "name": source_name or le.get("source_name") or le.get("name") or "",
            "engineer_override": False,
        }
        if source_name:
            restored["source_name"] = source_name
        ch["logical_endpoint"] = restored if restored.get("name") else None
    else:
        ch["logical_endpoint"] = {"name": source_name} if source_name else None


def apply_overrides_to_hardware_model(
    model: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate HardwareIOModel channels with engineer override fields (in place).

    Also synthesizes channel stubs for SPARE bits the engineer named/muted so
    overrides survive model rebuild / refresh (not only in-session patch).
    """
    ov = overrides if overrides is not None else load_overrides()
    channels_ov = ov.get("channels") or {}

    # Index existing channels by physical_address
    by_addr: dict[str, dict[str, Any]] = {}
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for ch in mod.get("channels") or []:
                addr = (ch.get("physical_address") or "").strip()
                if addr:
                    by_addr[addr] = ch

    # Apply to existing channels
    for addr, o in channels_ov.items():
        ch = by_addr.get(addr)
        if ch is not None:
            _apply_one_channel(ch, o if isinstance(o, dict) else {})

    # Synthesize missing SPARE channels that have engineer overrides
    for addr, o in channels_ov.items():
        if addr in by_addr:
            continue
        if not isinstance(o, dict):
            continue
        eng = str(o.get("engineerName") or "").strip()
        gen = True if o.get("generate") is None else bool(o.get("generate"))
        # Only materialize when engineer named it or explicitly muted
        if not eng and gen:
            continue
        parsed = _parse_channel_addr(addr)
        if not parsed:
            continue
        rio, direction, data_index, bit = parsed
        target_mod = None
        target_ad = None
        for ad in model.get("adapters") or []:
            if (ad.get("rio_name") or "").strip() != rio:
                continue
            for mod in ad.get("modules") or []:
                if mod.get("is_adapter_card"):
                    continue
                mod_dir = (mod.get("direction") or "").strip().upper()
                try:
                    di = int(mod.get("data_index")) if mod.get("data_index") is not None else None
                except (TypeError, ValueError):
                    di = None
                if mod_dir == direction and di == data_index:
                    target_mod = mod
                    target_ad = ad
                    break
            if target_mod:
                break
        if not target_mod:
            continue
        stub = {
            "fortna_word": None,
            "fortna_bit": bit,
            "word_bit_key": None,
            "physical_address": addr,
            "direction": direction,
            "logical_endpoint": None,
            "engineer_synthesized": True,
        }
        _apply_one_channel(stub, o)
        target_mod.setdefault("channels", []).append(stub)
        # Keep channels sorted by bit
        try:
            target_mod["channels"].sort(key=lambda c: int(c.get("fortna_bit") or 0))
        except Exception:
            pass
        by_addr[addr] = stub

    # Stamp fields on all channels even without override (defaults).
    # Channels NOT in the override file must have engineerName cleared — otherwise
    # a prior in-memory patch / stale session value survives into Autogen.
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for ch in mod.get("channels") or []:
                addr = (ch.get("physical_address") or "").strip()
                if addr and addr in channels_ov:
                    continue  # already applied from file
                le = ch.get("logical_endpoint") or {}
                if "sourceName" not in ch or not ch.get("sourceName"):
                    if isinstance(le, dict):
                        src = str(
                            le.get("source_name")
                            or ("" if le.get("engineer_override") else le.get("name"))
                            or ""
                        ).strip()
                    else:
                        src = ""
                    ch["sourceName"] = src
                # Force-clear stale engineer override when not in persistence
                ch["engineerName"] = None
                ch["effectiveName"] = ch.get("sourceName") or None
                if "generate" not in ch:
                    ch["generate"] = True
                    ch["muted"] = False
                if isinstance(le, dict) and le.get("engineer_override"):
                    ch["logical_endpoint"] = {
                        **le,
                        "name": ch.get("sourceName") or le.get("source_name") or "",
                        "engineer_override": False,
                    }

    model["overrides"] = {
        "path": str(DEFAULT_OVERRIDES_PATH),
        "count": len(channels_ov),
        "projectIdentity": ov.get("projectIdentity") or {},
    }
    return model


def overrides_for_iomap(overrides: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Map physical_address → {effectiveName, generate, sourceName, engineerName}.

    Cleared / sentinel engineer names are omitted (engineerName=None) so Autogen
    cannot emit stale logical bases.
    """
    ov = overrides if overrides is not None else load_overrides()
    # Opportunistically prune defaults so disk stays clean after reverts
    try:
        prune_inactive_overrides(ov)
    except Exception:
        pass
    out: dict[str, dict[str, Any]] = {}
    for addr, ch in (ov.get("channels") or {}).items():
        src = str(ch.get("sourceName") or "").strip()
        eng = str(ch.get("engineerName") or "").strip() or None
        if eng and (is_clear_sentinel(eng) or should_clear_engineer(eng, src)):
            eng = None
        gen = True if ch.get("generate") is None else bool(ch.get("generate"))
        # Skip fully-default entries (no eng name, generate on)
        if eng is None and gen:
            continue
        out[str(addr)] = {
            "sourceName": src,
            "engineerName": eng,
            "effectiveName": effective_name(src, eng),
            "generate": gen,
        }
    return out
