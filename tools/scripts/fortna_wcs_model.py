#!/usr/bin/env python3
"""WCSModel discovery from RUN — evidence authority for WCS_Interface_TCP_IP.

Sorter presence alone does NOT enable WCS. MsgWCS / WCSEvents / Machine peers are
evidence fields (PROVEN table rows) but TCP endpoint + pack emit require engineer
assignment or an explicit proven enable rule.

Authority classes: PROVEN | DERIVED | ENGINEER_ASSIGNED | REVIEW_REQUIRED
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fortna_asc import read_asc

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
CONTRACT_PATH = ROOT / "config" / "program_packs" / "wcs_interface_contract.json"

PROVEN = "PROVEN"
DERIVED = "DERIVED"
ENGINEER_ASSIGNED = "ENGINEER_ASSIGNED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _truthy_yn(v: Any) -> bool:
    return _clean(v).upper() in {"Y", "YES", "TRUE", "1"}


def _field(value: Any, authority: str, *, reason: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"value": value, "authority": authority}
    if reason:
        out["reason"] = reason
    return out


def _fortna_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    for cand in (run_dir / "FORTNA", run_dir / "Fortna", run_dir):
        if cand.is_dir():
            return cand
    return run_dir / "FORTNA"


def _resolve_machine_asc(fortna: Path, machine: str = "") -> Path | None:
    if machine:
        site = fortna / f"Machine.asc.{machine}"
        if site.is_file():
            return site
    primary = fortna / "Machine.asc"
    if primary.is_file() and primary.stat().st_size > 0:
        return primary
    # Prefer largest Machine.asc.* site overlay
    overlays = sorted(fortna.glob("Machine.asc.*"), key=lambda p: p.stat().st_size, reverse=True)
    return overlays[0] if overlays else None


def _resolve_msgmap_asc(fortna: Path, machine: str = "") -> Path | None:
    if machine:
        site = fortna / f"MsgMap.asc.{machine}"
        if site.is_file():
            return site
    primary = fortna / "MsgMap.asc"
    if primary.is_file():
        return primary
    overlays = sorted(fortna.glob("MsgMap.asc.*"), key=lambda p: p.stat().st_size, reverse=True)
    return overlays[0] if overlays else None


def load_wcs_contract() -> dict[str, Any]:
    if CONTRACT_PATH.is_file():
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return {"pack": "WCS_Interface_TCP_IP", "status": "MORE_EVIDENCE_REQUIRED"}


def discover_wcs_evidence(run_dir: Path | str, machine: str = "") -> dict[str, Any]:
    """Inventory RUN WCS-related tables. Never invents Greensboro tag names."""
    run_dir = Path(run_dir)
    fortna = _fortna_dir(run_dir)
    machine = _clean(machine)

    tables: dict[str, Any] = {}

    def invent(name: str, path: Path | None, *, name_col: str | None = None) -> dict[str, Any]:
        info: dict[str, Any] = {
            "table": name,
            "exists": bool(path and path.is_file()),
            "path": str(path.relative_to(run_dir)).replace("\\", "/") if path and path.is_file() else None,
            "byte_size": path.stat().st_size if path and path.is_file() else 0,
            "row_count": 0,
            "active_rows": 0,
            "headers": [],
            "samples": [],
            "authority": PROVEN if path and path.is_file() else REVIEW_REQUIRED,
        }
        if not info["exists"]:
            return info
        headers, rows = read_asc(path)  # type: ignore[arg-type]
        info["headers"] = list(headers or [])
        info["row_count"] = len(rows)
        active: list[dict[str, str]] = []
        for r in rows:
            if name == "MsgWCS":
                dest = _clean(r.get("Destination"))
                if dest and dest.upper() not in {"N/A", "INVALID", "NONE"}:
                    active.append(r)
            elif name == "WCSEvents":
                if _truthy_yn(r.get("WCSEnable")) and _clean(r.get("EventName")).upper() not in {
                    "", "N/A", "INVALID"
                }:
                    active.append(r)
            elif name_col:
                if _clean(r.get(name_col)).upper() not in {"", "N/A", "INVALID", "NONE"}:
                    active.append(r)
            else:
                active.append(r)
        info["active_rows"] = len(active)
        info["samples"] = [
            {k: _clean(r.get(k)) for k in (info["headers"][:6] or r.keys())}
            for r in active[:8]
        ]
        return info

    msgwcs = fortna / "MsgWCS.asc"
    tables["MsgWCS"] = invent("MsgWCS", msgwcs if msgwcs.is_file() else None)

    wcse = fortna / "WCSEvents.asc"
    tables["WCSEvents"] = invent("WCSEvents", wcse if wcse.is_file() else None)

    msgmap_path = _resolve_msgmap_asc(fortna, machine)
    tables["MsgMap"] = invent("MsgMap", msgmap_path, name_col="Message_Name")

    mach_path = _resolve_machine_asc(fortna, machine)
    tables["Machine"] = invent("Machine", mach_path, name_col="Machine_Name")

    # Enabled WCS events (PROVEN from WCSEvents)
    enabled_events: list[dict[str, str]] = []
    if tables["WCSEvents"]["exists"]:
        _h, rows = read_asc(fortna / "WCSEvents.asc")
        for r in rows:
            if not _truthy_yn(r.get("WCSEnable")):
                continue
            ev = _clean(r.get("EventName"))
            if ev.upper() in {"", "N/A", "INVALID"}:
                continue
            enabled_events.append(
                {
                    "event": ev,
                    "destination": _clean(r.get("WCSDestination")),
                    "category": _clean(r.get("WCSCategory")),
                    "service": _clean(r.get("WCSService")),
                }
            )

    # MsgMap WCS_EVENT → MsgWCS peer
    msgmap_wcs: list[dict[str, str]] = []
    if msgmap_path and msgmap_path.is_file():
        _h, rows = read_asc(msgmap_path)
        for r in rows:
            menu = _clean(r.get("Menu_Name")).upper()
            msg = _clean(r.get("Message_Name")).upper()
            if "WCS" in menu or "WCS" in msg:
                msgmap_wcs.append(
                    {
                        "message_name": _clean(r.get("Message_Name")),
                        "machine_name": _clean(r.get("Machine_Name")),
                        "menu_name": _clean(r.get("Menu_Name")),
                    }
                )

    # Machine peers that look like WCS / host messaging (not sorter TCP)
    wcs_peers: list[dict[str, str]] = []
    tcp_candidates: list[dict[str, str]] = []
    if mach_path and mach_path.is_file():
        _h, rows = read_asc(mach_path)
        for r in rows:
            name = _clean(r.get("Machine_Name"))
            if not name or name.upper() in {"N/A", "INVALID", "NONE"}:
                continue
            proto = _clean(r.get("Communication_Protocol"))
            ctype = _clean(r.get("Connection_Type"))
            port = _clean(r.get("Machine_Port"))
            row = {
                "machine_name": name,
                "connection_type": ctype,
                "protocol": proto,
                "port": port,
            }
            u = f"{name} {proto} {ctype}".upper()
            if "WCS" in u or name.upper().startswith("WCS_"):
                wcs_peers.append(row)
            # Numeric TCP port candidates — engineer still required for PLC Helix endpoint
            if ctype.upper() in {"CONNECT_TCPCLIENT", "TCPSERV_LISTEN", "TCPSERV_RDWR"} and port.isdigit():
                tcp_candidates.append(row)

    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "tables": tables,
        "counts": {
            "msgwcs_active": int(tables["MsgWCS"].get("active_rows") or 0),
            "wcs_events_enabled": len(enabled_events),
            "wcs_events_total": int(tables["WCSEvents"].get("row_count") or 0),
            "msgmap_wcs_rows": len(msgmap_wcs),
            "wcs_machine_peers": len(wcs_peers),
            "tcp_port_candidates": len(tcp_candidates),
        },
        "enabled_events": enabled_events[:40],
        "msgmap_wcs": msgmap_wcs,
        "wcs_peers": wcs_peers,
        "tcp_candidates": tcp_candidates[:20],
        "notes": [
            "RUN MsgWCS/WCSEvents prove host-side WCS messaging activity.",
            "PLC WCS_Interface_TCP_IP Helix TCP endpoint is engineer/commissioning.",
            "Sorter discovery alone must not enable WCS pack emit.",
        ],
    }


def wcs_build_is_engineer_enabled(wcs_build: dict[str, Any] | None) -> bool:
    cfg = dict(wcs_build or {})
    if not cfg:
        return False
    if cfg.get("enabled") is True or cfg.get("include") is True:
        return True
    if _clean(cfg.get("authority") or cfg.get("enable_authority")).upper() in {
        ENGINEER_ASSIGNED,
        "ENGINEER",
        PROVEN,
    }:
        return True
    if cfg.get("appliedAt") or cfg.get("engineer_enabled"):
        return True
    # Explicit proven flag from validation / engineer checklist
    if cfg.get("proven") is True or cfg.get("proven_enable") is True:
        return True
    return False


def build_wcs_model(
    run_dir: Path | str | None = None,
    machine: str = "",
    *,
    wcs_build: dict[str, Any] | None = None,
    sorter_present: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build WCSModel with authority-tagged fields.

    enabled is True only when engineer-assigned or explicit proven enable —
    never from sorter presence or MsgWCS/WCSEvents inventory alone.
    """
    contract = load_wcs_contract()
    wcs_build = dict(wcs_build or {})
    evidence = evidence or (
        discover_wcs_evidence(run_dir, machine) if run_dir else {"counts": {}, "tables": {}}
    )
    counts = dict(evidence.get("counts") or {})

    has_run_signal = bool(
        counts.get("msgwcs_active")
        or counts.get("wcs_events_enabled")
        or counts.get("msgmap_wcs_rows")
        or counts.get("wcs_machine_peers")
    )

    engineer_on = wcs_build_is_engineer_enabled(wcs_build)
    proven_on = bool(wcs_build.get("proven") or wcs_build.get("proven_enable")) and not engineer_on
    # Explicit enable_authority=PROVEN on workbook also qualifies
    if _clean(wcs_build.get("enable_authority")).upper() == PROVEN:
        proven_on = True

    enabled = bool(engineer_on or proven_on)
    enable_authority = (
        ENGINEER_ASSIGNED if engineer_on else (PROVEN if proven_on else REVIEW_REQUIRED)
    )
    enable_reason = (
        "workbook.wcs_build engineer enable"
        if engineer_on
        else (
            "explicit proven enable flag"
            if proven_on
            else (
                "RUN WCS evidence present — pack emit requires engineer/proven enable"
                if has_run_signal
                else "no WCS enable evidence"
            )
        )
    )
    if sorter_present and not enabled:
        enable_reason += "; sorter_present=true does not enable WCS"

    # Endpoint / framing — engineer required (may be blank)
    endpoint = wcs_build.get("tcp_endpoint") or wcs_build.get("endpoint") or {}
    if not isinstance(endpoint, dict):
        endpoint = {"host": _clean(endpoint), "port": wcs_build.get("tcp_port")}
    framing = wcs_build.get("framing") or {}
    if not isinstance(framing, dict):
        framing = {"stx": wcs_build.get("stx"), "etx": wcs_build.get("etx")}

    endpoint_authority = (
        ENGINEER_ASSIGNED
        if (endpoint.get("host") or endpoint.get("port") or endpoint.get("value"))
        else REVIEW_REQUIRED
    )

    model: dict[str, Any] = {
        "kind": "WCSModel",
        "version": 1,
        "machine": _clean(machine) or _clean(evidence.get("machine")),
        "pack": contract.get("pack") or "WCS_Interface_TCP_IP",
        "contract_status": contract.get("status") or "MORE_EVIDENCE_REQUIRED",
        "enabled": enabled,
        "enable": _field(enabled, enable_authority, reason=enable_reason),
        "sorter_present": bool(sorter_present),
        "sorter_does_not_enable_wcs": True,
        "evidence": {
            "msgwcs_active": _field(counts.get("msgwcs_active", 0), PROVEN),
            "wcs_events_enabled": _field(counts.get("wcs_events_enabled", 0), PROVEN),
            "wcs_events_total": _field(counts.get("wcs_events_total", 0), PROVEN),
            "msgmap_wcs_rows": _field(counts.get("msgmap_wcs_rows", 0), PROVEN),
            "wcs_machine_peers": _field(
                evidence.get("wcs_peers") or [],
                PROVEN if counts.get("wcs_machine_peers") else REVIEW_REQUIRED,
            ),
            "tcp_candidates": _field(
                evidence.get("tcp_candidates") or [],
                REVIEW_REQUIRED,
                reason="Numeric TCP peers are not Helix PLC endpoint authority",
            ),
            "enabled_events_sample": _field(
                (evidence.get("enabled_events") or [])[:12],
                PROVEN if counts.get("wcs_events_enabled") else REVIEW_REQUIRED,
            ),
            "tables": evidence.get("tables") or {},
            "has_run_signal": has_run_signal,
        },
        "endpoint": _field(
            {
                "host": endpoint.get("host") or endpoint.get("ip") or "",
                "port": endpoint.get("port") or "",
            },
            endpoint_authority,
            reason="TCP endpoint is SITE_CONFIGURATION / engineer-required",
        ),
        "framing": _field(
            {
                "stx": framing.get("stx") or wcs_build.get("stx") or "",
                "etx": framing.get("etx") or wcs_build.get("etx") or "",
            },
            ENGINEER_ASSIGNED if (framing.get("stx") or framing.get("etx")) else REVIEW_REQUIRED,
        ),
        "decision_points": _field(
            list(wcs_build.get("decision_points") or []),
            ENGINEER_ASSIGNED if wcs_build.get("decision_points") else REVIEW_REQUIRED,
        ),
        "heartbeat": _field(
            dict(wcs_build.get("heartbeat") or {}),
            ENGINEER_ASSIGNED if wcs_build.get("heartbeat") else REVIEW_REQUIRED,
        ),
        "lane_strings": _field(
            list(wcs_build.get("lane_strings") or []),
            ENGINEER_ASSIGNED if wcs_build.get("lane_strings") else REVIEW_REQUIRED,
            reason="Do not invent Greensboro DP1_L*_DivertedLane_str names",
        ),
        "task": {
            "name": "P03_WCS_10ms",
            "type": "PERIODIC",
            "rate_ms": int((wcs_build.get("task_rate_ms") or 10)),
            "priority": int((wcs_build.get("task_priority") or 3)),
            "authority": DERIVED,
            "note": "Oracle example rate — not a universal constant",
        },
        "anti_cheat": {
            "no_auto_include_from_sorter": True,
            "no_greensboro_tag_invention": True,
            "hollow_emit_forbidden_unless_enabled": True,
        },
        "wcs_build": {k: v for k, v in wcs_build.items() if k != "password"},
    }
    return model


def discover(
    run_dir: Path | str,
    machine: str = "",
    *,
    wcs_build: dict[str, Any] | None = None,
    sorter_present: bool = False,
) -> dict[str, Any]:
    """Convenience: evidence + WCSModel for a RUN."""
    evidence = discover_wcs_evidence(run_dir, machine)
    model = build_wcs_model(
        run_dir,
        machine,
        wcs_build=wcs_build,
        sorter_present=sorter_present,
        evidence=evidence,
    )
    return {"evidence": evidence, "model": model}


__all__ = [
    "build_wcs_model",
    "discover",
    "discover_wcs_evidence",
    "load_wcs_contract",
    "wcs_build_is_engineer_enabled",
    "PROVEN",
    "DERIVED",
    "ENGINEER_ASSIGNED",
    "REVIEW_REQUIRED",
]
