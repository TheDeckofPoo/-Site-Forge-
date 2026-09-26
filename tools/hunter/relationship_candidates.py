"""Relationship candidates — recorded ONLY as strongly as the print supports.

  * "A <connector> B" printed on one line (->, TO, DRIVES, FEEDS, MOUNTED ON,
    WIRED TO, IN SAFETY CIRCUIT, ...)                      -> PROVEN
  * exactly one device + printed I/O / terminal on the same text row,
    no connector                                            -> DERIVED
  * several devices + I/O on a row without connector        -> REVIEW_REQUIRED
  * two devices on one line sharing a numeric core, no
    connector (e.g. "M1300 P1300")                          -> REVIEW_REQUIRED

Same page, numeric similarity, graphic proximity, same panel or similar
names are NEVER proof.  Hunter never infers Safety-zone membership, Area
membership, PLC endpoints or upstream/downstream flow.
"""
from __future__ import annotations

import re
from typing import List, Optional

from . import device_grammar as g
from .device_candidates import Item, _sheet_fields, line_items
from .evidence_records import EvidenceRecord
from .pdf_reader import DocumentText, PageText
from .sheet_index import SheetInfo
from .text_blocks import TextLine, bbox_of, context_for

ENDPOINT_KINDS = ("device", "io", "terminal", "io_module")


def _connector_at(items: List[Item], i: int):
    """Return (kind_text, n_items) if items[i:i+n] form a connector phrase."""
    for n in (3, 2, 1):
        seg = items[i:i + n]
        if len(seg) < n or any(it.kind != "word" for it in seg):
            continue
        phrase = " ".join(it.text for it in seg)
        if g.CONNECTOR_RE.match(phrase):
            return re.sub(r"\s+", "_", phrase.upper()).replace("→", "->"), n
    return None


def _digits(s: str) -> str:
    m = re.search(r"\d+", s)
    return m.group(0) if m else ""


def extract_line_relationships(
    doc: DocumentText, page: PageText, lines: List[TextLine], info: SheetInfo,
    project: Optional[str], controller: Optional[str],
) -> List[EvidenceRecord]:
    out: List[EvidenceRecord] = []
    common = dict(
        project=project, controller_scope_hint=controller,
        source_document=doc.source_document, source_document_hash=doc.sha256,
        page_number=page.page_number, page_size={"width": page.width, "height": page.height},
        **_sheet_fields(info),
    )

    def rec(a: Item, b: Item, kind: str, state: str, conf: float, notes: List[str], ln: TextLine):
        dev, other = (a, b) if a.kind == "device" else (b, a)
        fields = dict(
            raw_device_label=dev.text,
            normalized_name_candidate=g.normalize_label(dev.text),
            entity_type_candidate=dev.cls.family if dev.cls else None,
        )
        if other.kind == "device":
            fields["related_device_text"] = other.text
        elif other.kind == "io":
            fields["physical_address_text"] = other.text
        else:
            fields["module_or_terminal_text"] = other.text
        panels = [it.text for it in items if it.kind == "device" and it.cls.family in ("control_panel", "remote_io_panel")
                  and it is not dev and it is not other]
        if panels:
            fields["panel_or_rack_text"] = " | ".join(panels)
        out.append(EvidenceRecord(
            evidence_type="RELATIONSHIP", raw_text=ln.text, state=state, confidence=conf,
            relationship_kind=kind, bbox=bbox_of(a.words + b.words), context_text=context_for(lines, ln),
            grammar_rule="R-" + kind, notes=notes + ["no Safety-zone / Area / PLC-endpoint membership is implied"],
            **fields, **common,
        ))

    for ln in lines:
        if ln.line_id in info.consumed_line_ids:
            continue
        items = line_items(ln)
        endpoints_linked = set()
        # 1) explicit printed connectors
        for i, it in enumerate(items):
            if it.kind not in ENDPOINT_KINDS:
                continue
            conn = _connector_at(items, i + 1)
            if not conn:
                continue
            kind, n = conn
            j = i + 1 + n
            if j >= len(items) or items[j].kind not in ENDPOINT_KINDS:
                continue
            b = items[j]
            if "device" not in (it.kind, b.kind):
                continue
            rec(it, b, "EXPLICIT_" + kind, "PROVEN", 0.9,
                [f"explicit printed link '{it.text} {' '.join(x.text for x in items[i+1:j])} {b.text}'"], ln)
            endpoints_linked.update({id(it), id(b)})
        devices = [it for it in items if it.kind == "device"]
        field_devices = [d for d in devices if d.cls.family not in ("control_panel", "remote_io_panel", "controller")]
        refs = [it for it in items if it.kind in ("io", "terminal")]
        # 2) same printed row: device + I/O / terminal, no connector
        for r in refs:
            if id(r) in endpoints_linked:
                continue
            unlinked = [d for d in field_devices if id(d) not in endpoints_linked]
            if len(unlinked) == 1:
                rec(unlinked[0], r, "SAME_PRINTED_ROW", "DERIVED", 0.6,
                    ["device and printed reference share one text row; row layout is not an explicit connector"], ln)
            elif len(unlinked) > 1:
                for d in unlinked:
                    rec(d, r, "SAME_PRINTED_ROW_MULTI_DEVICE", "REVIEW_REQUIRED", 0.3,
                        ["several devices share this row with the printed reference: "
                         + ", ".join(x.text for x in unlinked)], ln)
        # 3) weak: two devices on one line with the same numeric core
        for a_i in range(len(devices)):
            for b_i in range(a_i + 1, len(devices)):
                a, b = devices[a_i], devices[b_i]
                if id(a) in endpoints_linked and id(b) in endpoints_linked:
                    continue
                if _digits(a.text) and _digits(a.text) == _digits(b.text) and a.cls.family != b.cls.family:
                    rec(a, b, "WEAK_SAME_LINE_NUMERIC_MATCH", "REVIEW_REQUIRED", 0.25,
                        ["same line + shared number only; similarity is NOT proof of a relationship"], ln)
    return out
