"""Cluster UNKNOWN Configio dialects / decode failures by enriched signatures.

Site-independent: no site/controller names in cluster identity.
Improves on empty PHYSICAL_RESOLUTION_FAILURE collapse by hashing structural
pattern + learning-signature fields.
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fortna_learning_signatures import (  # noqa: E402
    LEARNING_SIGNATURE_FIELDS,
    build_learning_signature,
)

from .classify_configio_dialect import structural_pattern_hash  # noqa: E402
from .corpus_models import FORM_UNKNOWN, DialectHit, UnknownCluster  # noqa: E402


def _norm(v: Any) -> str:
    return str(v or "").strip().upper()


def enriched_unknown_dims(
    hit: DialectHit | dict[str, Any],
    *,
    hardware_family: str = "",
    adapter_family: str = "",
    network_device_class: str = "",
    interface: str = "",
    lohi_shape: str = "",
    direction_evidence_class: str = "",
    bank_relationship_class: str = "",
    catalog_authority_status: str = "",
    hardware_topology_status: str = "",
    adapter_identity_status: str = "",
    failure_stage: str = "CONFIGIO_DIALECT",
    failure_reason: str = "UNKNOWN_CONFIGIO_FORM",
    subsystem: str = "IO",
) -> dict[str, Any]:
    """Derive site-independent clustering dimensions for one unknown hit."""
    if isinstance(hit, DialectHit):
        raw = hit.raw_example
        form = hit.configio_form
        catalog = hit.catalog
        evidence = dict(hit.evidence or {})
    else:
        raw = str(hit.get("raw_example") or hit.get("raw") or hit.get("desc") or "")
        form = str(hit.get("configio_form") or hit.get("form") or FORM_UNKNOWN)
        catalog = str(hit.get("catalog") or "")
        evidence = dict(hit.get("evidence") or {})

    sph = str(evidence.get("structural_pattern_hash") or structural_pattern_hash(raw))
    cat_sig = _norm(catalog) or _norm(
        (evidence.get("catalog_signature") or {}).get("catalog_number")
        if isinstance(evidence.get("catalog_signature"), dict)
        else evidence.get("catalog_signature")
    )

    sig = build_learning_signature(
        subsystem=subsystem,
        hardware_family=hardware_family,
        adapter_family=adapter_family,
        network_device_class=network_device_class,
        configio_form=form,
        catalog_signature=cat_sig,
        catalog_authority_status=catalog_authority_status,
        direction_evidence_class=direction_evidence_class,
        lohi_shape=lohi_shape,
        bank_relationship_class=bank_relationship_class,
        interface=interface,
        hardware_topology_status=hardware_topology_status,
        adapter_identity_status=adapter_identity_status,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
    )
    # Cluster key = signature + structural pattern (shape), never site names
    cluster_raw = f"{sig['signature_id']}|{sph}"
    cluster_id = "uc_" + hashlib.sha1(cluster_raw.encode("utf-8")).hexdigest()[:12]
    return {
        "cluster_id": cluster_id,
        "pattern_hash": sph,
        "signature_id": sig["signature_id"],
        "structural_pattern": sph,
        "signature": sig,
        "raw": raw,
        "configio_form": form,
        "catalog_signature": cat_sig,
    }


def cluster_unknown_dialects(
    hits: list[DialectHit | dict[str, Any]],
    *,
    default_meta: dict[str, Any] | None = None,
) -> list[UnknownCluster]:
    """Group UNKNOWN dialect hits into site-independent clusters."""
    meta = dict(default_meta or {})
    buckets: dict[str, dict[str, Any]] = {}
    for hit in hits or []:
        form = (
            hit.configio_form
            if isinstance(hit, DialectHit)
            else str(hit.get("configio_form") or "")
        )
        if form and form != FORM_UNKNOWN:
            continue
        dims = enriched_unknown_dims(
            hit,
            hardware_family=str(meta.get("hardware_family") or ""),
            adapter_family=str(meta.get("adapter_family") or ""),
            network_device_class=str(meta.get("network_device_class") or ""),
            interface=str(meta.get("interface") or ""),
            lohi_shape=str(meta.get("lohi_shape") or ""),
            direction_evidence_class=str(meta.get("direction_evidence_class") or ""),
            bank_relationship_class=str(meta.get("bank_relationship_class") or ""),
            catalog_authority_status=str(meta.get("catalog_authority_status") or ""),
            hardware_topology_status=str(meta.get("hardware_topology_status") or ""),
            adapter_identity_status=str(meta.get("adapter_identity_status") or ""),
            failure_stage=str(meta.get("failure_stage") or "CONFIGIO_DIALECT"),
            failure_reason=str(meta.get("failure_reason") or "UNKNOWN_CONFIGIO_FORM"),
            subsystem=str(meta.get("subsystem") or "IO"),
        )
        cid = dims["cluster_id"]
        archive = ""
        machine = ""
        count = 1
        if isinstance(hit, DialectHit):
            archive = hit.archive_sha256
            machine = hit.machine
            count = int(hit.count or 1)
            raw = hit.raw_example
        else:
            archive = str(hit.get("archive_sha256") or "")
            machine = str(hit.get("machine") or "")
            count = int(hit.get("count") or 1)
            raw = dims["raw"]

        b = buckets.get(cid)
        if not b:
            fields = {
                k: dims["signature"].get(k) or ""
                for k in LEARNING_SIGNATURE_FIELDS
            }
            fields["structural_pattern_hash"] = dims["pattern_hash"]
            b = {
                "cluster_id": cid,
                "pattern_hash": dims["pattern_hash"],
                "signature_id": dims["signature_id"],
                "structural_pattern": dims["structural_pattern"],
                "example_raw": [],
                "count": 0,
                "fields": fields,
                "archives": [],
                "machines": [],
            }
            buckets[cid] = b
        b["count"] += count
        if raw and raw not in b["example_raw"]:
            b["example_raw"].append(raw)
        if archive:
            b["archives"].append(archive)
        if machine:
            # stored for inventory only — NOT part of cluster identity
            b["machines"].append(machine)

    clusters = [
        UnknownCluster(
            cluster_id=v["cluster_id"],
            pattern_hash=v["pattern_hash"],
            signature_id=v["signature_id"],
            structural_pattern=v["structural_pattern"],
            example_raw=v["example_raw"],
            count=v["count"],
            fields=v["fields"],
            archives=v["archives"],
            machines=v["machines"],
        )
        for v in buckets.values()
    ]
    return sorted(clusters, key=lambda c: (-c.count, c.cluster_id))


def cluster_failure_records(records: list[dict[str, Any]]) -> list[UnknownCluster]:
    """Cluster generic failure dicts that already carry learning-signature fields."""
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "example_raw": [],
            "count": 0,
            "fields": {},
            "archives": [],
            "machines": [],
            "signature_id": "",
            "pattern_hash": "",
        }
    )
    for rec in records or []:
        sig = build_learning_signature(
            **{k: rec.get(k) or "" for k in LEARNING_SIGNATURE_FIELDS}
        )
        raw = str(rec.get("raw") or rec.get("desc") or rec.get("example") or "")
        sph = str(rec.get("structural_pattern_hash") or structural_pattern_hash(raw))
        cid = "uc_" + hashlib.sha1(
            f"{sig['signature_id']}|{sph}".encode("utf-8")
        ).hexdigest()[:12]
        b = buckets[cid]
        b["signature_id"] = sig["signature_id"]
        b["pattern_hash"] = sph
        b["fields"] = {k: sig.get(k) or "" for k in LEARNING_SIGNATURE_FIELDS}
        b["fields"]["structural_pattern_hash"] = sph
        b["count"] += int(rec.get("count") or 1)
        if raw and raw not in b["example_raw"]:
            b["example_raw"].append(raw)
        if rec.get("archive_sha256"):
            b["archives"].append(str(rec["archive_sha256"]))
        if rec.get("machine"):
            b["machines"].append(str(rec["machine"]))

    out = [
        UnknownCluster(
            cluster_id=cid,
            pattern_hash=v["pattern_hash"],
            signature_id=v["signature_id"],
            structural_pattern=v["pattern_hash"],
            example_raw=v["example_raw"],
            count=v["count"],
            fields=v["fields"],
            archives=v["archives"],
            machines=v["machines"],
        )
        for cid, v in buckets.items()
    ]
    return sorted(out, key=lambda c: (-c.count, c.cluster_id))
