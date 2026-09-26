"""Per-page candidate extraction: device labels, printed I/O / terminal /
network references, continuation references and sheet metadata.

Grammar nominates; evidence semantics decide state:
  * label + same-line descriptive family text printed   -> PROVEN
  * label matching grammar only                         -> DERIVED
  * ambiguous prefix                                    -> REVIEW_REQUIRED
  * device-like but unclassifiable                      -> UNKNOWN (kept)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import device_grammar as g
from .evidence_records import EvidenceRecord
from .pdf_reader import DocumentText, PageText, Word
from .sheet_index import SheetInfo
from .text_blocks import TextLine, bbox_of, context_for


@dataclass
class Item:
    kind: str  # device|ambiguous|unknown|io|io_module|terminal|network|continuation|word
    text: str
    words: List[Word]
    cls: Optional[g.TokenClass] = None
    rule_id: Optional[str] = None
    target: Optional[str] = None
    extra: dict = field(default_factory=dict)


def _line_spans(text: str) -> List[Tuple[int, int, str, str, Optional[str]]]:
    """(start, end, kind, rule_id, target) for line-level printed references."""
    spans: List[Tuple[int, int, str, str, Optional[str]]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b, *_ in spans)

    for m in g.CONTINUATION_RE.finditer(text):
        spans.append((m.start(), m.end(), "continuation", "C-XREF", m.group(1)))
    for m in g.IO_MODULE_RE.finditer(text):
        if free(m.start(), m.end()):
            spans.append((m.start(), m.end(), "io_module", "IO-MODULE", None))
    for rid, rx in g.IO_ADDRESS_RES:
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                spans.append((m.start(), m.end(), "io", rid, None))
    for rid, rx in g.TERMINAL_RES:
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                spans.append((m.start(), m.end(), "terminal", "T-" + rid, None))
    for m in g.NETWORK_RE.finditer(text):
        if free(m.start(), m.end()):
            spans.append((m.start(), m.end(), "network", "N-IPV4", None))
    return sorted(spans)


def line_items(line: TextLine) -> List[Item]:
    """Split a line into ordered items (printed refs, device tokens, words)."""
    spans = _line_spans(line.text)
    items: List[Item] = []
    covered = set()
    span_items = []
    for s, e, kind, rid, target in spans:
        ws = line.words_in_span(s, e)
        if not ws:
            continue
        for w in ws:
            covered.add(w.index)
        span_items.append((ws[0].x0, Item(kind, line.text[s:e], ws, rule_id=rid, target=target)))
    word_items = []
    for w in line.words:
        if w.index in covered:
            continue
        # split glued arrows: "PE1300->P1300"
        pieces = [w.text]
        for arrow in ("->", "→", "=>"):
            if arrow in w.text and w.text != arrow:
                pieces = []
                for k, part in enumerate(w.text.split(arrow)):
                    if k:
                        pieces.append(arrow)
                    if part:
                        pieces.append(part)
                break
        for p in pieces:
            tok = g.strip_token(p)
            c = g.classify_token(tok)
            if c is not None:
                word_items.append((w.x0, Item(c.kind, tok, [w], cls=c, rule_id=c.rule_id)))
            else:
                word_items.append((w.x0, Item("word", p, [w])))
    ordered = sorted(span_items + word_items, key=lambda t: t[0])
    # stable: python sort keeps split-piece order for equal x0
    items = [it for _, it in ordered]
    return items


def _sheet_fields(info: Optional[SheetInfo]) -> dict:
    if info is None:
        return {"sheet_number": None, "sheet_title": None, "drawing_revision": None}
    return {
        "sheet_number": info.sheet_number,
        "sheet_title": info.sheet_title,
        "drawing_revision": info.drawing_revision,
    }


def _panel_on_line(items: List[Item]) -> Optional[str]:
    panels = [it.text for it in items if it.kind == "device" and it.cls and it.cls.family in ("control_panel", "remote_io_panel")]
    return " | ".join(panels) if panels else None


def failure_record(doc: DocumentText, page: Optional[PageText], etype: str, note: str,
                   project, controller, info: Optional[SheetInfo] = None) -> EvidenceRecord:
    return EvidenceRecord(
        project=project,
        controller_scope_hint=controller,
        source_document=doc.source_document,
        source_document_hash=doc.sha256,
        page_number=page.page_number if page else 0,
        evidence_type=etype,
        raw_text="",
        state="REVIEW_REQUIRED",
        confidence=0.0,
        bbox={"x0": 0.0, "top": 0.0, "x1": page.width, "bottom": page.height} if page else None,
        page_size={"width": page.width, "height": page.height} if page else None,
        notes=[note, "extraction could not proceed; no content was inferred"],
        **_sheet_fields(info),
    )


def extract_page_candidates(
    doc: DocumentText,
    page: PageText,
    lines: List[TextLine],
    info: SheetInfo,
    project: Optional[str],
    controller: Optional[str],
) -> List[EvidenceRecord]:
    records: List[EvidenceRecord] = []
    common = dict(
        project=project,
        controller_scope_hint=controller,
        source_document=doc.source_document,
        source_document_hash=doc.sha256,
        page_number=page.page_number,
        page_size={"width": page.width, "height": page.height},
        **_sheet_fields(info),
    )

    if info.title_block_found:
        used = [ln for ln in lines if ln.line_id in info.consumed_line_ids]
        words = [w for ln in used for w in ln.words]
        records.append(EvidenceRecord(
            evidence_type="SHEET_METADATA",
            raw_text=" | ".join(ln.text for ln in used),
            state=info.state,
            confidence=0.9 if info.state == "PROVEN" else 0.5,
            entity_type_candidate="sheet_metadata",
            bbox=bbox_of(words),
            notes=list(info.notes) + ([f"missing fields: {', '.join(info.missing_fields)}"] if info.missing_fields else []),
            **common,
        ))

    for ln in lines:
        if ln.line_id in info.consumed_line_ids:
            continue  # title-block text is sheet metadata, not device evidence
        items = line_items(ln)
        ctx = context_for(lines, ln)
        panel = _panel_on_line(items)
        for it in items:
            bb = bbox_of(it.words)
            if it.kind == "device":
                fam = it.cls.family
                kw = g.corroborating_keyword(fam, ln.text)
                notes = [f"family nominated by naming grammar rule {it.rule_id} (naming pattern is not physical proof)"]
                if kw:
                    state, conf = "PROVEN", 0.9
                    notes.append(f"print states family on same line: '{kw}'")
                else:
                    state, conf = "DERIVED", it.cls.base_confidence
                    adj = [o for o in lines if o.line_id != ln.line_id and abs(o.top - ln.top) <= 14
                           and min(o.x1, ln.x1) > max(o.x0, ln.x0)]
                    for o in adj:
                        akw = g.corroborating_keyword(fam, o.text)
                        if akw:
                            notes.append(f"adjacent printed text mentions '{akw}' (not same line; not promoted)")
                            break
                if fam in g.SAFETY_FAMILIES:
                    notes.append("safety device label only; no Safety-zone / Area membership is implied")
                records.append(EvidenceRecord(
                    evidence_type="DEVICE_LABEL", raw_text=ln.text, state=state, confidence=conf,
                    raw_device_label=it.text, normalized_name_candidate=g.normalize_label(it.text),
                    entity_type_candidate=fam, grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=notes, **common,
                ))
            elif it.kind == "ambiguous":
                records.append(EvidenceRecord(
                    evidence_type="AMBIGUOUS_DEVICE_TOKEN", raw_text=ln.text, state="REVIEW_REQUIRED",
                    confidence=0.4, raw_device_label=it.text,
                    normalized_name_candidate=g.normalize_label(it.text),
                    entity_type_candidate="ambiguous", grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["ambiguous prefix; possible families: " + ", ".join(it.cls.candidates)], **common,
                ))
            elif it.kind == "unknown":
                records.append(EvidenceRecord(
                    evidence_type="UNKNOWN_DEVICE_TOKEN", raw_text=ln.text, state="UNKNOWN",
                    confidence=0.2, raw_device_label=it.text,
                    normalized_name_candidate=g.normalize_label(it.text),
                    entity_type_candidate="unknown", grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["device-like token not recognised by grammar; conserved for review (unsupported != invisible)"],
                    **common,
                ))
            elif it.kind == "io":
                records.append(EvidenceRecord(
                    evidence_type="IO_REFERENCE", raw_text=ln.text, state="PROVEN", confidence=0.9,
                    physical_address_text=it.text, entity_type_candidate="io_channel_reference",
                    panel_or_rack_text=panel, grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["printed I/O address text; PROVEN = text is printed, not an I/O assignment"]
                    + (["panel/rack text printed on same row only"] if panel else []),
                    **common,
                ))
            elif it.kind == "io_module":
                records.append(EvidenceRecord(
                    evidence_type="IO_MODULE_REFERENCE", raw_text=ln.text, state="PROVEN", confidence=0.9,
                    module_or_terminal_text=it.text, entity_type_candidate="io_module",
                    panel_or_rack_text=panel, grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["printed I/O module catalog text"], **common,
                ))
            elif it.kind == "terminal":
                records.append(EvidenceRecord(
                    evidence_type="TERMINAL_REFERENCE", raw_text=ln.text, state="PROVEN", confidence=0.9,
                    module_or_terminal_text=it.text, entity_type_candidate="terminal_reference",
                    panel_or_rack_text=panel, grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["printed terminal reference text"], **common,
                ))
            elif it.kind == "network":
                records.append(EvidenceRecord(
                    evidence_type="NETWORK_REFERENCE", raw_text=ln.text, state="PROVEN", confidence=0.85,
                    physical_address_text=it.text, entity_type_candidate="network_reference",
                    grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=["explicitly printed network address text"], **common,
                ))
            elif it.kind == "continuation":
                records.append(EvidenceRecord(
                    evidence_type="CONTINUATION_REFERENCE", raw_text=ln.text, state="PROVEN", confidence=0.9,
                    continuation_reference=it.target, entity_type_candidate="sheet_cross_reference",
                    grammar_rule=it.rule_id, bbox=bb, context_text=ctx,
                    notes=[f"printed cross-reference text '{it.text}'"], **common,
                ))
    return records
