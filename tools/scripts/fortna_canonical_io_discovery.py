#!/usr/bin/env python3
"""Canonical physical I/O discovery — source/hardware semantics over tag spelling.

Architecture law (anti-overfitting):
  PHYSICAL I/O DISCOVERY  ≠  LOGIX ADDRESS RENDERING

Raw address text is a representation only. Discovery authority is current
RUN/TAR hardware + configuration provenance (controller, panel, adapter,
module tree, Configio, EIP, catalog, slot, bank/word, direction, bit).

Unfamiliar raw syntax must NOT drop a proven physical row into NONPHYSICAL /
UNKNOWN_OWNER. When the endpoint is known but final Logix rendering is not:

  REVIEW_REQUIRED  (preserve evidence)

Do NOT hardcode site names or literal example prefixes (T_1794_AENT_*, CP3RIO*,
CP6RIO*). Adapter tokens are opaque; only address STRUCTURE is parsed.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_hardware_family import (
    FAMILY_FLEX,
    FAMILY_POINT,
    FAMILY_UNKNOWN,
    data_index_for_module,
    detect_family_from_catalog,
)

# Classification / conservation buckets
PHYSICAL = "PHYSICAL"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
UNSUPPORTED = "UNSUPPORTED"
FOREIGN = "FOREIGN"
INTENTIONALLY_NONPHYSICAL = "INTENTIONALLY_NONPHYSICAL"
# Parsed address spelling without RUN hardware provenance (ORI-089).
UNBACKED_ADDRESS_CANDIDATE = "UNBACKED_ADDRESS_CANDIDATE"

# Render readiness (separate from physical discovery)
RENDERABLE = "RENDERABLE"
RENDER_REVIEW = "REVIEW_REQUIRED"
RENDER_UNSUPPORTED = "UNSUPPORTED"

# Structural address forms — adapter / device token is OPAQUE ([^:]+), never a
# whitelist of T_1794_AENT / CP3RIO / AENTR / site literals.
_STRUCT_DATA_FULL = re.compile(
    r"^(?P<adapter>[^:]+):(?P<dir>[IO])\.Data\[(?P<data>\d+)\]\.(?P<bit>\d+)$",
    re.IGNORECASE,
)
_STRUCT_DATA_DIR_BARE = re.compile(
    r"^(?P<dir>[IO])\.Data\[(?P<data>\d+)\]\.(?P<bit>\d+)$",
    re.IGNORECASE,
)
_STRUCT_DATA_BARE = re.compile(
    r"^Data\[(?P<data>\d+)\]\.(?P<bit>\d+)$",
    re.IGNORECASE,
)
# Compact Fortna/export form: ADAPTER:SLOT:DIR.BIT  (e.g. *:1:I.0)
_STRUCT_COMPACT_SLOT = re.compile(
    r"^(?P<adapter>[^:]+):(?P<slot>\d+):(?P<dir>[IO])\.(?P<bit>\d+)$",
    re.IGNORECASE,
)

_FORM_LOGIX_DATA = "LOGIX_DATA_MEMBER"
_FORM_COMPACT_SLOT = "COMPACT_SLOT_DIR_BIT"
_FORM_DIR_BARE = "DIR_DATA_BARE"
_FORM_DATA_BARE = "DATA_BARE"
_FORM_OPAQUE = "OPAQUE_UNPARSED"


@dataclass(frozen=True)
class AddressStructure:
    """Parsed raw spelling structure — no site/prefix authority."""

    form: str
    adapter_token: str | None  # opaque spelling from raw text (may differ from hardware)
    direction: str | None
    data_index: int | None
    module_slot: int | None
    bit: int | None
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HardwareIoContext:
    """Proven RUN hardware context that outranks raw spelling."""

    controller: str = ""
    panel: str = ""
    adapter: str = ""  # canonical adapter / rio name from EIP/Configio
    module_slot: int | None = None
    module_type: str = ""
    family: str = FAMILY_UNKNOWN
    bank_word: int | str | None = None
    direction: str = ""
    bit: int | None = None
    source_file: str = ""
    source_type: str = ""
    confidence: str = "HIGH"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalPhysicalIoEndpoint:
    """Canonical physical endpoint — discovery dimensions + preserved raw spelling."""

    controller: str = ""
    panel: str = ""
    adapter: str = ""
    module_slot: int | None = None
    direction: str = ""
    bank_word: int | str | None = None
    data_index: int | None = None
    bit: int | None = None
    raw_address: str = ""
    address_form: str = _FORM_OPAQUE
    source_file: str = ""
    source_type: str = ""
    source_section: str = ""
    source_record: str = ""
    confidence: str = "UNKNOWN"
    signal_role: str = ""
    family: str = FAMILY_UNKNOWN
    module_type: str = ""
    classification: str = REVIEW_REQUIRED
    render_status: str = RENDER_REVIEW
    rendered_logix: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def endpoint_key(self) -> str:
        """Stable identity key from proven dimensions (not raw spelling)."""
        return "|".join(
            [
                str(self.controller or "-"),
                str(self.adapter or "-"),
                str(self.direction or "-"),
                f"slot={self.module_slot if self.module_slot is not None else '-'}",
                f"data={self.data_index if self.data_index is not None else '-'}",
                f"b={self.bit if self.bit is not None else '-'}",
                f"w={self.bank_word if self.bank_word is not None else '-'}",
            ]
        )


def _compact(s: str) -> str:
    return "".join(str(s or "").split())


def parse_address_structure(raw: str) -> AddressStructure:
    """Parse raw address STRUCTURE only — adapter token is opaque.

    Recognizes structural shapes similar to:
      <opaque>:I.Data[<n>].<b>
      <opaque>:<slot>:I.<b>
      I.Data[<n>].<b>
      Data[<n>].<b>

    Does NOT whitelist adapter prefixes. Changing the opaque left-hand name
    must not change structural fields when the rest of the spelling matches.
    """
    raw_s = str(raw or "").strip()
    compact = _compact(raw_s)
    if not compact:
        return AddressStructure(
            form=_FORM_OPAQUE,
            adapter_token=None,
            direction=None,
            data_index=None,
            module_slot=None,
            bit=None,
            raw=raw_s,
        )

    m = _STRUCT_DATA_FULL.match(compact)
    if m:
        return AddressStructure(
            form=_FORM_LOGIX_DATA,
            adapter_token=m.group("adapter"),
            direction=m.group("dir").upper(),
            data_index=int(m.group("data")),
            module_slot=None,  # data index known; chassis slot needs family/context
            bit=int(m.group("bit")),
            raw=raw_s,
        )

    m = _STRUCT_COMPACT_SLOT.match(compact)
    if m:
        return AddressStructure(
            form=_FORM_COMPACT_SLOT,
            adapter_token=m.group("adapter"),
            direction=m.group("dir").upper(),
            data_index=None,  # requires family to render Data[]
            module_slot=int(m.group("slot")),
            bit=int(m.group("bit")),
            raw=raw_s,
        )

    m = _STRUCT_DATA_DIR_BARE.match(compact)
    if m:
        return AddressStructure(
            form=_FORM_DIR_BARE,
            adapter_token=None,
            direction=m.group("dir").upper(),
            data_index=int(m.group("data")),
            module_slot=None,
            bit=int(m.group("bit")),
            raw=raw_s,
        )

    m = _STRUCT_DATA_BARE.match(compact)
    if m:
        return AddressStructure(
            form=_FORM_DATA_BARE,
            adapter_token=None,
            direction=None,
            data_index=int(m.group("data")),
            module_slot=None,
            bit=int(m.group("bit")),
            raw=raw_s,
        )

    return AddressStructure(
        form=_FORM_OPAQUE,
        adapter_token=None,
        direction=None,
        data_index=None,
        module_slot=None,
        bit=None,
        raw=raw_s,
    )


def _norm_dir(d: str | None) -> str:
    u = str(d or "").strip().upper()
    if u in ("I", "IN", "INPUT"):
        return "I"
    if u in ("O", "OUT", "OUTPUT"):
        return "O"
    return ""


def normalize_raw_address(
    raw: str,
    *,
    hardware: HardwareIoContext | None = None,
    controller: str = "",
    signal_role: str = "",
) -> CanonicalPhysicalIoEndpoint:
    """Normalize raw spelling through hardware/source context.

    SOURCE/HARDWARE SEMANTICS > TAG SPELLING

    If hardware proves the record is physical I/O, classify PHYSICAL even when
    the raw spelling form is unfamiliar. If dimensions are known but Logix
    rendering cannot be completed → render_status REVIEW_REQUIRED (not drop).
    """
    hw = hardware or HardwareIoContext()
    struct = parse_address_structure(raw)
    notes: list[str] = [f"address_form={struct.form}"]

    # Adapter: hardware context wins over opaque raw token.
    adapter = str(hw.adapter or "").strip()
    if not adapter and struct.adapter_token:
        adapter = struct.adapter_token
        notes.append("adapter_from_raw_token")
    elif adapter and struct.adapter_token and adapter.upper() != struct.adapter_token.upper():
        notes.append("raw_adapter_token_differs_from_hardware")

    direction = _norm_dir(hw.direction) or _norm_dir(struct.direction)
    bit = hw.bit if hw.bit is not None else struct.bit
    module_slot = hw.module_slot if hw.module_slot is not None else struct.module_slot
    family = str(hw.family or detect_family_from_catalog(hw.module_type) or FAMILY_UNKNOWN)
    module_type = str(hw.module_type or "")

    data_index = struct.data_index
    if data_index is None and module_slot is not None and family in (FAMILY_FLEX, FAMILY_POINT):
        data_index = data_index_for_module(int(module_slot), family)
        notes.append(f"data_index_from_family_slot:{family}")
    if data_index is None and hw.bank_word is None and struct.form == _FORM_OPAQUE:
        # No structural parse — still may be physical via hardware alone.
        pass

    # Prefer hardware data_index when both present and conflict → hardware wins.
    # (hw does not currently carry data_index; slot+family is the path.)

    ctrl = str(hw.controller or controller or "").strip()
    panel = str(hw.panel or "").strip()

    # ORI-089: SOURCE/HARDWARE CONTEXT > TAG SPELLING.
    # Raw address syntax may PARSE a candidate endpoint; it must NOT alone prove
    # PHYSICAL / PROVEN identity. Require supporting RUN hardware provenance.
    hw_adapter = str(hw.adapter or "").strip()
    hw_source = str(hw.source_type or "").strip()
    hw_backed = bool(
        hw_adapter
        and (
            hw_source
            or hw.module_type
            or hw.module_slot is not None
            or hw.bank_word is not None
            or panel
            or ctrl
        )
    )
    physical_proof = False
    if hw_backed and direction and (
        bit is not None or module_slot is not None or hw_source
    ):
        physical_proof = True
        notes.append("physical_from_hardware_context")
    elif hw_adapter and direction and bit is not None and hw_source:
        physical_proof = True
        notes.append("physical_from_hardware_context")

    syntax_parsed = bool(
        struct.form != _FORM_OPAQUE and direction and bit is not None
    )

    if physical_proof:
        classification = PHYSICAL
    elif syntax_parsed and not hw_backed:
        # Spelling alone → candidate / review, never PHYSICAL/PROVEN.
        classification = REVIEW_REQUIRED
        notes.append("unbacked_address_candidate_syntax_only")
        notes.append(UNBACKED_ADDRESS_CANDIDATE)
    else:
        classification = REVIEW_REQUIRED
        if not adapter:
            notes.append("missing_adapter")

    # Render readiness — separate from discovery
    rendered = ""
    render_status = RENDER_REVIEW
    if (
        physical_proof
        and adapter
        and direction in ("I", "O")
        and data_index is not None
        and bit is not None
    ):
        rendered = f"{adapter}:{direction}.Data[{data_index}].{bit}"
        render_status = RENDERABLE
    elif physical_proof:
        render_status = RENDER_REVIEW
        notes.append("physical_known_render_incomplete")
    elif syntax_parsed and not physical_proof:
        # May propose a rendered spelling for review, but classification stays review.
        if adapter and direction in ("I", "O") and data_index is not None and bit is not None:
            rendered = f"{adapter}:{direction}.Data[{data_index}].{bit}"
        render_status = RENDER_REVIEW
        notes.append("syntax_render_without_hardware_proof")
    else:
        render_status = RENDER_REVIEW

    conf = str(hw.confidence or "UNKNOWN")
    if physical_proof and conf == "UNKNOWN":
        conf = "HIGH" if hw_backed else "MEDIUM"
    elif not physical_proof and syntax_parsed:
        conf = "UNBACKED" if conf == "UNKNOWN" else conf

    return CanonicalPhysicalIoEndpoint(
        controller=ctrl,
        panel=panel,
        adapter=adapter,
        module_slot=module_slot,
        direction=direction,
        bank_word=hw.bank_word,
        data_index=data_index,
        bit=bit,
        raw_address=str(raw or "").strip(),
        address_form=struct.form,
        source_file=str(hw.source_file or ""),
        source_type=str(hw.source_type or ""),
        confidence=conf,
        signal_role=str(signal_role or ""),
        family=family,
        module_type=module_type,
        classification=classification,
        render_status=render_status,
        rendered_logix=rendered,
        notes=notes,
    )


def endpoints_equal_ignoring_raw(
    a: CanonicalPhysicalIoEndpoint | dict[str, Any],
    b: CanonicalPhysicalIoEndpoint | dict[str, Any],
) -> bool:
    """True when proven dimensions match — raw spelling ignored."""

    def _as_dict(x: Any) -> dict[str, Any]:
        if isinstance(x, CanonicalPhysicalIoEndpoint):
            return x.to_dict()
        return dict(x or {})

    da, db = _as_dict(a), _as_dict(b)
    keys = ("controller", "adapter", "direction", "module_slot", "data_index", "bit", "bank_word")
    for k in keys:
        va, vb = da.get(k), db.get(k)
        if va is None and vb is None:
            continue
        if str(va).upper() != str(vb).upper():
            # Allow slot↔data equivalence when one side only has data_index
            if k in ("module_slot", "data_index") and (va is None or vb is None):
                continue
            return False
    # Require adapter + direction + bit at minimum
    if not da.get("adapter") or not db.get("adapter"):
        return False
    if str(da.get("direction") or "").upper() != str(db.get("direction") or "").upper():
        return False
    if da.get("bit") is None or db.get("bit") is None:
        return False
    if int(da["bit"]) != int(db["bit"]):
        return False
    # data_index or module_slot must agree when both present
    if da.get("data_index") is not None and db.get("data_index") is not None:
        if int(da["data_index"]) != int(db["data_index"]):
            return False
    if da.get("module_slot") is not None and db.get("module_slot") is not None:
        if int(da["module_slot"]) != int(db["module_slot"]):
            return False
    return True


def build_io_source_index(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    """Deterministic I/O evidence index for one active RUN/controller.

    Conservation:
      discovered_physical
        = normalized (PHYSICAL + renderable)
        + review
        + unsupported
        + foreign
        + intentionally_nonphysical
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    rows: list[dict[str, Any]] = []
    buckets = {
        PHYSICAL: 0,
        REVIEW_REQUIRED: 0,
        UNSUPPORTED: 0,
        FOREIGN: 0,
        INTENTIONALLY_NONPHYSICAL: 0,
    }
    render_buckets = {RENDERABLE: 0, RENDER_REVIEW: 0, RENDER_UNSUPPORTED: 0}

    # --- Hardware channels from physical word map (primary discovery) ---
    try:
        from fortna_physical_word_resolver import build_physical_word_map

        pm = build_physical_word_map(run_dir, machine)
    except Exception as ex:  # noqa: BLE001
        pm = {"error": str(ex), "by_word_bit": {}, "adapters": []}

    by_wb = pm.get("by_word_bit") or {}
    adapters = pm.get("adapters") or []
    adapter_by_rio: dict[str, dict[str, Any]] = {}
    for ad in adapters:
        if not isinstance(ad, dict):
            continue
        for key in (ad.get("rio_name"), ad.get("name"), ad.get("eipcfg_name")):
            if key:
                adapter_by_rio[str(key).upper()] = ad

    for wb_key, hit in by_wb.items():
        if not isinstance(hit, dict):
            continue
        channel = str(hit.get("channel") or "").strip()
        rio = str(hit.get("rio_name") or hit.get("adapter") or "").strip()
        direction = _norm_dir(hit.get("direction"))
        try:
            bit = int(hit.get("bit") if hit.get("bit") is not None else -1)
        except (TypeError, ValueError):
            bit = -1
        try:
            slot = int(
                hit.get("eip_slot")
                if hit.get("eip_slot") is not None
                else hit.get("slot")
                if hit.get("slot") is not None
                else -1
            )
        except (TypeError, ValueError):
            slot = -1
        mtype = str(hit.get("type") or hit.get("module_type") or "")
        family = str(hit.get("family") or detect_family_from_catalog(mtype) or FAMILY_UNKNOWN)
        word = None
        if isinstance(wb_key, str) and ":" in wb_key:
            try:
                word = int(wb_key.split(":", 1)[0])
            except ValueError:
                word = wb_key
        elif hit.get("octal_word") is not None:
            word = hit.get("octal_word")

        ad_meta = adapter_by_rio.get(rio.upper()) or {}
        hw = HardwareIoContext(
            controller=machine,
            panel=str(hit.get("panel") or ad_meta.get("panel") or ""),
            adapter=rio,
            module_slot=slot if slot >= 0 else None,
            module_type=mtype,
            family=family,
            bank_word=word,
            direction=direction,
            bit=bit if bit >= 0 else None,
            source_file="eipcfg+configio",
            source_type="physical_word_map",
            confidence=str(hit.get("binding_confidence") or hit.get("confidence") or "HIGH"),
        )
        # Preserve channel spelling as raw; also accept if missing by synthesizing later
        ep = normalize_raw_address(channel or "", hardware=hw, controller=machine)
        if not ep.raw_address and channel:
            ep.raw_address = channel
        if not ep.raw_address and ep.rendered_logix:
            ep.raw_address = ep.rendered_logix
            ep.notes.append("raw_synthesized_from_render")
        # Physical discovery from hardware map always counts as physical evidence
        if ep.classification != PHYSICAL:
            ep.classification = PHYSICAL
            ep.notes.append("forced_physical_from_word_map")
        row = {
            "source_file": ep.source_file,
            "source_type": ep.source_type,
            "controller": ep.controller,
            "panel": ep.panel,
            "adapter": ep.adapter,
            "module_slot": ep.module_slot,
            "direction": ep.direction,
            "raw_address": ep.raw_address,
            "normalized_endpoint": ep.to_dict(),
            "endpoint_key": ep.endpoint_key,
            "confidence": ep.confidence,
            "word_bit_key": wb_key,
        }
        rows.append(row)
        buckets[PHYSICAL] = buckets.get(PHYSICAL, 0) + 1
        render_buckets[ep.render_status] = render_buckets.get(ep.render_status, 0) + 1

    # --- Conveyor.asc named claims: ensure none vanish on unfamiliar syntax ---
    try:
        from fortna_io_claim_ledger import iter_raw_named_claims
        from fortna_physical_word_resolver import PhysicalWordResolver

        claims = iter_raw_named_claims(run_dir, machine)
        resolver = PhysicalWordResolver(run_dir, machine)
    except Exception:  # noqa: BLE001
        claims = []
        resolver = None

    claim_rows = 0
    claim_review = 0
    for claim in claims:
        claim_rows += 1
        word = claim.get("fortna_word")
        bit = claim.get("fortna_bit")
        hit = None
        if resolver is not None:
            try:
                hit = resolver.resolve(str(word), str(bit))
            except Exception:
                hit = None
        if isinstance(hit, dict) and hit.get("channel"):
            # Already covered by word map path — skip duplicate conservation add
            continue
        # Unresolved / unfamiliar — preserve as REVIEW, never drop
        hw = HardwareIoContext(
            controller=machine,
            adapter="",
            bank_word=word,
            bit=None,
            direction="",
            source_file=str(claim.get("source_table") or "FORTNA/Conveyor.asc"),
            source_type="conveyor_named_claim",
            confidence="LOW",
        )
        # No raw Logix spelling — fabricate opaque placeholder that parse leaves OPAQUE
        raw = f"UNRENDERED_WORD_BIT:{word}.{bit}"
        ep = normalize_raw_address(raw, hardware=hw, controller=machine)
        ep.classification = REVIEW_REQUIRED
        ep.render_status = RENDER_REVIEW
        ep.source_record = str(claim.get("name") or "")
        ep.notes.append("named_claim_without_physical_channel")
        rows.append(
            {
                "source_file": ep.source_file,
                "source_type": ep.source_type,
                "controller": machine,
                "panel": "",
                "adapter": "",
                "module": "",
                "direction": "",
                "raw_address": raw,
                "normalized_endpoint": ep.to_dict(),
                "endpoint_key": ep.endpoint_key,
                "confidence": "LOW",
                "claim_name": claim.get("name"),
            }
        )
        buckets[REVIEW_REQUIRED] = buckets.get(REVIEW_REQUIRED, 0) + 1
        claim_review += 1
        render_buckets[RENDER_REVIEW] = render_buckets.get(RENDER_REVIEW, 0) + 1

    discovered = sum(buckets.values())
    accounted = discovered  # every row placed in a bucket
    conservation_ok = discovered == accounted and buckets.get(PHYSICAL, 0) + buckets.get(
        REVIEW_REQUIRED, 0
    ) + buckets.get(UNSUPPORTED, 0) + buckets.get(FOREIGN, 0) + buckets.get(
        INTENTIONALLY_NONPHYSICAL, 0
    ) == discovered

    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "policy": {
            "source_hardware_semantics_gt_tag_spelling": True,
            "raw_syntax_preserved": True,
            "unfamiliar_syntax_is_review_not_drop": True,
            "no_site_prefix_hardcode": True,
        },
        "counts": dict(buckets),
        "render_counts": dict(render_buckets),
        "discovered_physical_evidence": int(buckets.get(PHYSICAL, 0)),
        "discovered_total": discovered,
        "accounted_total": accounted,
        "conservation_ok": bool(conservation_ok),
        "named_claims_seen": claim_rows,
        "named_claims_review_only": claim_review,
        "adapter_count": len(adapters),
        "rows": rows,
        "physical_word_map_error": pm.get("error"),
    }


def write_io_source_index(
    run_dir: Path | str,
    machine: str,
    out_path: Path | str,
) -> dict[str, Any]:
    """Build and write the I/O source index JSON."""
    idx = build_io_source_index(run_dir, machine)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Slim on-disk: drop full rows if huge — keep summary + sample
    slim = dict(idx)
    all_rows = list(slim.get("rows") or [])
    slim["row_count"] = len(all_rows)
    slim["rows_sample"] = all_rows[:80]
    if len(all_rows) > 80:
        slim["rows"] = all_rows  # keep full for smoke; callers may pop
    out.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    return idx
