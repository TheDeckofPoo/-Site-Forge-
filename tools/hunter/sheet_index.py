"""Title-block / sheet metadata detection (sheet number, title, revision).

Only literal printed key/value text is used ("SHEET: E-101", "TITLE: ...",
"REV: B", "DWG NO: ...").  Nothing is guessed from file names or page
order.  Missing fields are flagged REVIEW_REQUIRED.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .device_grammar import CONTINUATION_RE
from .pdf_reader import PageText
from .text_blocks import TextLine, bbox_of

TITLE_BLOCK_REGION_TOP = 0.75  # bottom 25% of the sheet

SHEET_RE = re.compile(
    r"\b(?:SHEET|SHT)\.?\s*(?:NO\.?|NUMBER|#)?\s*[:#]?\s*(?!TITLE\b)([A-Z0-9](?:[A-Z0-9\-\.]*[A-Z0-9])?)(?:\s+OF\s+(\d+))?",
    re.I,
)
TITLE_RE = re.compile(
    r"\b(?:SHEET\s+)?TITLE\s*[:]\s*(.+?)(?=\s+(?:SHEET|SHT|REV|REVISION|DWG|DRAWING|DATE)\b|$)", re.I
)
REV_RE = re.compile(r"\bREV(?:ISION)?(?:\.|:|#|\s)\s*(?:NO\.?\s*)?[:#]?\s*([A-Z0-9]{1,3})\b", re.I)
DWG_RE = re.compile(
    r"\b(?:DWG|DRAWING)\.?\s*(?:NO\.?|NUMBER|#)\s*[:#]?\s*([A-Z0-9](?:[A-Z0-9\-\.]*[A-Z0-9])?)", re.I
)
DATE_RE = re.compile(r"\bDATE\s*[:]\s*(\S+)", re.I)


@dataclass
class SheetInfo:
    source_document: str
    page_number: int
    sheet_number: Optional[str] = None
    sheet_count_text: Optional[str] = None
    sheet_title: Optional[str] = None
    drawing_revision: Optional[str] = None
    drawing_number: Optional[str] = None
    drawing_date: Optional[str] = None
    title_block_found: bool = False
    title_block_in_expected_region: bool = False
    has_text_layer: bool = True
    missing_fields: List[str] = field(default_factory=list)
    source_lines: List[Dict] = field(default_factory=list)
    state: str = "REVIEW_REQUIRED"
    notes: List[str] = field(default_factory=list)
    consumed_line_ids: Set[int] = field(default_factory=set)

    def to_json(self) -> Dict:
        return {
            "source_document": self.source_document,
            "page_number": self.page_number,
            "sheet_number": self.sheet_number,
            "sheet_count_text": self.sheet_count_text,
            "sheet_title": self.sheet_title,
            "drawing_revision": self.drawing_revision,
            "drawing_number": self.drawing_number,
            "drawing_date": self.drawing_date,
            "title_block_found": self.title_block_found,
            "title_block_in_expected_region": self.title_block_in_expected_region,
            "has_text_layer": self.has_text_layer,
            "missing_fields": list(self.missing_fields),
            "source_lines": list(self.source_lines),
            "state": self.state,
            "notes": list(self.notes),
        }


def _scan(lines: List[TextLine]) -> Dict:
    found: Dict = {}
    used: List[TextLine] = []
    for ln in lines:
        text = ln.text
        if CONTINUATION_RE.search(text):
            continue  # "CONTINUED ON SHEET X" is a cross-reference, not a title block
        hit = False
        text_wo_title = text
        m = TITLE_RE.search(text)
        if m:
            text_wo_title = text[: m.start()] + " " + text[m.end():]
            if "sheet_title" not in found:
                found["sheet_title"] = m.group(1).strip()
                hit = True
        m = SHEET_RE.search(text_wo_title)
        if m and "sheet_number" not in found:
            found["sheet_number"] = m.group(1)
            if m.group(2):
                found["sheet_count_text"] = m.group(2)
            hit = True
        m = DWG_RE.search(text_wo_title)
        if m and "drawing_number" not in found:
            found["drawing_number"] = m.group(1)
            hit = True
        m = REV_RE.search(text_wo_title)
        if m and "drawing_revision" not in found:
            found["drawing_revision"] = m.group(1)
            hit = True
        m = DATE_RE.search(text_wo_title)
        if m and "drawing_date" not in found:
            found["drawing_date"] = m.group(1)
            hit = True
        if hit:
            used.append(ln)
    return {"found": found, "used": used}


def detect_sheet(source_document: str, page: PageText, lines: List[TextLine]) -> SheetInfo:
    info = SheetInfo(source_document=source_document, page_number=page.page_number)
    if not page.has_text_layer:
        info.has_text_layer = False
        info.missing_fields = ["sheet_number", "sheet_title", "drawing_revision"]
        info.notes.append("TEXT_LAYER_MISSING: title block could not be read (no OCR by default)")
        return info
    region_top = page.height * TITLE_BLOCK_REGION_TOP
    region_lines = [ln for ln in lines if ln.top >= region_top]
    res = _scan(region_lines)
    in_region = bool(res["found"])
    if not in_region:
        res = _scan(lines)
    found, used = res["found"], res["used"]
    for k, v in found.items():
        setattr(info, k, v)
    if info.sheet_number is None and info.drawing_number is not None:
        info.sheet_number = info.drawing_number
        info.notes.append("sheet_number taken from printed drawing number (no explicit SHEET field)")
    info.title_block_found = bool(found)
    info.title_block_in_expected_region = in_region
    info.consumed_line_ids = {ln.line_id for ln in used}
    info.source_lines = [{"text": ln.text, "bbox": bbox_of(ln.words)} for ln in used]
    for f in ("sheet_number", "sheet_title", "drawing_revision"):
        if getattr(info, f) in (None, ""):
            info.missing_fields.append(f)
    if not info.title_block_found:
        info.notes.append("MISSING_TITLE_BLOCK: no printed sheet/title/revision fields found")
    elif not in_region:
        info.notes.append("title-block-like fields found outside the expected title-block region")
    info.state = (
        "PROVEN" if (in_region and info.sheet_number and not info.missing_fields) else "REVIEW_REQUIRED"
    )
    return info
