"""EvidenceRecord — the Hunter evidence contract.

State semantics (the ONLY allowed states):
  PROVEN          the PRINT ITSELF explicitly shows it (literal printed text,
                  e.g. a label printed next to its own descriptive text, a
                  printed I/O address, a printed "A -> B" link).  PROVEN is
                  print-proven ONLY: not RUN-proven, not field-verified, not
                  PLC-ready, not an engineering decision.
  DERIVED         nominated by grammar / layout (naming pattern, same printed
                  row) but not explicitly stated by the print.
  REVIEW_REQUIRED ambiguous, conflicting, weak or incomplete; a human must look.
  UNKNOWN         device-like text Hunter cannot classify.  Kept, never dropped.

Hunter never emits ENGINEER_ASSIGNED or any other authority state.

Provenance law: every record carries source_document, source_document_hash,
page_number and raw_text (the exact printed line).  The only records whose
raw_text may be empty are extraction failures (TEXT_LAYER_MISSING,
DOCUMENT_READ_ERROR), which explain themselves in ``notes``.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from . import ALLOWED_STATES, EXTRACTOR_VERSION

EVIDENCE_TYPES = (
    "DOCUMENT_READ_ERROR",
    "TEXT_LAYER_MISSING",
    "SHEET_METADATA",
    "DEVICE_LABEL",
    "AMBIGUOUS_DEVICE_TOKEN",
    "UNKNOWN_DEVICE_TOKEN",
    "IO_MODULE_REFERENCE",
    "IO_REFERENCE",
    "TERMINAL_REFERENCE",
    "NETWORK_REFERENCE",
    "CONTINUATION_REFERENCE",
    "RELATIONSHIP",
)
_TYPE_ORDER = {t: i for i, t in enumerate(EVIDENCE_TYPES)}
EXTRACTION_FAILURE_TYPES = frozenset({"DOCUMENT_READ_ERROR", "TEXT_LAYER_MISSING"})


@dataclass
class EvidenceRecord:
    project: Optional[str]
    controller_scope_hint: Optional[str]
    source_document: str
    source_document_hash: str
    page_number: int
    evidence_type: str
    raw_text: str
    state: str
    confidence: float
    sheet_number: Optional[str] = None
    sheet_title: Optional[str] = None
    drawing_revision: Optional[str] = None
    raw_device_label: Optional[str] = None
    normalized_name_candidate: Optional[str] = None
    entity_type_candidate: Optional[str] = None
    grammar_rule: Optional[str] = None
    physical_address_text: Optional[str] = None
    panel_or_rack_text: Optional[str] = None
    module_or_terminal_text: Optional[str] = None
    related_device_text: Optional[str] = None
    relationship_kind: Optional[str] = None
    continuation_reference: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None
    page_size: Optional[Dict[str, float]] = None
    context_text: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    extractor_version: str = EXTRACTOR_VERSION
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.state not in ALLOWED_STATES:
            raise ValueError(f"illegal Hunter state {self.state!r}; allowed: {ALLOWED_STATES}")
        if self.evidence_type not in _TYPE_ORDER:
            raise ValueError(f"unknown evidence_type {self.evidence_type!r}")
        if not self.source_document or not self.source_document_hash:
            raise ValueError("provenance law: source_document and hash are required")
        if self.evidence_type not in EXTRACTION_FAILURE_TYPES:
            if not self.raw_text or self.page_number < 1:
                raise ValueError("provenance law: page_number and raw_text are required")
        elif not self.notes:
            raise ValueError("extraction-failure records must explain themselves in notes")
        self.confidence = round(float(self.confidence), 3)
        if not self.evidence_id:
            self.evidence_id = make_evidence_id(self)

    def to_json(self) -> Dict:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


def make_evidence_id(r: EvidenceRecord) -> str:
    b = r.bbox or {}
    parts = [
        r.source_document_hash,
        str(r.page_number),
        r.evidence_type,
        r.raw_device_label or "",
        r.related_device_text or "",
        r.physical_address_text or "",
        r.module_or_terminal_text or "",
        r.continuation_reference or "",
        r.relationship_kind or "",
        f"{float(b.get('x0', 0)):.1f}",
        f"{float(b.get('top', 0)):.1f}",
    ]
    return "HE-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def sort_key(r: EvidenceRecord):
    b = r.bbox or {}
    return (
        r.source_document,
        r.page_number,
        _TYPE_ORDER[r.evidence_type],
        float(b.get("top", 0)),
        float(b.get("x0", 0)),
        r.raw_device_label or "",
        r.evidence_id,
    )
