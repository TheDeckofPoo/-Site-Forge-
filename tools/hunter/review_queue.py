"""Review queue + duplicate/raw-label observations.

The review queue is where Hunter admits what the print does not prove.
Raw labels are NEVER merged: label variants that normalize alike are
reported as observations and queued as possible conflicts.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Dict, List

from .device_grammar import normalize_label
from .evidence_records import EvidenceRecord

CATEGORIES = (
    "DOCUMENT_READ_ERROR",
    "TEXT_LAYER_MISSING",
    "MISSING_TITLE_BLOCK",
    "POSSIBLE_CONFLICTING_LABELS",
    "AMBIGUOUS_TYPE",
    "UNRECOGNIZED_DEVICE_TOKEN",
    "WEAK_RELATIONSHIP",
    "CONTINUATION_TARGET_NOT_IN_INPUT_SET",
)
_ORDER = {c: i for i, c in enumerate(CATEGORIES)}
PRIORITY = {
    "DOCUMENT_READ_ERROR": "HIGH",
    "TEXT_LAYER_MISSING": "HIGH",
    "MISSING_TITLE_BLOCK": "MEDIUM",
    "POSSIBLE_CONFLICTING_LABELS": "MEDIUM",
    "AMBIGUOUS_TYPE": "MEDIUM",
    "UNRECOGNIZED_DEVICE_TOKEN": "MEDIUM",
    "WEAK_RELATIONSHIP": "LOW",
    "CONTINUATION_TARGET_NOT_IN_INPUT_SET": "LOW",
}
LABEL_TYPES = ("DEVICE_LABEL", "AMBIGUOUS_DEVICE_TOKEN", "UNKNOWN_DEVICE_TOKEN")


def _item(category: str, reason: str, *, source_document=None, page_number=None, sheet_number=None,
          raw_text=None, raw_device_label=None, evidence_ids=(), bbox=None, extra=None) -> Dict:
    ids = sorted(evidence_ids)
    key = "|".join([category, str(source_document), str(page_number), str(raw_device_label), ",".join(ids), reason])
    d = {
        "review_id": "HR-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
        "category": category,
        "priority": PRIORITY[category],
        "reason": reason,
        "source_document": source_document,
        "page_number": page_number,
        "sheet_number": sheet_number,
        "raw_text": raw_text,
        "raw_device_label": raw_device_label,
        "evidence_ids": ids,
        "bbox": bbox,
    }
    if extra:
        d.update(extra)
    return d


def label_observations(records: List[EvidenceRecord]) -> List[Dict]:
    groups: Dict[str, List[EvidenceRecord]] = defaultdict(list)
    for r in records:
        if r.evidence_type in LABEL_TYPES and r.raw_device_label:
            groups[normalize_label(r.raw_device_label)].append(r)
    obs = []
    for norm in sorted(groups):
        rs = groups[norm]
        raws = sorted({r.raw_device_label for r in rs})
        places = sorted({(r.source_document, r.page_number) for r in rs})
        occ = [
            {"source_document": r.source_document, "page_number": r.page_number, "sheet_number": r.sheet_number,
             "raw_device_label": r.raw_device_label, "evidence_id": r.evidence_id}
            for r in sorted(rs, key=lambda r: (r.source_document, r.page_number, r.evidence_id))
        ]
        if len(raws) > 1:
            obs.append({"kind": "RAW_LABEL_VARIANTS", "normalized_name_candidate": norm, "raw_labels": raws,
                        "occurrence_count": len(rs), "occurrences": occ,
                        "note": "raw labels normalize alike; NOT merged — human must confirm same device"})
        elif len(places) > 1:
            obs.append({"kind": "MULTI_SHEET_OCCURRENCE", "normalized_name_candidate": norm, "raw_labels": raws,
                        "occurrence_count": len(rs), "occurrences": occ,
                        "note": "same raw label printed on several pages/sheets; each occurrence kept as its own evidence"})
        elif len(rs) > 1:
            obs.append({"kind": "REPEATED_ON_PAGE", "normalized_name_candidate": norm, "raw_labels": raws,
                        "occurrence_count": len(rs), "occurrences": occ,
                        "note": "same raw label printed more than once on one page"})
    return obs


def build_review_queue(records: List[EvidenceRecord], sheets: List[Dict], observations: List[Dict]) -> List[Dict]:
    q: List[Dict] = []
    for r in records:
        base = dict(source_document=r.source_document, page_number=r.page_number, sheet_number=r.sheet_number,
                    raw_text=r.raw_text, raw_device_label=r.raw_device_label, evidence_ids=[r.evidence_id], bbox=r.bbox)
        if r.evidence_type == "DOCUMENT_READ_ERROR":
            q.append(_item("DOCUMENT_READ_ERROR", "; ".join(r.notes), **base))
        elif r.evidence_type == "TEXT_LAYER_MISSING":
            q.append(_item("TEXT_LAYER_MISSING", "; ".join(r.notes), **base))
        elif r.evidence_type == "AMBIGUOUS_DEVICE_TOKEN":
            q.append(_item("AMBIGUOUS_TYPE", "; ".join(r.notes), **base))
        elif r.evidence_type == "UNKNOWN_DEVICE_TOKEN":
            q.append(_item("UNRECOGNIZED_DEVICE_TOKEN", "device-like token not classified; kept as UNKNOWN", **base))
        elif r.evidence_type == "RELATIONSHIP" and r.state != "PROVEN":
            q.append(_item("WEAK_RELATIONSHIP", f"{r.relationship_kind} ({r.state}): " + "; ".join(r.notes[:1]), **base,
                           extra={"related_text": r.related_device_text or r.physical_address_text or r.module_or_terminal_text}))
        elif r.evidence_type == "CONTINUATION_REFERENCE" and any("not in input set" in n for n in r.notes):
            q.append(_item("CONTINUATION_TARGET_NOT_IN_INPUT_SET",
                           f"cross-reference target '{r.continuation_reference}' not found among input sheets", **base))
    for s in sheets:
        if s.get("has_text_layer") and s.get("missing_fields"):
            q.append(_item("MISSING_TITLE_BLOCK",
                           "missing printed title-block fields: " + ", ".join(s["missing_fields"]),
                           source_document=s["source_document"], page_number=s["page_number"],
                           sheet_number=s.get("sheet_number"),
                           raw_text=" | ".join(x["text"] for x in s.get("source_lines", [])) or None))
    for o in observations:
        if o["kind"] == "RAW_LABEL_VARIANTS":
            first = o["occurrences"][0]
            q.append(_item("POSSIBLE_CONFLICTING_LABELS",
                           f"raw labels {o['raw_labels']} normalize to candidate '{o['normalized_name_candidate']}'; not merged",
                           source_document=first["source_document"], page_number=first["page_number"],
                           sheet_number=first["sheet_number"], raw_device_label=" | ".join(o["raw_labels"]),
                           evidence_ids=[x["evidence_id"] for x in o["occurrences"]]))
    q.sort(key=lambda d: (_ORDER[d["category"]], str(d["source_document"]), d["page_number"] or 0,
                          str(d["raw_device_label"]), d["review_id"]))
    return q
