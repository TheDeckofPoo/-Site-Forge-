#!/usr/bin/env python3
"""Automatic 1794/1734 rack + module discovery (deterministic).

Display names (AREA_RIO_N / engineer rename) never affect canonical identity,
slots, banks, or compiler relationships.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fortna_asc import read_asc
from fortna_hardware_family import channel_capacity_for_catalog, detect_family_from_catalog
from fortna_hardware_identity import build_hardware_identity_model
from fortna_physical_word_resolver import (
    _find_eipcfg,
    _find_eipmodules,
    _load_configio_rows,
    _load_eipmodules_rows,
    parse_eipcfg,
)
from fortna_rockwell_catalog import detect_rockwell_catalogs, first_catalog

STATUS_PROVEN = "PROVEN"
STATUS_DERIVED = "DERIVED"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_UNKNOWN = "UNKNOWN"

# Network device taxonomy — only remote I/O heads consume AREA_RIO_N
DEVICE_REMOTE_IO_RACK = "REMOTE_IO_RACK"
DEVICE_NETWORK_DRIVE = "NETWORK_DRIVE"
DEVICE_NETWORK_SCANNER = "NETWORK_SCANNER"
DEVICE_NETWORK_DEVICE = "NETWORK_DEVICE"
DEVICE_UNKNOWN = "UNKNOWN_NETWORK_DEVICE"

_RIO_HEAD_CATALOGS = {
    "1794-AENT",
    "1794-AENTR",
    "1734-AENT",
    "1734-AENTR",
    "1738-AENTR",
    "1738-AENTR/B",
}


def classify_network_device(catalog: str, family: str = "") -> str:
    """Classify Ethernet node by catalog/family — not name substring alone."""
    cat = (catalog or "").strip().upper().split("/")[0]
    fam = (family or "").strip().upper()
    if cat in {c.upper().split("/")[0] for c in _RIO_HEAD_CATALOGS} or (
        cat.endswith("-AENT") or cat.endswith("-AENTR")
    ):
        if cat.startswith(("1794", "1734", "1738")):
            return DEVICE_REMOTE_IO_RACK
    if "POWERFLEX" in cat or cat.startswith("PF") or "POWERFLEX" in fam:
        return DEVICE_NETWORK_DRIVE
    if "VU" in cat or "SCANNER" in cat:
        return DEVICE_NETWORK_SCANNER
    if cat:
        return DEVICE_NETWORK_DEVICE
    return DEVICE_UNKNOWN


def _canon(*parts: Any) -> str:
    raw = "|".join(str(p).strip().upper() for p in parts if str(p).strip() != "")
    return "hw_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _ip_key(ip: str) -> tuple:
    try:
        return (0, int(ipaddress.ip_address(ip)))
    except Exception:
        return (1, ip or "")


@dataclass
class RackModule:
    canonical_id: str
    physical_slot: int | None
    catalog_number: str
    hardware_family: str
    direction: str
    channel_capacity: int
    data_index: int | None
    input_bank: int | None = None
    output_bank: int | None = None
    source_names: list[str] = field(default_factory=list)
    status: str = STATUS_PROVEN  # overall (legacy)
    placement_status: str = STATUS_PROVEN
    bank_binding_status: str = STATUS_UNKNOWN
    catalog_status: str = STATUS_PROVEN
    evidence: list[dict[str, Any]] = field(default_factory=list)
    placement: str = "SLOTTED"  # SLOTTED | UNPLACED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RackInstance:
    canonical_adapter_id: str
    hardware_family: str
    catalog_number: str
    ip_address: str
    node: str
    source_aliases: list[str]
    provisional_display_name: str
    engineer_display_name: str = ""
    adapter_index: int | None = None
    device_class: str = DEVICE_REMOTE_IO_RACK
    modules: list[RackModule] = field(default_factory=list)
    unplaced_modules: list[RackModule] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = STATUS_PROVEN

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _sort_key_adapter(ad: dict[str, Any], idx: int) -> tuple:
    """Deterministic provisional rack order — never filesystem/dict accident."""
    # 1) topology source sequence (adapter_index if present)
    try:
        seq = int(ad.get("adapter_index")) if ad.get("adapter_index") is not None else idx
    except (TypeError, ValueError):
        seq = idx
    # 2) node if present
    try:
        node = int(ad.get("node")) if ad.get("node") is not None else 10**9
    except (TypeError, ValueError):
        node = 10**9
    # 3) IP numeric
    ipk = _ip_key(str(ad.get("targetip") or ""))
    # 4) stable source index
    # 5) canonical tie-break from name+ip
    name = str(ad.get("rio_name") or ad.get("name") or "")
    cid = _canon("ADAPTER", ad.get("targetip") or "", name, seq)
    return (seq, node, ipk, name.upper(), cid)


def discover_racks(run_dir: Path | str, machine: str) -> dict[str, Any]:
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    topo = parse_eipcfg(run_dir, machine)
    eipmods = _load_eipmodules_rows(run_dir, machine)
    configio = _load_configio_rows(run_dir, machine)
    hw = build_hardware_identity_model(run_dir, machine)

    # Index EIPModules by (norm adapter, slot)
    def _norm(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

    em_by_ad_slot: dict[tuple[str, int], dict[str, Any]] = {}
    for em in eipmods:
        try:
            slot = int(em.get("slot"))
        except (TypeError, ValueError):
            continue
        em_by_ad_slot[(_norm(str(em.get("adapter") or "")), slot)] = em

    adapters = list(topo.get("adapters") or [])
    ordered = sorted(
        enumerate(adapters),
        key=lambda iv: _sort_key_adapter(iv[1], iv[0]),
    )

    racks: list[RackInstance] = []
    other_network_devices: list[dict[str, Any]] = []
    catalog_hits: list[dict[str, Any]] = []
    rio_seq = 0

    # Scan Configio Desc for catalog signatures (type evidence only)
    for r in configio:
        for ev in detect_rockwell_catalogs(
            r.get("desc"),
            source_file="Configio.asc",
            source_table="Configio",
            source_row=r.get("row"),
            run_dir=run_dir,
        ):
            catalog_hits.append(ev.to_dict())

    for src_i, ad in ordered:
        rio = str(ad.get("rio_name") or ad.get("name") or "").strip()
        ip = str(ad.get("targetip") or "").strip()
        head_cat = ""
        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE" or "AENT" in str(
                m.get("type") or ""
            ).upper():
                head_cat = str(m.get("type") or m.get("catalog") or "")
                break
        if not head_cat:
            # Adapter-level catalog (e.g. PowerFlex drive nodes)
            head_cat = str(ad.get("type") or ad.get("name") or "")
            hit = first_catalog(head_cat, run_dir=run_dir)
            if hit:
                head_cat = hit.catalog_number
        fam = str(ad.get("family") or detect_family_from_catalog(head_cat) or "")
        device_class = classify_network_device(head_cat, fam)

        cid = None
        aliases: list[str] = []
        for ha in hw.get("adapters") or []:
            names = set(_norm(x) for x in (ha.get("aliases") or []) + (ha.get("source_names") or []))
            if _norm(rio) in names or (ip and ip == ha.get("ip_address")):
                cid = ha.get("canonical_id")
                aliases = list(ha.get("aliases") or [])
                break
        if not cid:
            cid = _canon("ADAPTER", machine, ip or rio, src_i)
        if rio and rio not in aliases:
            aliases = [rio] + aliases

        if device_class != DEVICE_REMOTE_IO_RACK:
            other_network_devices.append(
                {
                    "device_class": device_class,
                    "canonical_id": cid,
                    "catalog": head_cat,
                    "family": fam,
                    "ip": ip,
                    "aliases": aliases,
                    "adapter_index": src_i,
                }
            )
            continue

        rio_seq += 1
        provisional = f"AREA_RIO_{rio_seq}"
        rack = RackInstance(
            canonical_adapter_id=cid,
            hardware_family=fam,
            catalog_number=head_cat,
            ip_address=ip,
            node=str(ad.get("node") or ""),
            source_aliases=aliases,
            provisional_display_name=provisional,
            engineer_display_name="",
            adapter_index=src_i,
            device_class=DEVICE_REMOTE_IO_RACK,
            evidence=[
                {
                    "source": "eipcfg_xml",
                    "ref": str(_find_eipcfg(run_dir, machine) or ""),
                    "fact": f"adapter={rio} ip={ip} index={src_i} class={DEVICE_REMOTE_IO_RACK}",
                }
            ],
            status=STATUS_PROVEN if ip and head_cat else STATUS_DERIVED,
        )

        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE":
                continue
            cat = str(m.get("type") or m.get("catalog") or "").strip()
            try:
                slot = int(m.get("slot"))
            except (TypeError, ValueError):
                slot = None
            try:
                di = int(m.get("data_index")) if m.get("data_index") is not None else None
            except (TypeError, ValueError):
                di = None
            direction = str(m.get("direction") or "")
            ib = ob = None
            bank_binding = STATUS_UNKNOWN
            placement_status = STATUS_PROVEN if slot is not None else STATUS_REVIEW
            catalog_status = STATUS_PROVEN if cat else STATUS_UNKNOWN
            # Corroborate banks from EIPModules
            em = None
            bank_join = "none"
            if slot is not None:
                candidates = [_norm(rio), _norm(str(ad.get("name") or ""))]
                for key in ((c, slot) for c in candidates if c):
                    if key in em_by_ad_slot:
                        em = em_by_ad_slot[key]
                        bank_join = "exact_alias"
                        break
                if em is None:
                    # Soft/substring match — evidence only; NOT PROVEN bank authority
                    for (ead, eslot), row in em_by_ad_slot.items():
                        if eslot != slot:
                            continue
                        for c in candidates:
                            if c and (c in ead or ead in c):
                                em = row
                                bank_join = "substring_name"
                                break
                        if em is not None:
                            break
            if em:
                try:
                    ib = int(em.get("input_bank")) if em.get("input_bank") is not None else None
                except (TypeError, ValueError):
                    ib = None
                try:
                    ob = int(em.get("output_bank")) if em.get("output_bank") is not None else None
                except (TypeError, ValueError):
                    ob = None
                em_type = str(em.get("type") or "")
                if em_type and cat and em_type.upper() != cat.upper():
                    status = STATUS_REVIEW
                    bank_binding = STATUS_REVIEW
                elif bank_join == "exact_alias":
                    status = STATUS_PROVEN
                    bank_binding = STATUS_PROVEN
                    if not cat:
                        cat = em_type
                else:
                    # substring-only join → DERIVED banks, not PROVEN
                    status = STATUS_DERIVED
                    bank_binding = STATUS_DERIVED
                    if not cat:
                        cat = em_type
            else:
                status = STATUS_PROVEN if cat and slot is not None else STATUS_REVIEW
                bank_join = "eipcfg_slot_only"
                bank_binding = STATUS_UNKNOWN
            placement_status = STATUS_PROVEN if slot is not None else STATUS_REVIEW
            catalog_status = STATUS_PROVEN if cat else STATUS_UNKNOWN

            # Also attach banks from module itself if present
            if ib is None:
                try:
                    ib = int(m.get("input_bank")) if m.get("input_bank") is not None else None
                except (TypeError, ValueError):
                    ib = None
            if ob is None:
                try:
                    ob = int(m.get("output_bank")) if m.get("output_bank") is not None else None
                except (TypeError, ValueError):
                    ob = None

            mod = RackModule(
                canonical_id=_canon("MODULE", cid, slot if slot is not None else "?", cat),
                physical_slot=slot,
                catalog_number=cat,
                hardware_family=detect_family_from_catalog(cat) or fam,
                direction=direction,
                channel_capacity=channel_capacity_for_catalog(cat),
                data_index=di,
                input_bank=ib,
                output_bank=ob,
                source_names=[str(m.get("name") or "").strip()] if m.get("name") else [],
                status=status,
                placement_status=placement_status,
                bank_binding_status=bank_binding,
                catalog_status=catalog_status,
                evidence=[
                    {
                        "source": "eipcfg_xml",
                        "ref": f"{rio}.slot{slot}",
                        "fact": f"type={cat} slot={slot} data_index={di}",
                    },
                    {
                        "source": "bank_join",
                        "ref": bank_join,
                        "fact": (
                            f"bank_join={bank_join} status={status} "
                            f"ib={ib} ob={ob}"
                        ),
                    },
                ]
                + (
                    [
                        {
                            "source": "eipmodules",
                            "ref": f"adapter={em.get('adapter')} slot={em.get('slot')}",
                            "fact": f"type={em.get('type')} ib={ib} ob={ob}",
                        }
                    ]
                    if em
                    else []
                ),
                placement="SLOTTED" if slot is not None else "UNPLACED",
            )
            if slot is None:
                rack.unplaced_modules.append(mod)
            else:
                rack.modules.append(mod)

        rack.modules.sort(key=lambda x: (x.physical_slot is None, x.physical_slot or 0))
        racks.append(rack)

    # Numeric suffix analysis on Configio Desc catalog hits
    suffix_analysis = analyze_numeric_suffixes(catalog_hits, eipmods, configio, racks)

    return {
        "kind": "rack_discovery",
        "version": 1,
        "machine": machine,
        "run_dir": str(run_dir),
        "racks": [r.to_dict() for r in racks],
        "other_network_devices": other_network_devices,
        "provisional_order_rule": (
            "REMOTE_IO_RACK only: adapter_index → node → IP numeric → name → canonical_id"
        ),
        "display_identity_note": (
            "provisional_display_name / engineer_display_name never change canonical_id, "
            "slots, banks, or compiler relationships"
        ),
        "configio_catalog_signatures": catalog_hits[:80],
        "configio_catalog_signature_count": len(catalog_hits),
        "numeric_suffix_analysis": suffix_analysis,
        "stats": {
            "rack_count": len(racks),
            "slotted_modules": sum(len(r.modules) for r in racks),
            "unplaced_modules": sum(len(r.unplaced_modules) for r in racks),
            "other_network_devices": len(other_network_devices),
        },
    }


def analyze_numeric_suffixes(
    catalog_hits: list[dict[str, Any]],
    eipmods: list[dict[str, Any]],
    configio: list[dict[str, Any]],
    racks: list[RackInstance],
) -> dict[str, Any]:
    """Statistical/deterministic probe of trailing -N after catalog in Desc."""
    samples = []
    for hit in catalog_hits:
        trail = str(hit.get("trailing_text") or "")
        m = re.search(r"(\d+)$", trail.replace("-", " ").replace("_", " "))
        if not m:
            continue
        suffix = int(m.group(1))
        row = hit.get("source_row")
        cfg = next((c for c in configio if c.get("row") == row), None)
        bank = None
        try:
            bank = int(cfg.get("bank")) if cfg and cfg.get("bank") is not None else None
        except (TypeError, ValueError):
            bank = None
        # Compare to EIPModules slots with same catalog
        cat = hit.get("catalog_number") or ""
        matching_slots = [
            int(em.get("slot"))
            for em in eipmods
            if str(em.get("type") or "").upper() == cat.upper()
            and em.get("slot") is not None
        ]
        samples.append(
            {
                "raw_text": hit.get("raw_text"),
                "catalog": cat,
                "suffix": suffix,
                "configio_bank": bank,
                "matching_eip_slots_same_catalog": sorted(set(matching_slots))[:12],
                "suffix_equals_any_slot": suffix in matching_slots,
                "suffix_equals_bank": bank is not None and suffix == bank,
            }
        )

    n = len(samples) or 1
    eq_slot = sum(1 for s in samples if s["suffix_equals_any_slot"])
    eq_bank = sum(1 for s in samples if s["suffix_equals_bank"])
    # Restart at adapter? check if suffixes reset near adapter boundaries — weak probe
    return {
        "sample_count": len(samples),
        "suffix_equals_eip_slot_count": eq_slot,
        "suffix_equals_eip_slot_rate": round(eq_slot / n, 3),
        "suffix_equals_configio_bank_count": eq_bank,
        "suffix_equals_configio_bank_rate": round(eq_bank / n, 3),
        "conclusion": (
            "UNKNOWN"
            if eq_slot / n < 0.8 and eq_bank / n < 0.8
            else (
                "CORRELATES_WITH_SLOT"
                if eq_slot / n >= 0.8
                else "CORRELATES_WITH_BANK"
                if eq_bank / n >= 0.8
                else "UNKNOWN"
            )
        ),
        "note": (
            "Trailing -N after catalog is NEVER auto-promoted to physical_slot. "
            "Conclusion is evidence correlation only."
        ),
        "samples": samples[:40],
    }


def rename_rack_display(
    discovery: dict[str, Any],
    canonical_adapter_id: str,
    engineer_display_name: str,
) -> dict[str, Any]:
    """Rename display only — identity/topology unchanged."""
    out = json.loads(json.dumps(discovery))
    for r in out.get("racks") or []:
        if r.get("canonical_adapter_id") == canonical_adapter_id:
            r["engineer_display_name"] = engineer_display_name
            # Prove immutable fields untouched by returning copies of keys
            r["_display_rename_only"] = True
    return out
