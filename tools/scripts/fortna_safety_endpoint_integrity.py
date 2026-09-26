#!/usr/bin/env python3
"""ORI-051 / ORI-052 / ORI-055 / ORI-056 / ORI-057 — endpoint integrity pipeline.

Ordered pipeline (see apply_endpoint_integrity_pipeline):
  normalize endpoints → resolve signal roles → direction proof →
  collision review → hardware-backed readiness.

Critical mid-migration collision reproducer (ORI-057):
  ESLS610L physicalEndpoint="I.Data[17].2"   # or T_1734:I.Data[17].2
  T_23MCR1 physicalEndpoint="2705.12"
  word_bit_to_endpoint={"2705.12": "T_1734:I.Data[17].2"}
  # after normalize + collision → both REVIEW_REQUIRED
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any


# Full Rockwell channel: ADAPTER:I|O.Data[N].B (whitespace-tolerant after compact)
_ROCKWELL_FULL_RE = re.compile(
    r"^([A-Z0-9_]+):([IO])\.DATA\[(\d+)\]\.(\d+)$",
    re.IGNORECASE,
)
# Direction-prefixed bare: I.Data[N].B / O.Data[N].B (adapter missing)
_ROCKWELL_DIR_BARE_RE = re.compile(
    r"^([IO])\.DATA\[(\d+)\]\.(\d+)$",
    re.IGNORECASE,
)
# Bare image suffix: Data[N].B
_ROCKWELL_DATA_RE = re.compile(
    r"^DATA\[(\d+)\]\.(\d+)$",
    re.IGNORECASE,
)
# Fortna word / word.bit shorthand
_WORD_BIT_RE = re.compile(r"^(\d+)(?:\.(\d+))?$")

_AUX_NAME_RE = re.compile(r"_AUX$", re.IGNORECASE)
_RESET_NAME_RE = re.compile(r"_RESET$", re.IGNORECASE)
_STATUS_NAME_RE = re.compile(
    r"_(?:OK|NOT_OK|STATUS|FLT|FAULT|HEALTH)$",
    re.IGNORECASE,
)
_T_PREFIX_RE = re.compile(r"^T_", re.IGNORECASE)


def _compact_endpoint(endpoint: str) -> str:
    """Uppercase and strip all whitespace for structural comparison."""
    return "".join(str(endpoint or "").upper().split())


def _parse_rockwell(endpoint: str) -> dict[str, Any] | None:
    """Parse Rockwell ADAPTER:DIR.Data[N].B, DIR.Data[N].B, or bare Data[N].B."""
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
    m_dir = _ROCKWELL_DIR_BARE_RE.match(compact)
    if m_dir:
        return {
            "adapter": None,
            "direction": m_dir.group(1).upper(),
            "data_index": int(m_dir.group(2)),
            "bit": int(m_dir.group(3)),
            "full": False,
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
    Direction-prefixed bare I.Data[N].B → I.DATA[N].B.
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
    if parsed and parsed.get("direction") and not parsed.get("full"):
        return (
            f"{parsed['direction']}.DATA[{parsed['data_index']}].{parsed['bit']}"
        )
    if parsed and not parsed.get("full"):
        return f"DATA[{parsed['data_index']}].{parsed['bit']}"
    # Non-Rockwell (word.bit / opaque): collapse whitespace, uppercase
    return _compact_endpoint(raw)


def _format_full_rockwell(adapter: str, direction: str, data_index: int, bit: int) -> str:
    return f"{adapter}:{direction}.DATA[{data_index}].{bit}"


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


def _device_kind(d: dict[str, Any]) -> str:
    return str(d.get("kind") or d.get("deviceKind") or "").strip().upper()


def _device_raw_endpoint(d: dict[str, Any]) -> str:
    """Prefer safetyFeedbackEndpoint for MCR/ESR readiness / ownership claims."""
    kind = _device_kind(d)
    if kind in {"MCR", "ESR"}:
        fb = str(d.get("safetyFeedbackEndpoint") or "").strip()
        if fb:
            return fb
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


def _keys_for_endpoint_string(
    ep: str,
    *,
    adapter_ctx: str = "",
    dir_ctx: str = "",
) -> set[str]:
    """Ownership claim keys for one endpoint spelling."""
    raw = str(ep or "").strip()
    if not raw:
        return set()
    keys: set[str] = set()
    parsed = _parse_rockwell(raw)

    if parsed and parsed.get("full"):
        full = _format_full_rockwell(
            parsed["adapter"],
            parsed["direction"],
            parsed["data_index"],
            parsed["bit"],
        )
        keys.add(full)
        # Adapter-scoped bare Data[N].B — never global I.DATA[N].B (cross-adapter false collisions)
        keys.add(
            f"{parsed['adapter']}|DATA[{parsed['data_index']}].{parsed['bit']}"
        )
        return keys

    if parsed and parsed.get("direction") and not parsed.get("full"):
        data_bit = f"DATA[{parsed['data_index']}].{parsed['bit']}"
        dir_key = f"{parsed['direction']}.{data_bit}"
        keys.add(dir_key)
        adapter = adapter_ctx
        if adapter:
            keys.add(f"{adapter}|{data_bit}")
            keys.add(f"{adapter}:{parsed['direction']}.{data_bit}")
        elif dir_ctx and dir_ctx != parsed["direction"]:
            pass
        return keys

    if parsed and not parsed.get("full"):
        data_bit = f"DATA[{parsed['data_index']}].{parsed['bit']}"
        if adapter_ctx:
            keys.add(f"{adapter_ctx}|{data_bit}")
            if dir_ctx:
                keys.add(f"{adapter_ctx}:{dir_ctx}.{data_bit}")
                keys.add(f"{dir_ctx}.{data_bit}")
        else:
            # Bare suffix with no adapter context — only collide with identical bare
            keys.add(data_bit)
        return keys

    # Opaque / word.bit — exact normalized key only
    keys.add(normalize_endpoint_key(raw))
    return keys


def _claim_keys_for_device(d: dict[str, Any]) -> set[str]:
    """Ownership claim keys for ORI-051 / ORI-057 collision detection.

    Full Rockwell paths claim both the exact ADAPTER:DIR.Data[N].B key and an
    adapter-scoped Data[N].B key so bare suffixes with the same proven adapter
    collide. After normalization, word.bit and Rockwell of the same point share
    keys via the resolved Rockwell form and via endpoint_resolved_from.
    Incomplete endpoints never invent missing module/channel identity.
    """
    ep = _device_raw_endpoint(d)
    adapter_ctx = _device_adapter_context(d)
    dir_ctx = _device_direction_context(d)
    keys = _keys_for_endpoint_string(ep, adapter_ctx=adapter_ctx, dir_ctx=dir_ctx)

    # Mid-migration: also claim the pre-normalization spelling
    resolved_from = str(d.get("endpoint_resolved_from") or "").strip()
    if resolved_from:
        keys |= _keys_for_endpoint_string(
            resolved_from, adapter_ctx=adapter_ctx, dir_ctx=dir_ctx
        )

    # Signal-level endpoints also participate in ownership
    for sig in d.get("signals") or d.get("relatedSignals") or []:
        if not isinstance(sig, dict):
            continue
        sep = str(
            sig.get("physicalEndpoint") or sig.get("physical_address") or ""
        ).strip()
        if sep and sep != ep:
            keys |= _keys_for_endpoint_string(
                sep, adapter_ctx=adapter_ctx, dir_ctx=dir_ctx
            )
        sfrom = str(sig.get("endpoint_resolved_from") or "").strip()
        if sfrom:
            keys |= _keys_for_endpoint_string(
                sfrom, adapter_ctx=adapter_ctx, dir_ctx=dir_ctx
            )
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


def _channel_direction(
    endpoint: str,
    *,
    endpoint_direction: dict[str, str] | None = None,
) -> str:
    """I/O direction from parsed Rockwell :I./:O. or endpoint_direction map."""
    parsed = _parse_rockwell(endpoint)
    if parsed and parsed.get("direction"):
        return str(parsed["direction"]).upper()
    if endpoint_direction:
        canon = normalize_endpoint_key(endpoint)
        for key in (canon, str(endpoint or "").strip(), _compact_endpoint(endpoint)):
            if not key:
                continue
            v = endpoint_direction.get(key)
            if v:
                u = str(v).strip().upper()
                if u in ("I", "IN", "INPUT"):
                    return "I"
                if u in ("O", "OUT", "OUTPUT"):
                    return "O"
    return ""


# ---------------------------------------------------------------------------
# ORI-055 / ORI-056 / ORI-057 — maps, normalize, roles, direction, pipeline
# ---------------------------------------------------------------------------


def build_hardware_endpoint_maps(
    run_dir: Path | str | None,
    machine: str = "",
) -> dict[str, Any]:
    """Build Rockwell ↔ word.bit maps from the hardware I/O model.

    Returns:
      valid_endpoints: set[str] — FULL Rockwell addresses from hardware model
      word_bit_to_endpoint: dict[str,str] — exact "WORD.BIT" → Rockwell addr
      endpoint_to_word_bit: dict[str,str] — reverse
      endpoint_direction: dict[str,str] — normalized Rockwell key → "I" or "O"
    """
    valid_endpoints: set[str] = set()
    word_bit_to_endpoint: dict[str, str] = {}
    endpoint_to_word_bit: dict[str, str] = {}
    endpoint_direction: dict[str, str] = {}
    if not run_dir:
        return {
            "valid_endpoints": valid_endpoints,
            "word_bit_to_endpoint": word_bit_to_endpoint,
            "endpoint_to_word_bit": endpoint_to_word_bit,
            "endpoint_direction": endpoint_direction,
        }
    try:
        from fortna_hardware_io_model import build_hardware_io_model

        hw = build_hardware_io_model(run_dir, machine)
        for adapter in hw.get("adapters") or []:
            for mod in adapter.get("modules") or []:
                for ch in mod.get("channels") or []:
                    if not isinstance(ch, dict):
                        continue
                    addr = str(ch.get("physical_address") or "").strip()
                    if addr:
                        valid_endpoints.add(addr)
                        canon = normalize_endpoint_key(addr)
                        direction = ""
                        parsed = _parse_rockwell(addr)
                        if parsed and parsed.get("direction"):
                            direction = str(parsed["direction"]).upper()
                        else:
                            raw_dir = str(ch.get("direction") or "").strip().upper()
                            if raw_dir in ("I", "IN", "INPUT"):
                                direction = "I"
                            elif raw_dir in ("O", "OUT", "OUTPUT"):
                                direction = "O"
                        if canon and direction in ("I", "O"):
                            endpoint_direction[canon] = direction
                    word = ch.get("fortna_word")
                    if word is None:
                        word = ch.get("octal_word")
                    if word is None:
                        word = ch.get("io_word")
                    bit = ch.get("fortna_bit")
                    if bit is None:
                        bit = ch.get("bit")
                    if bit is None:
                        bit = ch.get("data_bit")
                    if word is not None and bit is not None and addr:
                        # Exact word.bit only — never word-alone (ambiguous across bits)
                        key = f"{int(word)}.{int(bit)}"
                        word_bit_to_endpoint.setdefault(key, addr)
                        endpoint_to_word_bit.setdefault(
                            normalize_endpoint_key(addr), key
                        )
    except Exception:
        pass
    return {
        "valid_endpoints": valid_endpoints,
        "word_bit_to_endpoint": word_bit_to_endpoint,
        "endpoint_to_word_bit": endpoint_to_word_bit,
        "endpoint_direction": endpoint_direction,
    }


def _unique_full_rockwell_for_bare(
    *,
    direction: str | None,
    data_index: int,
    bit: int,
    valid_endpoints: set[str] | None = None,
    word_bit_to_endpoint: dict[str, str] | None = None,
) -> str | None:
    """Resolve bare/dir-bare Data[N].B to full ADAPTER:DIR.Data[N].B if unique."""
    candidates: set[str] = set()
    sources: list[str] = []
    if valid_endpoints:
        sources.extend(str(x) for x in valid_endpoints if x)
    if word_bit_to_endpoint:
        sources.extend(str(v) for v in word_bit_to_endpoint.values() if v)
    want_dir = str(direction or "").upper() or None
    for addr in sources:
        parsed = _parse_rockwell(addr)
        if not parsed or not parsed.get("full"):
            continue
        if int(parsed["data_index"]) != int(data_index):
            continue
        if int(parsed["bit"]) != int(bit):
            continue
        if want_dir and str(parsed["direction"]).upper() != want_dir:
            continue
        candidates.add(
            _format_full_rockwell(
                parsed["adapter"],
                parsed["direction"],
                parsed["data_index"],
                parsed["bit"],
            )
        )
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _resolve_one_endpoint(
    ep: str,
    word_bit_to_endpoint: dict[str, str] | None,
    *,
    valid_endpoints: set[str] | None = None,
) -> tuple[str, str | None]:
    """Return (resolved_endpoint, resolved_from_or_None)."""
    raw = str(ep or "").strip()
    if not raw:
        return "", None
    parsed = _parse_rockwell(raw)
    if parsed and parsed.get("full"):
        # Prefer canonical Rockwell spelling; no resolution provenance
        return (
            _format_full_rockwell(
                parsed["adapter"],
                parsed["direction"],
                parsed["data_index"],
                parsed["bit"],
            ),
            None,
        )

    def _canon_resolved(addr: str) -> str:
        p = _parse_rockwell(addr)
        if p and p.get("full"):
            return _format_full_rockwell(
                p["adapter"], p["direction"], p["data_index"], p["bit"]
            )
        return str(addr)

    wb = word_bit_to_endpoint or {}
    compact = _compact_endpoint(raw)
    # Exact word.bit proof
    if compact in wb:
        return _canon_resolved(wb[compact]), raw
    if raw in wb:
        return _canon_resolved(wb[raw]), raw
    # word.bit with original spelling variants
    m_wb = _WORD_BIT_RE.match(compact)
    if m_wb and m_wb.group(2) is not None:
        key = f"{int(m_wb.group(1))}.{int(m_wb.group(2))}"
        if key in wb:
            return _canon_resolved(wb[key]), raw

    # Direction-prefixed or bare Data[N].B → unique full Rockwell from maps
    if parsed and not parsed.get("full"):
        resolved = _unique_full_rockwell_for_bare(
            direction=parsed.get("direction"),
            data_index=int(parsed["data_index"]),
            bit=int(parsed["bit"]),
            valid_endpoints=valid_endpoints,
            word_bit_to_endpoint=wb or None,
        )
        if resolved:
            return resolved, raw

    return raw, None


def _apply_endpoint_resolution(
    target: dict[str, Any],
    word_bit_to_endpoint: dict[str, str] | None,
    *,
    valid_endpoints: set[str] | None = None,
) -> None:
    ep = str(
        target.get("physicalEndpoint") or target.get("physical_address") or ""
    ).strip()
    if not ep:
        return
    resolved, from_ep = _resolve_one_endpoint(
        ep,
        word_bit_to_endpoint,
        valid_endpoints=valid_endpoints,
    )
    if not resolved or resolved == ep:
        # Still canonicalize full Rockwell spelling in-place when unchanged source
        parsed = _parse_rockwell(ep)
        if parsed and parsed.get("full"):
            canon = _format_full_rockwell(
                parsed["adapter"],
                parsed["direction"],
                parsed["data_index"],
                parsed["bit"],
            )
            if canon != ep:
                target["physicalEndpoint"] = canon
                if target.get("physical_address"):
                    target["physical_address"] = canon
        return
    target["physicalEndpoint"] = resolved
    target["physical_address"] = resolved
    if from_ep:
        target["endpoint_resolved_from"] = from_ep


def normalize_device_endpoints(
    devices: list[dict[str, Any]],
    word_bit_to_endpoint: dict[str, str] | None = None,
    *,
    also_normalize_signals: bool = True,
    valid_endpoints: set[str] | None = None,
) -> list[dict[str, Any]]:
    """ORI-057: resolve word.bit / bare Rockwell forms to FULL Rockwell addresses.

    For each device (and each related signal when also_normalize_signals):
      - word.bit mapped in word_bit_to_endpoint → set physicalEndpoint to Rockwell
      - bare I.Data[n].b / O.Data[n].b / Data[n].b → full ADAPTER:... when unique
      - keep endpoint_resolved_from as the pre-normalization spelling

    MUST run BEFORE collision review.
    """
    wb = word_bit_to_endpoint or {}
    # Derive valid endpoint set from map values when not provided
    ve = set(valid_endpoints or set())
    if not ve and wb:
        ve = {str(v) for v in wb.values() if v}

    for d in devices or []:
        if not isinstance(d, dict):
            continue
        _apply_endpoint_resolution(d, wb, valid_endpoints=ve or None)
        if also_normalize_signals:
            for sig in d.get("signals") or d.get("relatedSignals") or []:
                if isinstance(sig, dict):
                    _apply_endpoint_resolution(sig, wb, valid_endpoints=ve or None)
        # Re-align device physicalEndpoint from feedback after signal normalize
        fb = str(d.get("safetyFeedbackEndpoint") or "").strip()
        if fb:
            resolved, from_ep = _resolve_one_endpoint(
                fb, wb, valid_endpoints=ve or None
            )
            if resolved:
                d["safetyFeedbackEndpoint"] = resolved
                if from_ep and not d.get("endpoint_resolved_from"):
                    # only stamp if device endpoint itself was not resolved
                    pass
        cmd = str(d.get("commandEndpoint") or "").strip()
        if cmd:
            resolved, _from = _resolve_one_endpoint(
                cmd, wb, valid_endpoints=ve or None
            )
            if resolved:
                d["commandEndpoint"] = resolved
    return devices


def _strip_t_prefix(name: str) -> str:
    return _T_PREFIX_RE.sub("", str(name or "").strip())


def _classify_safety_signal_role(
    name: str,
    *,
    kind: str = "",
    existing_role: str = "",
) -> str:
    """Generic safety signal role (no site-specific names)."""
    bare = _strip_t_prefix(str(name or "").strip())
    role_in = str(existing_role or "").strip().upper()
    kind_u = str(kind or "").strip().upper()

    # Name suffixes and AUX role win over coarse PRIMARY
    if role_in == "AUX" or _AUX_NAME_RE.search(bare):
        return "AUX_FEEDBACK"
    if role_in == "RESET" or _RESET_NAME_RE.search(bare):
        return "RESET"
    if role_in in {"STATUS", "OK", "NOT_OK"} or _STATUS_NAME_RE.search(bare):
        return "STATUS"
    if role_in in {"COMMAND", "FEEDBACK", "AUX_FEEDBACK"}:
        return role_in

    if kind_u in {"MCR", "ESR"}:
        # Bare energize coil (no AUX / status / reset) → COMMAND
        return "COMMAND"
    if kind_u in {"ESTOP", "ESLS", "CS"}:
        return "FEEDBACK"
    if role_in == "PRIMARY" or not role_in:
        return "PRIMARY"
    return role_in


def _signal_endpoint(sig: dict[str, Any]) -> str:
    return str(
        sig.get("physicalEndpoint") or sig.get("physical_address") or ""
    ).strip()


def resolve_safety_signal_roles(
    devices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """ORI-055: annotate signal roles and pick feedback/command endpoints.

    Roles: COMMAND, FEEDBACK, AUX_FEEDBACK, RESET, STATUS, PRIMARY.
    Sets d["safetyFeedbackEndpoint"] (prefer INPUT AUX_FEEDBACK/FEEDBACK) and
    d["commandEndpoint"] when a COMMAND coil is present.
    """
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        kind = _device_kind(d)
        signals = [
            s
            for s in (d.get("signals") or d.get("relatedSignals") or [])
            if isinstance(s, dict)
        ]
        feedback_ranked: list[tuple[int, str]] = []
        command_ep = ""
        for sig in signals:
            name = str(sig.get("name") or "").strip()
            existing = str(
                sig.get("safety_role") or sig.get("role") or sig.get("signalRole") or ""
            )
            role = _classify_safety_signal_role(
                name, kind=str(sig.get("kind") or kind), existing_role=existing
            )
            sig["safety_role"] = role
            # Keep role field aligned for downstream consumers
            sig["role"] = role
            ep = _signal_endpoint(sig)
            if not ep:
                continue
            if role == "COMMAND" and not command_ep:
                command_ep = ep
            if role in {"AUX_FEEDBACK", "FEEDBACK"}:
                direction = _channel_direction(ep)
                # Prefer AUX_FEEDBACK over FEEDBACK; prefer INPUT direction
                rank = 0
                if role == "AUX_FEEDBACK":
                    rank += 10
                if direction == "I":
                    rank += 5
                elif direction == "O":
                    rank -= 2
                feedback_ranked.append((rank, ep))

        # Device-level fallback when no signal rows: classify the device itself
        if not signals:
            device_role = _classify_safety_signal_role(
                str(d.get("name") or ""), kind=kind
            )
            d["safety_role"] = device_role
            ep = str(
                d.get("physicalEndpoint") or d.get("physical_address") or ""
            ).strip()
            if device_role == "COMMAND" and ep:
                command_ep = command_ep or ep
            elif device_role in {"AUX_FEEDBACK", "FEEDBACK"} and ep:
                feedback_ranked.append((5 if _channel_direction(ep) == "I" else 0, ep))

        feedback_ranked.sort(key=lambda t: t[0], reverse=True)
        if feedback_ranked:
            d["safetyFeedbackEndpoint"] = feedback_ranked[0][1]
        if command_ep:
            d["commandEndpoint"] = command_ep

        # ESTOP/ESLS/CS: fill blank device endpoint from feedback when missing
        if kind in {"ESTOP", "ESLS", "CS"} and d.get("safetyFeedbackEndpoint"):
            if not str(d.get("physicalEndpoint") or "").strip():
                d["physicalEndpoint"] = d["safetyFeedbackEndpoint"]
    return devices


def _expected_direction_for_input_role(role: str, kind: str) -> str | None:
    """Return expected I/O direction for a safety role, or None if unconstrained."""
    role_u = str(role or "").strip().upper()
    kind_u = str(kind or "").strip().upper()
    if role_u in {"AUX_FEEDBACK", "FEEDBACK"}:
        return "I"
    if role_u == "COMMAND":
        return "O"
    if kind_u in {"ESTOP", "ESLS", "CS"} and role_u in {
        "",
        "PRIMARY",
        "FEEDBACK",
    }:
        return "I"
    if kind_u in {"MCR", "ESR"} and role_u in {"", "PRIMARY", "COMMAND"}:
        return "O"
    return None


def _mark_direction_mismatch(d: dict[str, Any], *, detail: str = "") -> None:
    d["status"] = "REVIEW_REQUIRED"
    d["readiness"] = "REVIEW_REQUIRED"
    d["assignable"] = False
    d["directionMismatch"] = True
    d["review_reason"] = "DIRECTION_MISMATCH"
    if detail:
        d["direction_mismatch_detail"] = detail


def apply_direction_proof(
    devices: list[dict[str, Any]],
    *,
    endpoint_direction: dict[str, str] | None = None,
    valid_endpoints: set[str] | None = None,
) -> dict[str, Any]:
    """ORI-056: refuse READY when signal role direction contradicts channel direction.

    - Input-role Safety (ESTOP, ESLS, ESR/MCR AUX_FEEDBACK) on OUTPUT → DIRECTION_MISMATCH
    - Output-role COMMAND on INPUT channel → DIRECTION_MISMATCH
    Direction from parsed Rockwell :I./:O. or endpoint_direction map.
    """
    mismatches: list[dict[str, Any]] = []
    _ = valid_endpoints  # reserved for future adapter-scoped proofs

    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if d.get("endpointConflict"):
            continue
        kind = _device_kind(d)
        checked = False

        # Signal-level proofs
        for sig in d.get("signals") or d.get("relatedSignals") or []:
            if not isinstance(sig, dict):
                continue
            role = str(
                sig.get("safety_role") or sig.get("role") or sig.get("signalRole") or ""
            ).upper()
            ep = _signal_endpoint(sig)
            if not ep or not role:
                continue
            expected = _expected_direction_for_input_role(role, str(sig.get("kind") or kind))
            if not expected:
                continue
            actual = _channel_direction(ep, endpoint_direction=endpoint_direction)
            if not actual:
                continue
            checked = True
            if actual != expected:
                detail = f"{sig.get('name')}:{role} expects {expected} got {actual} ({ep})"
                _mark_direction_mismatch(d, detail=detail)
                mismatches.append(
                    {
                        "name": d.get("name"),
                        "signal": sig.get("name"),
                        "endpoint": ep,
                        "role": role,
                        "expected": expected,
                        "actual": actual,
                    }
                )
                break

        if d.get("directionMismatch"):
            continue

        # Device-level: feedback / command endpoints
        fb = str(d.get("safetyFeedbackEndpoint") or "").strip()
        if fb and kind in {"MCR", "ESR", "ESTOP", "ESLS", "CS"}:
            actual = _channel_direction(fb, endpoint_direction=endpoint_direction)
            if actual and actual != "I":
                _mark_direction_mismatch(
                    d, detail=f"safetyFeedbackEndpoint expects I got {actual} ({fb})"
                )
                mismatches.append(
                    {
                        "name": d.get("name"),
                        "signal": None,
                        "endpoint": fb,
                        "role": "FEEDBACK",
                        "expected": "I",
                        "actual": actual,
                    }
                )
                continue

        cmd = str(d.get("commandEndpoint") or "").strip()
        if cmd and kind in {"MCR", "ESR"}:
            actual = _channel_direction(cmd, endpoint_direction=endpoint_direction)
            if actual and actual != "O":
                _mark_direction_mismatch(
                    d, detail=f"commandEndpoint expects O got {actual} ({cmd})"
                )
                mismatches.append(
                    {
                        "name": d.get("name"),
                        "signal": None,
                        "endpoint": cmd,
                        "role": "COMMAND",
                        "expected": "O",
                        "actual": actual,
                    }
                )
                continue

        if checked:
            continue

        # Fallback: ESTOP/ESLS/CS primary endpoint must be INPUT
        if kind in {"ESTOP", "ESLS", "CS"}:
            ep = str(
                d.get("physicalEndpoint") or d.get("physical_address") or ""
            ).strip()
            actual = _channel_direction(ep, endpoint_direction=endpoint_direction)
            if ep and actual and actual != "I":
                _mark_direction_mismatch(
                    d, detail=f"{kind} expects I got {actual} ({ep})"
                )
                mismatches.append(
                    {
                        "name": d.get("name"),
                        "signal": None,
                        "endpoint": ep,
                        "role": "FEEDBACK",
                        "expected": "I",
                        "actual": actual,
                    }
                )

    return {
        "direction_mismatches": mismatches,
        "direction_mismatch_count": len(mismatches),
        "devices": devices,
    }


def _role_direction_ok_for_readiness(
    d: dict[str, Any],
    endpoint: str,
    *,
    endpoint_direction: dict[str, str] | None = None,
) -> bool:
    """FULL readiness requires channel direction matching the signal role."""
    if d.get("directionMismatch") or str(d.get("review_reason") or "") == "DIRECTION_MISMATCH":
        return False
    kind = _device_kind(d)
    actual = _channel_direction(endpoint, endpoint_direction=endpoint_direction)
    if not actual:
        # No proven direction on the channel — do not block solely on absence here;
        # hardware map membership still required for FULL.
        return True

    # Prefer role implied by which endpoint we are proving
    fb = str(d.get("safetyFeedbackEndpoint") or "").strip()
    cmd = str(d.get("commandEndpoint") or "").strip()
    ep_norm = normalize_endpoint_key(endpoint)
    if fb and normalize_endpoint_key(fb) == ep_norm:
        return actual == "I"
    if cmd and normalize_endpoint_key(cmd) == ep_norm:
        return actual == "O"
    if kind in {"ESTOP", "ESLS", "CS"}:
        return actual == "I"
    if kind in {"MCR", "ESR"} and fb:
        # Readiness endpoint should be feedback (INPUT)
        return actual == "I"
    return True


def apply_hardware_backed_readiness(
    devices: list[dict[str, Any]],
    *,
    valid_endpoints: set[str] | None = None,
    configio_words: set[str] | None = None,
    endpoint_direction: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Mark devices without FULL hardware-backed endpoints as REVIEW (not READY).

    ORI-056: FULL also requires correct direction for the signal role. Devices
    already marked DIRECTION_MISMATCH stay REVIEW even if the channel exists.
    """
    not_ready = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if d.get("endpointConflict"):
            continue
        if d.get("directionMismatch") or str(d.get("review_reason") or "") == "DIRECTION_MISMATCH":
            d["hardwareBacked"] = False
            d["endpoint_proof_depth"] = d.get("endpoint_proof_depth") or "NONE"
            d["status"] = "REVIEW_REQUIRED"
            d["readiness"] = "REVIEW_REQUIRED"
            d["assignable"] = False
            d["review_reason"] = "DIRECTION_MISMATCH"
            not_ready.append(d.get("name"))
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

        # Direction gate on FULL proof
        if depth == "FULL" and not _role_direction_ok_for_readiness(
            d, ep, endpoint_direction=endpoint_direction
        ):
            _mark_direction_mismatch(
                d, detail=f"FULL channel wrong direction for role ({ep})"
            )
            d["hardwareBacked"] = False
            d["endpoint_proof_depth"] = "FULL"
            not_ready.append(d.get("name"))
            continue

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


def apply_endpoint_integrity_pipeline(
    devices: list[dict[str, Any]],
    *,
    run_dir: Path | str | None = None,
    machine: str = "",
    valid_endpoints: set[str] | None = None,
    word_bit_to_endpoint: dict[str, str] | None = None,
    configio_words: set[str] | None = None,
    endpoint_direction: dict[str, str] | None = None,
) -> dict[str, Any]:
    """ORI pipeline: normalize → roles → hardware → direction → collision → READY."""
    ve = set(valid_endpoints or set())
    wb = dict(word_bit_to_endpoint or {})
    ed = dict(endpoint_direction or {})

    if run_dir and (not ve or not wb or not ed):
        maps = build_hardware_endpoint_maps(run_dir, machine)
        if not ve:
            ve = set(maps.get("valid_endpoints") or set())
        if not wb:
            wb = dict(maps.get("word_bit_to_endpoint") or {})
        if not ed:
            ed = dict(maps.get("endpoint_direction") or {})

    # 1. Normalize endpoints (BEFORE collision)
    normalize_device_endpoints(
        devices,
        wb,
        also_normalize_signals=True,
        valid_endpoints=ve or None,
    )
    # 2. Resolve signal roles / feedback vs command
    resolve_safety_signal_roles(devices)
    # 3. Direction proof (ORI-056)
    direction_report = apply_direction_proof(
        devices,
        endpoint_direction=ed or None,
        valid_endpoints=ve or None,
    )
    # 4. Collision review AFTER normalize (ORI-051 / ORI-057)
    collision_report = apply_endpoint_collision_review(devices)
    # 5. Hardware-backed readiness (ORI-052 / ORI-056 direction gate)
    readiness_report = apply_hardware_backed_readiness(
        devices,
        valid_endpoints=ve or None,
        configio_words=configio_words,
        endpoint_direction=ed or None,
    )
    return {
        "collisions": collision_report.get("collisions") or [],
        "conflicted_count": int(collision_report.get("conflicted_count") or 0),
        "not_hardware_backed": readiness_report.get("not_hardware_backed") or [],
        "not_hardware_backed_count": int(
            readiness_report.get("not_hardware_backed_count") or 0
        ),
        "direction_mismatches": direction_report.get("direction_mismatches") or [],
        "direction_mismatch_count": int(
            direction_report.get("direction_mismatch_count") or 0
        ),
        "devices": devices,
        "valid_endpoints": ve,
        "word_bit_to_endpoint": wb,
        "endpoint_direction": ed,
    }
