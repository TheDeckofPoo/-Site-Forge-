"""Deterministic Hunter pipeline (read-only).

 1 enumerate PDFs  2 sha256  3 pages  4 native words  5 coordinates
 6 title block / sheet metadata  7 device-token candidates  8 context
 9 family  10 printed I/O / terminals  11 explicit relationships
 12 continuation / cross-refs  13 evidence  14 review queue  15 summary
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from . import EXTRACTOR_VERSION, HUNTER_VERSION
from .device_candidates import extract_page_candidates, failure_record
from .device_grammar import normalize_label
from .evidence_records import sort_key
from .export import OUTPUT_FILES, build_summary, write_outputs
from .pdf_reader import enumerate_pdfs, read_document
from .relationship_candidates import extract_line_relationships
from .review_queue import build_review_queue, label_observations
from .sheet_index import detect_sheet
from .text_blocks import build_lines


def run_hunter(input_path: Path, out_dir: Path, project: Optional[str] = None,
               controller: Optional[str] = None, generated_at: Optional[str] = None) -> Dict:
    input_path = Path(input_path)
    pdfs = enumerate_pdfs(input_path)
    records, sheets, documents = [], [], []
    for rel, path in pdfs:
        doc = read_document(rel, path)
        documents.append({
            "source_document": rel, "sha256": doc.sha256, "size_bytes": doc.size_bytes,
            "page_count": len(doc.pages), "read_status": "ERROR" if doc.read_error else "OK",
            "read_error": doc.read_error,
        })
        if doc.read_error:
            records.append(failure_record(doc, None, "DOCUMENT_READ_ERROR",
                                          f"DOCUMENT_READ_ERROR: {doc.read_error}", project, controller))
        for page in doc.pages:
            lines = build_lines(page) if page.has_text_layer else []
            info = detect_sheet(rel, page, lines)
            sj = info.to_json()
            sj["warnings"] = list(page.warnings)
            sj["image_count"] = page.image_count
            sj["word_count"] = len(page.words)
            sj["page_size"] = {"width": page.width, "height": page.height}
            sheets.append(sj)
            if not page.has_text_layer:
                records.append(failure_record(doc, page, "TEXT_LAYER_MISSING", page.warnings[-1],
                                              project, controller, info))
                continue
            records.extend(extract_page_candidates(doc, page, lines, info, project, controller))
            records.extend(extract_line_relationships(doc, page, lines, info, project, controller))

    # cross-reference targets that are not in the input set -> note (+ review)
    known = {normalize_label(s["sheet_number"]) for s in sheets if s.get("sheet_number")}
    for r in records:
        if r.evidence_type == "CONTINUATION_REFERENCE":
            if normalize_label(r.continuation_reference or "") in known:
                r.notes.append("target sheet present in input set")
            else:
                r.notes.append("target sheet not in input set")

    # de-duplicate identical evidence ids (same thing seen twice) deterministically
    uniq = {}
    for r in sorted(records, key=sort_key):
        uniq.setdefault(r.evidence_id, r)
    records = sorted(uniq.values(), key=sort_key)
    sheets.sort(key=lambda s: (s["source_document"], s["page_number"]))

    observations = label_observations(records)
    review = build_review_queue(records, sheets, observations)
    summary = build_summary(records, sheets, observations, review, documents)
    fingerprint = hashlib.sha256("\n".join(r.evidence_id for r in records).encode()).hexdigest()
    manifest = {
        "tool": "HUNTER",
        "hunter_version": HUNTER_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project": project,
        "controller_scope_hint": controller,
        "controller_scope_hint_usage": "metadata only; never used to assign devices to a controller",
        "input_path": str(input_path),
        "input_mode": "file" if input_path.is_file() else "directory",
        "inputs": documents,
        "outputs": list(OUTPUT_FILES),
        "read_only": True,
        "ocr_enabled": False,
        "llm_used": False,
        "authority": "EVIDENCE_ONLY",
        "allowed_states": ["PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN"],
        "evidence_count": len(records),
        "evidence_fingerprint": fingerprint,
    }
    paths = write_outputs(Path(out_dir), manifest, records, sheets, summary, review)
    return {"manifest": manifest, "records": records, "sheets": sheets, "summary": summary,
            "review_queue": review, "paths": paths}
