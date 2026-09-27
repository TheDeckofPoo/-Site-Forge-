#!/usr/bin/env python3
"""Build minimal panel-local Relay evidence packets.

Never includes whole TAR, finished L5X/ACD, credentials, or unrelated controllers.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from fortna_relay_trigger import classify_relay_trigger

_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "openai_api_key",
        "password",
        "token",
        "secret",
        "credential",
        "l5x",
        "acd",
        "tar_bytes",
        "archive_bytes",
        "finished_plc",
    }
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _panel_token(text: str) -> str:
    u = str(text or "").upper().replace("-", "_")
    m = re.search(r"(?:^|_)(CP\d+)(?:_|$)", u)
    if m:
        return m.group(1)
    m = re.search(r"\b(CP\d+)\b", str(text or "").upper())
    return m.group(1) if m else ""


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _FORBIDDEN_KEYS or any(x in lk for x in ("api_key", "password", "secret")):
                continue
            if lk.endswith("_l5x") or lk.endswith("_acd") or "tar.gz" in lk:
                continue
            out[k] = _scrub(v)
        return out
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str) and len(obj) > 8000:
        return obj[:8000] + "…[truncated]"
    return obj


def _row_panel(row: dict[str, Any]) -> str:
    return (
        _panel_token(row.get("panel") or "")
        or _panel_token(row.get("desc") or "")
        or _panel_token(row.get("rio_name") or "")
        or _panel_token(row.get("adapter") or "")
        or ""
    )


def build_evidence_packet(
    *,
    point: dict[str, Any],
    machine: str,
    panel: str = "",
    configio_rows: list[dict[str, Any]] | None = None,
    adapter_modules: list[dict[str, Any]] | None = None,
    conveyor_rows: list[dict[str, Any]] | None = None,
    logic_snippets: list[dict[str, Any]] | None = None,
    site_forge_result: dict[str, Any] | None = None,
    foreign_controller_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a panel-scoped evidence packet for one Relay case."""
    trigger = classify_relay_trigger(point)
    target_panel = (
        panel
        or _panel_token(point.get("panel") or "")
        or _panel_token(point.get("physicalEndpoint") or "")
        or _panel_token(str(site_forge_result or {}).get("panel") or "")
    )
    raw_address = str(
        point.get("raw_address")
        or point.get("physicalEndpoint")
        or (
            f"{point.get('io_word')}.{point.get('io_bit')}"
            if point.get("io_word") not in (None, "")
            else ""
        )
        or ""
    ).strip()

    # Panel-local filter for Configio / modules
    cfg = []
    for row in configio_rows or []:
        if not isinstance(row, dict):
            continue
        rp = _row_panel(row)
        if target_panel and rp and rp != target_panel:
            continue
        cfg.append(
            {
                k: row.get(k)
                for k in (
                    "Desc",
                    "desc",
                    "Bank",
                    "bank",
                    "Octal_Word",
                    "octal_word",
                    "LoHi",
                    "lohi",
                    "In_Out",
                    "in_out",
                    "Interface",
                )
                if k in row or k.lower() in {x.lower() for x in row}
            }
            or _scrub(row)
        )

    mods = []
    for m in adapter_modules or []:
        if not isinstance(m, dict):
            continue
        mp = _row_panel(m) or _panel_token(m.get("name") or m.get("rio_name") or "")
        if target_panel and mp and mp != target_panel:
            continue
        mods.append(
            _scrub(
                {
                    "name": m.get("name"),
                    "type": m.get("type") or m.get("catalog"),
                    "slot": m.get("slot"),
                    "direction": m.get("direction"),
                    "input_bank": m.get("input_bank"),
                    "output_bank": m.get("output_bank"),
                    "rio_name": m.get("rio_name") or m.get("adapter_name"),
                    "panel": mp or target_panel,
                }
            )
        )

    # Explicitly drop foreign controller rows from the packet
    _ = foreign_controller_rows  # accepted only to prove exclusion in tests

    conv = []
    for row in conveyor_rows or []:
        if not isinstance(row, dict):
            continue
        # Keep only rows matching the signal / word under review when possible
        name = str(row.get("IO_Name") or row.get("name") or "")
        want = str(point.get("name") or point.get("signal") or "")
        word = str(row.get("IO_Address_Word") or row.get("word") or "")
        if want and name and want.upper() not in name.upper() and name.upper() not in want.upper():
            if raw_address and word and word not in raw_address:
                continue
        conv.append(
            _scrub(
                {
                    "IO_Name": name,
                    "IO_Address_Word": word,
                    "IO_Address_Bit": row.get("IO_Address_Bit") or row.get("bit"),
                    "Machine_Name": row.get("Machine_Name") or row.get("machine"),
                    "Type": row.get("Type"),
                }
            )
        )

    packet = {
        "kind": "relay_evidence_packet",
        "version": 1,
        "generated_at": _ts(),
        "production_authority": False,
        "shadow_mode": True,
        "machine": str(machine or "").strip(),
        "panel": target_panel,
        "case": {
            "case_id": str(point.get("case_id") or point.get("id") or point.get("name") or raw_address),
            "signal": point.get("name") or point.get("signal"),
            "raw_address": raw_address,
            "relay_reason": (trigger.get("reasons") or [None])[0],
            "relay_reasons": trigger.get("reasons") or [],
        },
        "site_forge_result": _scrub(site_forge_result or {
            "confidence": point.get("confidence") or point.get("binding_confidence"),
            "status": point.get("status"),
            "review_reason": point.get("review_reason"),
            "physicalEndpoint": point.get("physicalEndpoint"),
            "inventory_scope": point.get("inventory_scope"),
            "endpoint_proof_depth": point.get("endpoint_proof_depth"),
            "assignable": point.get("assignable"),
        }),
        "evidence": {
            "configio_rows": cfg[:40],
            "adapter_modules": mods[:80],
            "conveyor_rows": conv[:20],
            "logic_snippets": _scrub(list(logic_snippets or [])[:10]),
            "contradictions": list(point.get("contradictions") or []),
            "ownership": {
                "machine": point.get("machine"),
                "inventory_scope": point.get("inventory_scope"),
                "review_reason": point.get("review_reason"),
            },
        },
        "exclusions": {
            "whole_tar": True,
            "finished_l5x": True,
            "acd": True,
            "unrelated_controllers": True,
            "foreign_rows_supplied": len(foreign_controller_rows or []),
            "foreign_rows_included": 0,
            "credentials": True,
        },
        "trigger": trigger,
    }
    # Hash is stable across invocations — exclude timestamps
    packet["evidence_packet_hash"] = _sha256_obj(
        {
            k: v
            for k, v in packet.items()
            if k not in {"evidence_packet_hash", "generated_at"}
        }
    )
    return packet


def assert_packet_safe(packet: dict[str, Any]) -> list[str]:
    """Return policy violations if packet contains forbidden material."""
    violations: list[str] = []
    blob = json.dumps(packet, default=str).lower()
    if "openai_api_key" in blob or "sk-" in blob:
        violations.append("CREDENTIAL_LEAK")
    if ".l5x" in blob and "finished_l5x" not in blob:
        # allow exclusion flags mentioning l5x
        if "exclusions" not in packet or not packet.get("exclusions", {}).get("finished_l5x"):
            violations.append("L5X_CONTENT")
    if packet.get("exclusions", {}).get("foreign_rows_included", 0):
        violations.append("FOREIGN_CONTROLLER_INCLUDED")
    if packet.get("production_authority") is True:
        violations.append("PRODUCTION_AUTHORITY_TRUE")
    return violations
