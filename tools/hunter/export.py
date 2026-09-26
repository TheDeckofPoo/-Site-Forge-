"""Deterministic writers for Hunter outputs (stable ordering, sorted keys)."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

from . import ALLOWED_STATES
from .evidence_records import EvidenceRecord

OUTPUT_FILES = (
    "hunter_manifest.json",
    "hunter_evidence.jsonl",
    "hunter_device_index.csv",
    "hunter_summary.json",
    "hunter_review_queue.json",
    "hunter_sheet_index.json",
)
CSV_COLUMNS = (
    "raw_label", "normalized_candidate", "type", "state", "sheet", "page", "panel",
    "printed_io", "confidence", "notes", "source_document", "evidence_id",
)
LABEL_TYPES = ("DEVICE_LABEL", "AMBIGUOUS_DEVICE_TOKEN", "UNKNOWN_DEVICE_TOKEN")


def dump_json(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def evidence_jsonl(records: List[EvidenceRecord]) -> str:
    return "".join(json.dumps(r.to_json(), sort_keys=True, ensure_ascii=False) + "\n" for r in records)


def device_index_csv(records: List[EvidenceRecord]) -> str:
    rels: Dict[tuple, List[EvidenceRecord]] = {}
    for r in records:
        if r.evidence_type == "RELATIONSHIP" and r.state in ("PROVEN", "DERIVED") and r.raw_device_label:
            rels.setdefault((r.source_document, r.page_number, r.raw_device_label), []).append(r)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for r in records:
        if r.evidence_type not in LABEL_TYPES:
            continue
        linked = rels.get((r.source_document, r.page_number, r.raw_device_label), [])
        io_txt = sorted({f"{x.physical_address_text or x.module_or_terminal_text} [{x.state}]"
                         for x in linked if (x.physical_address_text or x.module_or_terminal_text)})
        panels = sorted({x.panel_or_rack_text for x in linked if x.panel_or_rack_text})
        w.writerow([
            r.raw_device_label, r.normalized_name_candidate or "", r.entity_type_candidate or "", r.state,
            r.sheet_number or "", r.page_number, " | ".join(panels), " ; ".join(io_txt),
            f"{r.confidence:.3f}", " ; ".join(r.notes), r.source_document, r.evidence_id,
        ])
    return buf.getvalue()


def build_summary(records: List[EvidenceRecord], sheets: List[Dict], observations: List[Dict],
                  review_queue: List[Dict], documents: List[Dict]) -> Dict:
    labels = [r for r in records if r.evidence_type in LABEL_TYPES]
    by_page = Counter(f"{r.source_document}#p{r.page_number}" for r in records)
    by_sheet = Counter(r.sheet_number or "(no sheet number)" for r in records)
    warn_pages = sorted(
        (
            {"source_document": s["source_document"], "page_number": s["page_number"],
             "warnings": sorted(set(s.get("warnings", [])) | ({"MISSING_TITLE_FIELDS: " + ", ".join(s["missing_fields"])}
                                                          if s.get("missing_fields") else set()))}
            for s in sheets if s.get("warnings") or s.get("missing_fields")
        ),
        key=lambda d: (d["source_document"], d["page_number"]),
    )
    return {
        "authority": "EVIDENCE_ONLY — Hunter is an evidence extractor, not an engineering authority",
        "state_semantics": {
            "PROVEN": "explicitly supported by the print text only (not RUN, not field, not PLC-ready)",
            "DERIVED": "nominated by naming grammar or layout; not explicitly stated by the print",
            "REVIEW_REQUIRED": "ambiguous, conflicting, weak or incomplete; human review needed",
            "UNKNOWN": "device-like text Hunter could not classify; conserved, not dropped",
        },
        "document_count": len(documents),
        "page_count": sum(d.get("page_count") or 0 for d in documents),
        "evidence_count": len(records),
        "device_label_observation_count": len(labels),
        "counts_by_family": dict(sorted(Counter(r.entity_type_candidate for r in labels).items())),
        "counts_by_state": {s: sum(1 for r in records if r.state == s) for s in ALLOWED_STATES},
        "label_counts_by_state": {s: sum(1 for r in labels if r.state == s) for s in ALLOWED_STATES},
        "counts_by_evidence_type": dict(sorted(Counter(r.evidence_type for r in records).items())),
        "counts_by_page": dict(sorted(by_page.items())),
        "counts_by_sheet": dict(sorted(by_sheet.items())),
        "unknown_token_count": sum(1 for r in records if r.evidence_type == "UNKNOWN_DEVICE_TOKEN"),
        "ambiguous_token_count": sum(1 for r in records if r.evidence_type == "AMBIGUOUS_DEVICE_TOKEN"),
        "pages_with_extraction_warnings": warn_pages,
        "duplicate_raw_label_observations": observations,
        "review_queue_count": len(review_queue),
        "review_queue_counts_by_category": dict(sorted(Counter(q["category"] for q in review_queue).items())),
    }


def write_outputs(out_dir: Path, manifest: Dict, records: List[EvidenceRecord], sheets: List[Dict],
                  summary: Dict, review_queue: List[Dict]) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "hunter_evidence.jsonl": evidence_jsonl(records),
        "hunter_device_index.csv": device_index_csv(records),
        "hunter_summary.json": dump_json(summary),
        "hunter_review_queue.json": dump_json({"review_queue": review_queue}),
        "hunter_sheet_index.json": dump_json({"sheets": sheets}),
        "hunter_manifest.json": dump_json(manifest),
    }
    paths = {}
    for name in OUTPUT_FILES:
        p = out_dir / name
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(payloads[name])
        paths[name] = p
    return paths
