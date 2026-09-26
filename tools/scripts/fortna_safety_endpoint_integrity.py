#!/usr/bin/env python3
"""ORI-051 / ORI-052 — endpoint ownership + hardware-backed readiness."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


# Full Rockwell channel: ADAPTER:I|O.Data[N].B (whitespace-tolerant after compact)
_ROCKWELL_FULL_RE = re.compile(
    r"^([A-Z0-9_]+):([IO])\.DATA\[(\d+)\]\.(\d+)$",
    re.IGNORECASE,
)
# Bare image suffix: Data[N].B
_ROCKWELL_DATA_RE = re.compile(
    r"^DATA\[(\d+)\]\.(\d+)$",
    re.IGNORECASE,
)
# Fortna word / word.bit shorthand
_WORD_BIT_RE = re.compile(r"^(\d+)(?:\.(\d+))?$")


def _compact_endpoint(endpoint: str) -> str:
    """Uppercase and strip all whitespace for structural comparison."""
    return "".join(str(endpoint or "").upper().split())


def _parse_rockwell(endpoint: str) -> dict[str, Any] | None:
    """Parse Rockwell ADAPTER:DIR.Data[N].B or bare Data[N].B forms."""
    compact = _compact_endpoint(endpoint)
    if not compact:
        return None
    m = _ROCKWELL_FULL_RE.match(compact)
    if m:
        return {
            "adapter": m.group(1).upper(),
            "direction": m.group(2).upper(),
            "data_index": int(m.group(3)),
            "bit": int(m.group(4)),
            "full": True,
        }
    m2 = _ROCKWELL_DATA_RE.match(compact)
    if m2:
        return {
            "adapter": None,
            "direction": None,
            "data_index": int(m2.group(1)),
            "bit": int(m2.group(2)),
            "full": False,
        }
    return None


def normalize_endpoint_key(endpoint: str) -> str:
    """Canonical physical endpoint key (ORI-051).

    Equivalent Rockwell spellings of the same point collapse to one key:
      T_1734:I.Data[17].2
      t_1734:i.data[17].2
      T_1734 : I . Data [ 17 ] . 2  →  T_1734:I.DATA[17].2
    Bare Data[N].B normalizes to DATA[N].B.
    """
    raw = str(endpoint or "").strip()
    if not raw:
        return ""
    parsed = _parse_rockwell(raw)
    if parsed and parsed.get("full"):
        return (
            f"{parsed['adapter']}:{parsed['direction']}"
            f".DATA[{parsed['data_index']}].{parsed['bit']}"
        )
    if parsed and not parsed.get("full"):
        return f"DATA[{parsed['data_index']}].{parsed['bit']}"
    # Non-Rockwell (word.bit / opaque): collapse whitespace, uppercase
    return _compact_endpoint(raw)


def _device_adapter_context(d: dict[str, Any]) -> str:
    """Proven adapter/RIO context for bare Data[N].B collision matching."""
    for k in ("adapter", "rio_name", "rioName", "module", "moduleName"):
        v = str(d.get(k) or "").strip()
        if v:
            return v.upper()
    pref = d.get("physicalIoRef") or d.get("physical_io_ref") or {}
    if isinstance(pref, dict):
        for k in ("adapter", "rio_name", "rioName", "module", "module_name"):
            v = str(pref.get(k) or "").strip()
            if v:
                return v.upper()
    return ""


def _device_direction_context(d: dict[str, Any]) -> str:
    for k in ("direction", "dir", "io_direction"):
        v = str(d.get(k) or "").strip().upper()
        if v in ("I", "O", "IN", "OUT", "INPUT", "OUTPUT"):
            return "I" if v in ("I", "IN", "INPUT") else "O"
    pref = d.get("physicalIoRef") or d.get("physical_io_ref") or {}
    if isinstance(pref, dict):
        v = str(pref.get("direction") or pref.get("dir") or "").strip().upper()
        if v in ("I", "O", "IN", "OUT", "INPUT", "OUTPUT"):
            return "I" if v in ("I", "IN", "INPUT") else "O"
    return ""


def _device_raw_endpoint(d: dict[str, Any]) -> str:
    ep = str(d.get("physicalEndpoint") or d.get("physical_address") or "").strip()
    if ep:
        return ep
    for sig in d.get("signals") or d.get("relatedSignals") or []:
        if not isinstance(sig, dict):
            continue
        ep = str(
            sig.get("physicalEndpoint") or sig.get("physical_address") or ""
        ).strip()
        if ep:
            return ep
    return ""


def _claim_keys_for_device(d: dict[str, Any]) -> set[str]:
    """Ownership claim keys for ORI-051 collision detection.

    Full Rockwell paths claim both the exact ADAPTER:DIR.Data[N].B key and an
    adapter-scoped Data[N].B key so bare suffixes with the same proven adapter
    collide. Incomplete endpoints never invent missing module/channel identity.
    """
    ep = _device_raw_endpoint(d)
    if not ep:
        return set()
    keys: set[str] = set()
    parsed = _parse_rockwell(ep)
    adapter_ctx = _device_adapter_context(d)
    dir_ctx = _device_direction_context(d)

    if parsed and parsed.get("full"):
        full = (
            f"{parsed['adapter']}:{parsed['direction']}"
            f".DATA[{parsed['data_index']}].{parsed['bit']}"
        )
        keys.add(full)
        keys.add(f"{parsed['adapter']}|DATA[{parsed['data_index']}].{parsed['bit']}")
        return keys

    if parsed and not parsed.get("full"):
        data_bit = f"DATA[{parsed['data_index']}].{parsed['bit']}"
        if adapter_ctx:
            keys.add(f"{adapter_ctx}|{data_bit}")
            if dir_ctx:
                keys.add(f"{adapter_ctx}:{dir_ctx}.{data_bit}")
        else:
            # Bare suffix with no adapter context — only collide with identical bare
            keys.add(data_bit)
        return keys

    # Opaque / word.bit — exact normalized key only
    keys.add(normalize_endpoint_key(ep))
    return keys


def build_endpoint_ownership_map(
    devices: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map canonical physical endpoint → claimant devices."""
    by_ep: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_pair: set[tuple[str, int]] = set()
    for idx, d in enumerate(devices or []):
        if not isinstance(d, dict):
            continue
        for key in _claim_keys_for_device(d):
            pair = (key, idx)
            if pair in seen_pair:
                continue
            seen_pair.add(pair)
            by_ep[key].append(d)
    return dict(by_ep)


def apply_endpoint_collision_review(
    devices: list[dict[str, Any]],
) -> dict[str, Any]:
    """ORI-051: multiple claimants of same endpoint → all REVIEW_REQUIRED."""
    ownership = build_endpoint_ownership_map(devices)
    collisions = []
    conflicted_names: set[str] = set()
    # Prefer reporting the most specific (full Rockwell) key when available
    reported: set[frozenset[str]] = set()
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
        name_set = frozenset(n.upper() for n in names)
        # De-dupe collision rows that share the same claimant set via dual keys
        if name_set in reported:
            conflicted_names.update(name_set)
            continue
        reported.add(name_set)
        collisions.append({"endpoint": ep, "claimants": names})
        conflicted_names.update(name_set)
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


def classify_endpoint_proof_depth(
    endpoint: str,
    *,
    valid_endpoints: set[str] | None = None,
    configio_words: set[str] | None = None,
) -> str:
    """ORI-052 proof depth: FULL | WORD_ONLY | NONE.

    FULL requires adapter/module/channel Rockwell identity proven against
    valid_endpoints. Word / word.bit configio matches are WORD_ONLY only.
    """
    raw = str(endpoint or "").strip()
    if not raw:
        return "NONE"

    parsed = _parse_rockwell(raw)
    if parsed and parsed.get("full"):
        if valid_endpoints is not None:
            canon = normalize_endpoint_key(raw)
            valid_canon = {normalize_endpoint_key(x) for x in valid_endpoints if x}
            if canon in valid_canon:
                return "FULL"
        # Well-formed path without hardware-model proof is not READY
        return "NONE"

    # Word-only / incomplete forms never qualify as FULL
    if configio_words is not None:
        words = {str(w).strip().upper() for w in configio_words if str(w).strip()}
        compact = _compact_endpoint(raw)
        if compact in words:
            return "WORD_ONLY"
        m = _WORD_BIT_RE.match(compact)
        if m and m.group(1) in words:
            return "WORD_ONLY"
        # Bare Data[N].B or other non-full forms with only word evidence nearby
        if parsed and not parsed.get("full"):
            return "NONE"

    return "NONE"


def endpoint_is_hardware_backed(
    endpoint: str,
    *,
    valid_endpoints: set[str] | None = None,
    configio_words: set[str] | None = None,
) -> bool:
    """ORI-052: READY only with FULL adapter/module/channel hardware proof."""
    return (
        classify_endpoint_proof_depth(
            endpoint,
            valid_endpoints=valid_endpoints,
            configio_words=configio_words,
        )
        == "FULL"
    )


def _device_has_configio_evidence(d: dict[str, Any]) -> bool:
    """Configio flags alone are not READY proof (ORI-052); retained for depth hints."""
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
    """Mark devices without FULL hardware-backed endpoints as REVIEW (not READY)."""
    not_ready = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if d.get("endpointConflict"):
            continue
        ep = _device_raw_endpoint(d)
        depth = classify_endpoint_proof_depth(
            ep,
            valid_endpoints=valid_endpoints,
            configio_words=configio_words,
        )
        # Configio / io_word alone never upgrades to FULL (ORI-052)
        if depth == "NONE" and configio_words:
            iw = str(d.get("io_word") or "").strip().upper()
            words = {str(w).strip().upper() for w in configio_words if str(w).strip()}
            if iw and iw in words:
                depth = "WORD_ONLY"
            elif _device_has_configio_evidence(d) and ep:
                # Endpoint present + configio flag but no module/channel proof
                compact = _compact_endpoint(ep)
                m = _WORD_BIT_RE.match(compact)
                if m and m.group(1) in words:
                    depth = "WORD_ONLY"
                elif not _parse_rockwell(ep) or not (_parse_rockwell(ep) or {}).get("full"):
                    depth = "WORD_ONLY"

        d["endpoint_proof_depth"] = depth
        backed = depth == "FULL"
        d["hardwareBacked"] = backed

        if not ep and not backed:
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            d["review_reason"] = d.get("review_reason") or "NO_PHYSICAL_ENDPOINT"
            not_ready.append(d.get("name"))
        elif depth == "WORD_ONLY":
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            d["review_reason"] = d.get("review_reason") or "WORD_ONLY_EVIDENCE"
            not_ready.append(d.get("name"))
        elif not backed:
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            reason = "NO_MODULE_CHANNEL_PROOF" if ep else "NO_ACTIVE_MACHINE_HARDWARE"
            d["review_reason"] = d.get("review_reason") or reason
            not_ready.append(d.get("name"))
        else:
            # FULL proof — device is assignment-ready (inventory may still be UNASSIGNED)
            d["readiness"] = "READY"
            d["hardwareBacked"] = True
            if d.get("assignable") is not False and not d.get("endpointConflict"):
                d["assignable"] = True
            # Clear hardware-only review reasons; keep unrelated REVIEW causes
            why = str(d.get("review_reason") or "")
            if why in {
                "",
                "NO_PHYSICAL_ENDPOINT",
                "WORD_ONLY_EVIDENCE",
                "NO_MODULE_CHANNEL_PROOF",
                "NO_ACTIVE_MACHINE_HARDWARE",
            }:
                d.pop("review_reason", None)
                if str(d.get("status") or "").upper() in {
                    "",
                    "REVIEW_REQUIRED",
                    "UNASSIGNED",
                    "GROUPED",
                }:
                    # Prefer UNASSIGNED for inventory membership; readiness carries READY
                    if str(d.get("status") or "").upper() == "REVIEW_REQUIRED":
                        d["status"] = "UNASSIGNED"
    return {
        "not_hardware_backed": not_ready,
        "not_hardware_backed_count": len(not_ready),
        "devices": devices,
    }
