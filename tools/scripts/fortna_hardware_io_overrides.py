#!/usr/bin/env python3
"""Engineer overrides for Hardware/I/O channels.

Preserves RUN-discovered source names. Engineer name becomes authoritative
for IO_MAP generation when set. generate=False mutes the channel from IO_MAP
without deleting evidence.
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


def validate_logical_name(name: str) -> tuple[bool, str]:
    """Validate Rockwell-style identifier or member path. Empty = clear override."""
    s = (name or "").strip()
    if not s:
        return True, ""
    if s.upper() in ("SPARE", "—", "-", "N/A", "NONE"):
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
    if eng:
        return eng
    return (source_name or "").strip()


def channel_override(overrides: dict[str, Any], physical_address: str) -> dict[str, Any]:
    ch = (overrides.get("channels") or {}).get(physical_address) or {}
    return {
        "sourceName": str(ch.get("sourceName") or "").strip(),
        "engineerName": str(ch.get("engineerName") or "").strip() or None,
        "generate": True if ch.get("generate") is None else bool(ch.get("generate")),
        "muted": False if ch.get("generate") is None else (not bool(ch.get("generate"))),
        "updatedAt": ch.get("updatedAt"),
    }


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
    if clear_engineer:
        cur["engineerName"] = ""
    elif engineer_name is not None:
        ok, err = validate_logical_name(engineer_name)
        if not ok:
            raise ValueError(err)
        cur["engineerName"] = (engineer_name or "").strip()
    if generate is not None:
        cur["generate"] = bool(generate)
    elif "generate" not in cur:
        cur["generate"] = True
    from datetime import datetime, timezone

    cur["updatedAt"] = datetime.now(timezone.utc).isoformat()
    channels[addr] = cur
    return cur


def apply_overrides_to_hardware_model(
    model: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate HardwareIOModel channels with engineer override fields (in place)."""
    ov = overrides if overrides is not None else load_overrides()
    channels_ov = ov.get("channels") or {}
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for ch in mod.get("channels") or []:
                addr = (ch.get("physical_address") or "").strip()
                if not addr:
                    continue
                src = ""
                le = ch.get("logical_endpoint") or {}
                if isinstance(le, dict):
                    src = str(le.get("name") or "").strip()
                o = channels_ov.get(addr) or {}
                source_name = str(o.get("sourceName") or src or "").strip()
                engineer_name = str(o.get("engineerName") or "").strip() or None
                generate = True if o.get("generate") is None else bool(o.get("generate"))
                eff = effective_name(source_name, engineer_name)
                ch["sourceName"] = source_name
                ch["engineerName"] = engineer_name
                ch["effectiveName"] = eff or None
                ch["generate"] = generate
                ch["muted"] = not generate
                # Keep logical_endpoint for RUN evidence; expose effective for UI
                if engineer_name:
                    ch["logical_endpoint"] = {
                        **(le if isinstance(le, dict) else {}),
                        "name": engineer_name,
                        "source_name": source_name or None,
                        "engineer_override": True,
                    }
                elif le and isinstance(le, dict):
                    ch["logical_endpoint"] = le
    model["overrides"] = {
        "path": str(DEFAULT_OVERRIDES_PATH),
        "count": len(channels_ov),
        "projectIdentity": ov.get("projectIdentity") or {},
    }
    return model


def overrides_for_iomap(overrides: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Map physical_address → {effectiveName, generate, sourceName, engineerName}."""
    ov = overrides if overrides is not None else load_overrides()
    out: dict[str, dict[str, Any]] = {}
    for addr, ch in (ov.get("channels") or {}).items():
        src = str(ch.get("sourceName") or "").strip()
        eng = str(ch.get("engineerName") or "").strip() or None
        gen = True if ch.get("generate") is None else bool(ch.get("generate"))
        out[str(addr)] = {
            "sourceName": src,
            "engineerName": eng,
            "effectiveName": effective_name(src, eng),
            "generate": gen,
        }
    return out
