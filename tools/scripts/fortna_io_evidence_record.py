#!/usr/bin/env python3
"""Structured I/O EvidenceRecord — Site Forge Investigator + future RELAY data plane.

ORI-029: unsupported / unresolved physical evidence remains visible as structured
records. UNKNOWN fields stay representable. Never invent adapter/module/endpoint/
ownership/direction.

AI_ENDPOINT_AUTHORITY = false — these records are advisory evidence only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


AI_ENDPOINT_AUTHORITY = False
USE_FOR_BUILD = False


@dataclass
class EvidenceRecord:
    """Canonical read-only evidence row for Investigator / RELAY."""

    evidence_id: str
    controller: str = ""
    owner_state: str = "UNKNOWN"
    source: str = ""
    source_location: str = ""

    interface_family: str = ""

    raw_address: str = ""
    normalized_address_candidate: str = ""

    direction_evidence: str = ""

    adapter_evidence: str = ""
    module_evidence: str = ""
    channel_evidence: str = ""

    tag_name: str = ""
    signal_name: str = ""
    device_candidate: str = ""

    confidence_state: str = "REVIEW_REQUIRED"
    unresolved_reason: str = ""

    provenance: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ai_endpoint_authority"] = AI_ENDPOINT_AUTHORITY
        d["use_for_build"] = USE_FOR_BUILD
        return d


def evidence_record_from_unsupported_row(
    row: dict[str, Any],
    *,
    controller: str = "",
) -> EvidenceRecord:
    """Map ORI-029 unsupported Configio row → EvidenceRecord (no invention)."""
    iface = str(row.get("interface") or row.get("interface_family") or "").strip()
    word = row.get("octal_word")
    if word is None:
        word = row.get("word_text") or ""
    bank = row.get("bank")
    raw_addr = ""
    if word not in (None, "", 0):
        raw_addr = str(word)
    eid = (
        f"unsup:{iface}:{row.get('source_file') or ''}:{row.get('source_row') or row.get('row')}"
    )
    return EvidenceRecord(
        evidence_id=eid,
        controller=str(row.get("controller") or controller or "").strip(),
        owner_state="UNKNOWN",
        source="CONFIGIO",
        source_location=str(
            row.get("source_file")
            or (row.get("provenance") or {}).get("table")
            or ""
        ),
        interface_family=iface,
        raw_address=raw_addr,
        normalized_address_candidate="",  # never invent Rockwell path
        direction_evidence=str(row.get("direction") or row.get("in_out") or "").strip(),
        adapter_evidence="",  # unknown — do not invent
        module_evidence="",
        channel_evidence="",
        tag_name="",
        signal_name=str(row.get("desc") or "").strip(),
        device_candidate="",
        confidence_state=str(row.get("disposition") or "REVIEW_REQUIRED"),
        unresolved_reason=str(
            row.get("unresolved_reason")
            or f"deterministic_decoder_does_not_support_interface={iface}"
        ),
        provenance=dict(row.get("provenance") or {})
        or {
            "table": row.get("source_file"),
            "row": row.get("source_row", row.get("row")),
            "kind": "RAW_CONFIGIO_UNSUPPORTED_INTERFACE",
        },
        extras={
            "bank": bank,
            "lohi": row.get("lohi"),
            "status": row.get("status") or "UNSUPPORTED_INTERFACE",
            "physical_endpoint": None,
        },
    )


def evidence_record_from_claim(
    claim: dict[str, Any],
    *,
    controller: str = "",
) -> EvidenceRecord:
    """Map a deterministic claim ledger row → EvidenceRecord."""
    cid = str(claim.get("claim_id") or claim.get("io_name") or "").strip()
    word = claim.get("word")
    bit = claim.get("bit")
    raw = ""
    if word is not None and bit is not None:
        raw = f"{word}.{bit}"
    elif word is not None:
        raw = str(word)
    phys = str(claim.get("physical_address") or "").strip()
    disp = str(claim.get("deterministic_disposition") or "").upper()
    if disp in {"ASSIGNED", "PROVEN"}:
        state = "PROVEN" if phys else "REVIEW_REQUIRED"
    elif disp:
        state = "REVIEW_REQUIRED"
    else:
        state = "UNKNOWN"
    return EvidenceRecord(
        evidence_id=f"claim:{cid}",
        controller=str(claim.get("controller") or controller or "").strip(),
        owner_state=str(claim.get("owner_state") or claim.get("owner") or "UNKNOWN"),
        source=str(claim.get("source") or "CLAIM_LEDGER"),
        source_location=str(claim.get("source_file") or claim.get("table") or ""),
        interface_family=str(claim.get("interface") or "").strip(),
        raw_address=raw,
        normalized_address_candidate=phys,
        direction_evidence=str(claim.get("direction") or claim.get("in_out") or "").strip(),
        adapter_evidence=str(claim.get("adapter") or "").strip(),
        module_evidence=str(claim.get("module") or claim.get("module_type") or "").strip(),
        channel_evidence=phys,
        tag_name=str(claim.get("io_name") or "").strip(),
        signal_name=str(claim.get("io_name") or claim.get("desc") or "").strip(),
        device_candidate=str(claim.get("device_name") or "").strip(),
        confidence_state=state,
        unresolved_reason=str(claim.get("unresolved_reason") or "").strip(),
        provenance={
            "claim_id": cid,
            "disposition": disp,
            "kind": "DETERMINISTIC_CLAIM",
        },
        extras={
            "bit": bit,
            "word": word,
            "deterministic_disposition": disp,
        },
    )


def build_evidence_records(
    evidence_bundle: dict[str, Any],
    *,
    controller: str = "",
) -> list[dict[str, Any]]:
    """Flatten evidence bundle → EvidenceRecord dicts for Investigator / RELAY."""
    mach = str(
        controller
        or evidence_bundle.get("machine")
        or evidence_bundle.get("controller")
        or ""
    ).strip()
    out: list[EvidenceRecord] = []
    for row in evidence_bundle.get("unsupported_interface_rows") or []:
        if isinstance(row, dict):
            out.append(evidence_record_from_unsupported_row(row, controller=mach))
    for claim in evidence_bundle.get("raw_claims") or []:
        if isinstance(claim, dict):
            out.append(evidence_record_from_claim(claim, controller=mach))
    return [r.to_dict() for r in out]


def get_evidence_related_to_signal(
    evidence_bundle: dict[str, Any],
    *,
    signal: str = "",
    word: Any = None,
    interface: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """Investigator query: all evidence related to an unresolved I/O signal."""
    want = str(signal or "").strip().upper()
    want_iface = str(interface or "").strip().upper()
    want_word = None
    if word is not None and str(word).strip() != "":
        try:
            want_word = int(float(str(word)))
        except (TypeError, ValueError):
            want_word = str(word).strip()

    records = build_evidence_records(evidence_bundle)
    hits: list[dict[str, Any]] = []
    for r in records:
        if want and want not in str(r.get("signal_name") or "").upper() and want not in str(
            r.get("tag_name") or ""
        ).upper() and want not in str(r.get("evidence_id") or "").upper():
            # still allow word/interface match
            if not want_word and not want_iface:
                continue
        if want_iface and want_iface not in str(r.get("interface_family") or "").upper():
            continue
        if want_word is not None:
            raw = str(r.get("raw_address") or "")
            extras = r.get("extras") or {}
            w = extras.get("word")
            if w is None and "." in raw:
                try:
                    w = int(float(raw.split(".", 1)[0]))
                except (TypeError, ValueError):
                    w = raw
            elif w is None and raw:
                try:
                    w = int(float(raw))
                except (TypeError, ValueError):
                    w = raw
            if str(w) != str(want_word):
                continue
        hits.append(r)
        if len(hits) >= max(1, int(limit or 100)):
            break
    return {
        "ok": True,
        "query": {"signal": signal, "word": word, "interface": interface},
        "count": len(hits),
        "records": hits,
        "ai_endpoint_authority": AI_ENDPOINT_AUTHORITY,
        "use_for_build": USE_FOR_BUILD,
        "read_only": True,
    }
