#!/usr/bin/env python3
"""ORI-051 / ORI-052 — endpoint ownership + hardware-backed readiness."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def normalize_endpoint_key(endpoint: str) -> str:
    """Canonical key for physical endpoint collision detection."""
    s = str(endpoint or "").strip().upper()
    if not s:
        return ""
    # Collapse whitespace; keep module:I/O.Data[n].b form intact
    return " ".join(s.split())


def build_endpoint_ownership_map(
    devices: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map normalized physical endpoint → claimant devices."""
    by_ep: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        ep = normalize_endpoint_key(
            d.get("physicalEndpoint") or d.get("physical_address") or ""
        )
        if not ep:
            # Inherit from related signals
            for sig in d.get("signals") or d.get("relatedSignals") or []:
                if not isinstance(sig, dict):
                    continue
                ep = normalize_endpoint_key(
                    sig.get("physicalEndpoint") or sig.get("physical_address") or ""
                )
                if ep:
                    break
        if not ep:
            continue
        by_ep[ep].append(d)
    return dict(by_ep)


def apply_endpoint_collision_review(
    devices: list[dict[str, Any]],
) -> dict[str, Any]:
    """ORI-051: multiple claimants of same endpoint → all REVIEW_REQUIRED."""
    ownership = build_endpoint_ownership_map(devices)
    collisions = []
    conflicted_names: set[str] = set()
    for ep, claimants in ownership.items():
        names = sorted(
            {
                str(c.get("name") or c.get("canonicalTag") or "").strip()
                for c in claimants
                if str(c.get("name") or "").strip()
            }
        )
        if len(names) < 2:
            continue
        collisions.append({"endpoint": ep, "claimants": names})
        conflicted_names.update(n.upper() for n in names)
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        nm = str(d.get("name") or "").strip().upper()
        if nm in conflicted_names:
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["endpointConflict"] = True
            d["assignable"] = False
            d["review_reason"] = "ENDPOINT_OWNERSHIP_CONFLICT"
    return {
        "collisions": collisions,
        "conflicted_count": len(conflicted_names),
        "devices": devices,
    }


def endpoint_is_hardware_backed(
    endpoint: str,
    *,
    valid_endpoints: set[str] | None = None,
    configio_words: set[str] | None = None,
) -> bool:
    """ORI-052: physical endpoint must exist in active-machine hardware model."""
    ep = normalize_endpoint_key(endpoint)
    if not ep:
        return False
    if valid_endpoints is not None:
        if ep in {normalize_endpoint_key(x) for x in valid_endpoints}:
            return True
        # Also accept word.bit shorthand present in configio word set
    if configio_words is not None:
        # endpoint forms: "603.1" or module path containing Data[n]
        if ep in {str(w).strip().upper() for w in configio_words}:
            return True
        # word.bit
        if "." in ep and ep.split(".", 1)[0] in {
            str(w).strip().upper() for w in configio_words
        }:
            return True
    # No hardware model supplied → cannot prove READY
    if valid_endpoints is None and configio_words is None:
        return False
    return False


def _device_has_configio_evidence(d: dict[str, Any]) -> bool:
    if d.get("configio_backed") or d.get("configIoBacked"):
        return True
    for sig in d.get("signals") or d.get("relatedSignals") or []:
        if not isinstance(sig, dict):
            continue
        if sig.get("configio_backed") or sig.get("configIoBacked"):
            return True
        for ev in sig.get("evidence") or []:
            if isinstance(ev, dict) and (
                ev.get("configio_backed") or ev.get("provenance") == "CONFIGIO"
            ):
                return True
    for ev in d.get("evidence") or []:
        if isinstance(ev, dict) and (
            ev.get("configio_backed") or ev.get("provenance") == "CONFIGIO"
        ):
            return True
    return False


def apply_hardware_backed_readiness(
    devices: list[dict[str, Any]],
    *,
    valid_endpoints: set[str] | None = None,
    configio_words: set[str] | None = None,
) -> dict[str, Any]:
    """Mark devices without hardware-backed endpoints as REVIEW (not READY)."""
    not_ready = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if d.get("endpointConflict"):
            continue
        ep = str(d.get("physicalEndpoint") or d.get("physical_address") or "").strip()
        if not ep:
            for sig in d.get("signals") or []:
                if isinstance(sig, dict) and (
                    sig.get("physicalEndpoint") or sig.get("physical_address")
                ):
                    ep = str(
                        sig.get("physicalEndpoint") or sig.get("physical_address")
                    ).strip()
                    break
        backed = endpoint_is_hardware_backed(
            ep,
            valid_endpoints=valid_endpoints,
            configio_words=configio_words,
        )
        # Configio-backed evidence on the device/signals also proves hardware
        if not backed and _device_has_configio_evidence(d):
            backed = True
        # Word.bit shorthand on device.io_word
        if not backed and configio_words:
            iw = str(d.get("io_word") or "").strip()
            if iw and iw in configio_words:
                backed = True
        d["hardwareBacked"] = backed
        if not ep and not backed:
            # Name-only / no endpoint — never READY (ORI-030/052)
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            d["review_reason"] = d.get("review_reason") or "NO_PHYSICAL_ENDPOINT"
            not_ready.append(d.get("name"))
        elif not backed:
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            d["review_reason"] = d.get("review_reason") or "NO_ACTIVE_MACHINE_HARDWARE"
            not_ready.append(d.get("name"))
        else:
            d.setdefault("readiness", d.get("status") or "READY")
            if d.get("assignable") is not False and not d.get("endpointConflict"):
                d["assignable"] = True
    return {
        "not_hardware_backed": not_ready,
        "not_hardware_backed_count": len(not_ready),
        "devices": devices,
    }
