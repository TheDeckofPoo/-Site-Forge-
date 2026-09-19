#!/usr/bin/env python3
"""WCS_Interface_TCP_IP pack compiler skeleton.

When WCSModel.enabled (engineer or proven), remap the library pack with site
config and schedule on P03_WCS_10ms. Never auto-include from sorter alone.
Never invent Greensboro divert / lane tag names.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fortna_wcs_model import (
    ENGINEER_ASSIGNED,
    PROVEN,
    REVIEW_REQUIRED,
    build_wcs_model,
    load_wcs_contract,
    wcs_build_is_engineer_enabled,
)

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
PROGRAM_LIBRARY_DIR = ROOT / "tools" / "libraries" / "programs"
WCS_PACK_FILE = "WCS_Interface_TCP_IP_Program.L5X"
WCS_PROGRAM = "WCS_Interface_TCP_IP"
WCS_TASK = "P03_WCS_10ms"

# Greensboro pack-template divert hosts embedded in gold WCS L5X.
# Remap to site divert_host when provided — never leave as orphan site tags.
PACK_TEMPLATE_WCS_HOSTS = ("P504", "P506", "P508", "P509", "P510")


def _clean(v: Any) -> str:
    return str(v or "").strip()


def should_emit_wcs(
    wcs_build: dict[str, Any] | None = None,
    wcs_model: dict[str, Any] | None = None,
    *,
    sorter_present: bool = False,
) -> bool:
    """Gate: emit only when model/build explicitly enables (not sorter alone)."""
    void = sorter_present  # documented no-op — sorter never gates True alone
    _ = void
    model = dict(wcs_model or {})
    if model.get("enabled") is True:
        return True
    enable = model.get("enable")
    if isinstance(enable, dict) and enable.get("value") is True:
        auth = _clean(enable.get("authority")).upper()
        if auth in {ENGINEER_ASSIGNED, PROVEN, "ENGINEER"}:
            return True
    return wcs_build_is_engineer_enabled(wcs_build)


def _load_wcs_pack_xml() -> dict[str, Any] | None:
    path = PROGRAM_LIBRARY_DIR / WCS_PACK_FILE
    if not path.is_file():
        return None
    from fortna_autogen import load_program_export  # local import — avoid cycle at import

    return load_program_export(path)


def remap_wcs_pack_xml(
    xml: str,
    *,
    site_stem: str = "",
    divert_host: str = "",
    endpoint: dict[str, Any] | None = None,
) -> str:
    """Remap library pack with site config. Prefer remap over copying Greensboro tags."""
    if not xml:
        return xml
    out = xml
    # Strip controller context name (Greensboro) — program target is site-agnostic
    out = re.sub(
        r'(<Controller\b[^>]*\bName=")ORLY_Greensboro_NC_PLC5(")',
        rf'\1{_clean(site_stem) or "SiteForge"}\2',
        out,
        count=1,
    )
    host = _clean(divert_host)
    if host and re.match(r"^P\d+", host, re.I):
        for slot in PACK_TEMPLATE_WCS_HOSTS:
            if slot.upper() == host.upper():
                continue
            # Family remap: P506_Divert1 → {host}_Divert1, etc.
            out = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(slot)}_",
                f"{host}_",
                out,
            )
    # Endpoint placeholders — only when engineer supplied (no invented IPs)
    endpoint = endpoint or {}
    host_ip = _clean(endpoint.get("host") or endpoint.get("ip"))
    port = _clean(endpoint.get("port"))
    if host_ip:
        # Soft annotate: do not invent socket Address bytes; leave gold structure
        out = out.replace("<!--SITE_WCS_ENDPOINT_HOST-->", host_ip)
    if port and port.isdigit():
        out = out.replace("<!--SITE_WCS_ENDPOINT_PORT-->", port)
    return out


def compile_wcs_pack(
    *,
    wcs_build: dict[str, Any] | None = None,
    wcs_model: dict[str, Any] | None = None,
    site_stem: str = "",
    divert_host: str = "",
    sorter_present: bool = False,
    run_dir: Path | str | None = None,
    machine: str = "",
) -> dict[str, Any]:
    """Compile / include WCS_Interface_TCP_IP when enabled.

    Returns {emitted, program_xml, tags, datatypes_xml, aois_xml, report, task}.
    """
    contract = load_wcs_contract()
    wcs_build = dict(wcs_build or {})
    model = dict(wcs_model or {})
    if not model and run_dir:
        model = build_wcs_model(
            run_dir,
            machine or _clean(wcs_build.get("machine")),
            wcs_build=wcs_build,
            sorter_present=sorter_present,
        )
    elif not model:
        model = build_wcs_model(
            None,
            machine or _clean(wcs_build.get("machine")),
            wcs_build=wcs_build,
            sorter_present=sorter_present,
        )

    report: dict[str, Any] = {
        "pack": WCS_PROGRAM,
        "contract_status": contract.get("status"),
        "enabled": bool(model.get("enabled")),
        "sorter_present": bool(sorter_present),
        "mode": "skipped",
        "severity": REVIEW_REQUIRED,
        "reasons": [],
    }

    if not should_emit_wcs(wcs_build, model, sorter_present=sorter_present):
        report["reasons"].append(
            model.get("enable", {}).get("reason")
            if isinstance(model.get("enable"), dict)
            else "WCSModel.enabled is false"
        )
        report["reasons"].append("sorter_present alone never enables WCS")
        return {
            "emitted": False,
            "program_xml": "",
            "tags": [],
            "datatypes_xml": "",
            "aois_xml": "",
            "report": report,
            "task": None,
            "wcs_model": model,
        }

    pack = _load_wcs_pack_xml()
    if not pack:
        report["mode"] = "error"
        report["severity"] = "FATAL_ERROR"
        report["reasons"].append(f"Missing library pack {WCS_PACK_FILE}")
        return {
            "emitted": False,
            "program_xml": "",
            "tags": [],
            "datatypes_xml": "",
            "aois_xml": "",
            "report": report,
            "task": None,
            "wcs_model": model,
        }

    endpoint_field = model.get("endpoint") if isinstance(model.get("endpoint"), dict) else {}
    endpoint_val = endpoint_field.get("value") if isinstance(endpoint_field, dict) else {}
    if not isinstance(endpoint_val, dict):
        endpoint_val = {}
    if not endpoint_val.get("host") and wcs_build.get("tcp_endpoint"):
        ep = wcs_build.get("tcp_endpoint")
        endpoint_val = ep if isinstance(ep, dict) else {"host": _clean(ep)}

    host = divert_host or _clean(wcs_build.get("divert_host_conveyor") or "")
    prog_xml = remap_wcs_pack_xml(
        pack.get("program_xml") or "",
        site_stem=site_stem,
        divert_host=host,
        endpoint=endpoint_val,
    )
    tags = [
        remap_wcs_pack_xml(t, site_stem=site_stem, divert_host=host, endpoint=endpoint_val)
        for t in (pack.get("tags") or [])
    ]
    dt_xml = remap_wcs_pack_xml(
        pack.get("datatypes_xml") or "",
        site_stem=site_stem,
        divert_host=host,
        endpoint=endpoint_val,
    )
    aoi_xml = remap_wcs_pack_xml(
        pack.get("aois_xml") or "",
        site_stem=site_stem,
        divert_host=host,
        endpoint=endpoint_val,
    )

    # Guard: do not leave bare Greensboro controller token in emit
    joined = prog_xml + "".join(tags)
    invented = []
    if "ORLY_Greensboro_NC_PLC5" in joined and site_stem and site_stem not in {
        "ORLY_Greensboro_NC_PLC5", "ORLY_Greensboro_NC_PLC4"
    }:
        invented.append("controller_context_not_retargeted")

    task = {
        "name": WCS_TASK,
        "type": "PERIODIC",
        "rate_ms": int((model.get("task") or {}).get("rate_ms") or 10),
        "priority": int((model.get("task") or {}).get("priority") or 3),
        "scheduled_programs": [WCS_PROGRAM],
    }
    report.update(
        {
            "mode": "library_pack_remap",
            "severity": ENGINEER_ASSIGNED if wcs_build_is_engineer_enabled(wcs_build) else PROVEN,
            "divert_host_remap": host or None,
            "endpoint_supplied": bool(endpoint_val.get("host") or endpoint_val.get("port")),
            "greensboro_residuals": invented,
            "routines_expected": [
                r.get("name") for r in (contract.get("routines") or []) if r.get("name")
            ],
        }
    )
    if not report["endpoint_supplied"]:
        report["reasons"].append("TCP endpoint still REVIEW_REQUIRED — pack included with gold socket CFG")
        report["severity"] = REVIEW_REQUIRED

    return {
        "emitted": True,
        "program_xml": prog_xml,
        "tags": tags,
        "datatypes_xml": dt_xml,
        "aois_xml": aoi_xml,
        "report": report,
        "task": task,
        "wcs_model": model,
    }


def wcs_model_qualifies_for_include(model: dict[str, Any] | None) -> bool:
    return should_emit_wcs(None, model)


__all__ = [
    "WCS_PROGRAM",
    "WCS_TASK",
    "compile_wcs_pack",
    "remap_wcs_pack_xml",
    "should_emit_wcs",
    "wcs_model_qualifies_for_include",
]
