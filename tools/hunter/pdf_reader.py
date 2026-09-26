"""PDF enumeration, hashing and native text-layer extraction.

Read-only: input files are opened for reading only.  No OCR is performed.
Coordinates are PDF points, top-left origin (pdfplumber convention),
rounded to 2 decimals for determinism.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Pages with fewer usable characters than this are treated as having no
# usable text layer (TEXT_LAYER_MISSING).
MIN_USABLE_CHARS = 3


@dataclass(frozen=True)
class Word:
    index: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class PageText:
    page_number: int  # 1-based
    width: float
    height: float
    words: List[Word] = field(default_factory=list)
    image_count: int = 0
    has_text_layer: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class DocumentText:
    source_document: str  # path relative to input root (stable id)
    path: Path
    sha256: str
    size_bytes: int
    pages: List[PageText] = field(default_factory=list)
    read_error: Optional[str] = None


def enumerate_pdfs(input_path: Path) -> List[tuple]:
    """Return sorted [(relative_name, absolute_path)] for a PDF or a dir."""
    input_path = Path(input_path)
    if input_path.is_file():
        return [(input_path.name, input_path.resolve())]
    if input_path.is_dir():
        found = [p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
        out = [(p.relative_to(input_path).as_posix(), p.resolve()) for p in found]
        return sorted(out, key=lambda t: t[0])
    raise FileNotFoundError(f"input not found: {input_path}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _r(v: float) -> float:
    return round(float(v), 2)


def read_document(source_document: str, path: Path) -> DocumentText:
    path = Path(path)
    doc = DocumentText(
        source_document=source_document,
        path=path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )
    try:
        import pdfplumber  # MIT; imported lazily so --help works without it
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pdfplumber is required: pip install -r tools/hunter/requirements.txt"
        ) from exc
    try:
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pt = PageText(page_number=i, width=_r(page.width), height=_r(page.height))
                try:
                    raw_words = page.extract_words(
                        keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5, y_tolerance=2
                    )
                except Exception as exc:  # noqa: BLE001
                    raw_words = []
                    pt.warnings.append(f"WORD_EXTRACTION_ERROR: {type(exc).__name__}: {exc}")
                try:
                    pt.image_count = len(page.images)
                except Exception:  # noqa: BLE001
                    pt.image_count = 0
                words = []
                for w in raw_words:
                    t = (w.get("text") or "").strip()
                    if not t:
                        continue
                    words.append((
                        _r(w["top"]), _r(w["x0"]), t, _r(w["x1"]), _r(w["bottom"])
                    ))
                words.sort(key=lambda t: (t[0], t[1], t[2]))
                pt.words = [
                    Word(index=k, text=t, x0=x0, top=top, x1=x1, bottom=bottom)
                    for k, (top, x0, t, x1, bottom) in enumerate(words)
                ]
                usable = sum(len(w.text) for w in pt.words if any(c.isalnum() for c in w.text))
                if usable < MIN_USABLE_CHARS:
                    pt.has_text_layer = False
                    pt.warnings.append(
                        "TEXT_LAYER_MISSING: no usable native text layer"
                        + (f" ({pt.image_count} image(s) on page)" if pt.image_count else "")
                        + "; OCR is disabled by default, nothing was inferred"
                    )
                doc.pages.append(pt)
    except Exception as exc:  # noqa: BLE001
        doc.read_error = f"{type(exc).__name__}: {exc}"
    return doc
