"""Group positioned words into text lines, keeping coordinates.

A line keeps a char-offset map to its words so that regex matches on the
line text can be traced back to exact word bounding boxes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .pdf_reader import PageText, Word

LINE_Y_TOL = 3.0      # words whose tops differ <= this share a line
WORD_GAP_FACTOR = 3.0  # horizontal gap (x char-heights) that splits a line into segments


@dataclass
class TextLine:
    line_id: int
    words: List[Word]
    text: str = ""
    spans: List[Tuple[int, int, Word]] = field(default_factory=list)

    def __post_init__(self) -> None:
        parts: List[str] = []
        pos = 0
        for w in self.words:
            if parts:
                pos += 1
            self.spans.append((pos, pos + len(w.text), w))
            parts.append(w.text)
            pos += len(w.text)
        self.text = " ".join(parts)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    def words_in_span(self, start: int, end: int) -> List[Word]:
        return [w for (s, e, w) in self.spans if s < end and e > start]


def bbox_of(words: Sequence[Word]) -> Dict[str, float]:
    return {
        "x0": round(min(w.x0 for w in words), 2),
        "top": round(min(w.top for w in words), 2),
        "x1": round(max(w.x1 for w in words), 2),
        "bottom": round(max(w.bottom for w in words), 2),
    }


def build_lines(page: PageText) -> List[TextLine]:
    """Cluster words into lines (by top), then split on large x gaps.

    Splitting on large gaps keeps separate drawing text objects that happen
    to sit at the same height from being glued into one "sentence".
    """
    rows: List[List[Word]] = []
    for w in sorted(page.words, key=lambda w: (w.top, w.x0, w.index)):
        if rows and abs(rows[-1][0].top - w.top) <= LINE_Y_TOL:
            rows[-1].append(w)
        else:
            rows.append([w])
    segments: List[List[Word]] = []
    for row in rows:
        row.sort(key=lambda w: (w.x0, w.index))
        cur = [row[0]]
        for w in row[1:]:
            prev = cur[-1]
            h = max(prev.bottom - prev.top, 1.0)
            if w.x0 - prev.x1 > WORD_GAP_FACTOR * h:
                segments.append(cur)
                cur = [w]
            else:
                cur.append(w)
        segments.append(cur)
    segments.sort(key=lambda seg: (round(seg[0].top, 1), seg[0].x0))
    return [TextLine(line_id=i, words=seg) for i, seg in enumerate(segments)]


def context_for(lines: List[TextLine], line: TextLine, radius: int = 2, max_dist: float = 40.0) -> str:
    """Nearby printed text (neighbouring lines vertically close, overlapping in x)."""
    near = []
    for other in lines:
        if other.line_id == line.line_id:
            near.append((0.0, other))
            continue
        dy = abs(other.top - line.top)
        overlap = min(other.x1, line.x1 + 150) - max(other.x0, line.x0 - 150)
        if dy <= max_dist and overlap > 0:
            near.append((dy, other))
    near.sort(key=lambda t: (t[0], t[1].top, t[1].x0))
    chosen = sorted((o for _, o in near[: 2 * radius + 1]), key=lambda o: (o.top, o.x0))
    return " | ".join(o.text for o in chosen)
