"""Deterministic Configio Desc dialect classifier.

Does NOT invent semantics. Unknowns are returned as UNKNOWN with a structural
pattern hash for clustering. Reuses fortna_physical_word_resolver parsers when
they match; adds forms those parsers do not cover (CATALOG_INDEX, BARE_CATALOG,
SHORT_ALIAS, NODE_SLOT, PANEL_STATION).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fortna_physical_word_resolver import (  # noqa: E402
    parse_configio_catalog_word_bank,
    parse_configio_desc,
    parse_configio_node_desc,
)
from fortna_rockwell_catalog import detect_rockwell_catalogs  # noqa: E402

from .corpus_models import (  # noqa: E402
    FORM_BARE_CATALOG,
    FORM_CATALOG_INDEX,
    FORM_CATALOG_WORD_BANK,
    FORM_NODE_SLOT,
    FORM_PANEL_STATION,
    FORM_SHORT_ALIAS,
    FORM_UNKNOWN,
    DialectHit,
)

# catalog-index: 1794-IA16-5  (exactly one trailing numeric — not word-bank)
_CATALOG_INDEX_RE = re.compile(
    r"^(?P<catalog>\d{4}-[A-Za-z0-9]+)-(?P<index>\d+)$",
    re.I,
)
# bare catalog: 1794-IA16 / 1734-IB8
_BARE_CATALOG_RE = re.compile(r"^(?P<catalog>\d{4}-[A-Za-z0-9]+)$", re.I)
# short alias: IB8-9 / OA4-12 / IV8-3 (family body + index, no 1794/1734 prefix)
_SHORT_ALIAS_RE = re.compile(
    r"^(?P<body>(?:I[ABV]|O[ABVW]|IE|OE)[A-Za-z0-9]*)-(?P<index>\d+)$",
    re.I,
)
# node-slot: AENTR-2NODE51-1 / AENT-3NODE52-7 / NODE51-1A (optional panel handled upstream)
_NODE_SLOT_RE = re.compile(
    r"^(?:(?P<head>AENTR?-\d+))?NODE(?P<node>\d+)\s*-?\s*(?P<slot>\d+)(?P<half>[A-Za-z])?$",
    re.I,
)
# panel-station: WEST PACK-SL1 / EAST SHIP-SL2 (spaces + -SLn)
_PANEL_STATION_RE = re.compile(
    r"^(?P<station>[A-Za-z][A-Za-z0-9 ]+?)-SL(?P<slot>\d+)$",
    re.I,
)
# memory / N/A placeholders — still UNKNOWN, but tagged
_PLACEHOLDER_RE = re.compile(r"^(N/?A|MEM(?:ORY)?|INVALID)$", re.I)


def structural_pattern_hash(raw: str) -> str:
    """Site-independent structural fingerprint of a Desc string.

    Digits → #, runs of letters kept as shape tokens, punctuation preserved.
    Same shape across sites → same hash.
    """
    s = (raw or "").strip()
    if not s:
        return "empty"
    shape: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            while i < len(s) and s[i].isdigit():
                i += 1
            shape.append("#")
            continue
        if ch.isalpha():
            j = i
            while j < len(s) and s[j].isalpha():
                j += 1
            token = s[i:j]
            # Preserve short tokens; collapse long alpha runs to length class
            if len(token) <= 6:
                shape.append(token.upper())
            else:
                shape.append(f"A{len(token)}")
            i = j
            continue
        shape.append(ch)
        i += 1
    raw_shape = "".join(shape)
    return "sp_" + hashlib.sha1(raw_shape.encode("utf-8")).hexdigest()[:12]


def _hit(
    *,
    form: str,
    raw: str,
    catalog: str = "",
    word: int | None = None,
    bank: int | None = None,
    node: str = "",
    suffix: str = "",
    panel: str = "",
    confidence: str = "HIGH",
    evidence: dict[str, Any] | None = None,
) -> DialectHit:
    return DialectHit(
        configio_form=form,
        raw_example=raw,
        catalog=catalog,
        word=word,
        bank=bank,
        node=node,
        suffix=suffix,
        panel=panel,
        confidence=confidence,
        evidence=dict(evidence or {}),
    )


def classify_configio_dialect(desc: str) -> DialectHit:
    """Classify one Configio Desc string into a dialect form.

    Order prefers more-specific structured forms first. Does not invent meaning
    for unknowns — returns UNKNOWN + structural pattern evidence.
    """
    raw = (desc or "").strip()
    if not raw:
        return _hit(
            form=FORM_UNKNOWN,
            raw=raw,
            confidence="LOW",
            evidence={
                "reason": "empty_desc",
                "structural_pattern_hash": structural_pattern_hash(raw),
            },
        )

    # 1) Panel-catalog (CP2-1794-IA16-3) → CATALOG_INDEX with panel evidence
    panel = parse_configio_desc(raw)
    if panel:
        return _hit(
            form=FORM_CATALOG_INDEX,
            raw=raw,
            catalog=str(panel.get("catalog") or ""),
            bank=_as_int(panel.get("index")),
            suffix=str(panel.get("index") or ""),
            panel=str(panel.get("panel") or ""),
            confidence="HIGH",
            evidence={
                "parser": "parse_configio_desc",
                "legacy_form": panel.get("form"),
                "direction": panel.get("direction"),
            },
        )

    # 2) Panel-node (CP5-NODE53-1A) → NODE_SLOT
    node_p = parse_configio_node_desc(raw)
    if node_p:
        return _hit(
            form=FORM_NODE_SLOT,
            raw=raw,
            node=str(node_p.get("node") or ""),
            suffix=f"{node_p.get('desc_slot')}{node_p.get('half') or ''}",
            panel=str(node_p.get("panel") or ""),
            bank=_as_int(node_p.get("desc_slot")),
            confidence="HIGH",
            evidence={
                "parser": "parse_configio_node_desc",
                "legacy_form": node_p.get("form"),
                "lohi": node_p.get("lohi"),
            },
        )

    # 3) Catalog-word-bank (1794-IA16-600-4) — must precede catalog-index
    cwb = parse_configio_catalog_word_bank(raw)
    if cwb:
        return _hit(
            form=FORM_CATALOG_WORD_BANK,
            raw=raw,
            catalog=str(cwb.get("catalog") or ""),
            word=_as_int(cwb.get("fortna_word")),
            bank=_as_int(cwb.get("eip_bank")),
            suffix=str(cwb.get("eip_bank") if cwb.get("eip_bank") is not None else ""),
            confidence="HIGH",
            evidence={
                "parser": "parse_configio_catalog_word_bank",
                "legacy_form": cwb.get("form"),
                "is_aent_head": cwb.get("is_aent_head"),
                "direction": cwb.get("direction"),
            },
        )

    # 4) Catalog-index (1794-IA16-5)
    m = _CATALOG_INDEX_RE.match(raw)
    if m:
        return _hit(
            form=FORM_CATALOG_INDEX,
            raw=raw,
            catalog=m.group("catalog"),
            bank=_as_int(m.group("index")),
            suffix=m.group("index"),
            confidence="HIGH",
            evidence={"parser": "catalog_index_re"},
        )

    # 5) Bare catalog (1794-IA16)
    m = _BARE_CATALOG_RE.match(raw)
    if m:
        return _hit(
            form=FORM_BARE_CATALOG,
            raw=raw,
            catalog=m.group("catalog"),
            confidence="HIGH",
            evidence={"parser": "bare_catalog_re"},
        )

    # 6) Node-slot without panel (AENTR-2NODE51-1)
    m = _NODE_SLOT_RE.match(raw.replace(" ", ""))
    if m and m.group("node"):
        return _hit(
            form=FORM_NODE_SLOT,
            raw=raw,
            node=m.group("node"),
            suffix=f"{m.group('slot')}{(m.group('half') or '')}",
            bank=_as_int(m.group("slot")),
            catalog=(m.group("head") or ""),
            confidence="HIGH",
            evidence={"parser": "node_slot_re", "head": m.group("head") or ""},
        )

    # 7) Short alias (IB8-9)
    m = _SHORT_ALIAS_RE.match(raw)
    if m:
        return _hit(
            form=FORM_SHORT_ALIAS,
            raw=raw,
            catalog=m.group("body").upper(),
            suffix=m.group("index"),
            bank=_as_int(m.group("index")),
            confidence="MEDIUM",
            evidence={"parser": "short_alias_re"},
        )

    # 8) Panel-station (WEST PACK-SL1)
    m = _PANEL_STATION_RE.match(raw)
    if m:
        return _hit(
            form=FORM_PANEL_STATION,
            raw=raw,
            panel=m.group("station").strip().upper(),
            suffix=m.group("slot"),
            bank=_as_int(m.group("slot")),
            confidence="MEDIUM",
            evidence={"parser": "panel_station_re"},
        )

    # Catalog signature present but form not classified → still UNKNOWN
    cats = detect_rockwell_catalogs(raw)
    cat_ev = cats[0].to_dict() if cats else {}
    ph = structural_pattern_hash(raw)
    reason = "placeholder" if _PLACEHOLDER_RE.match(raw) else "unclassified_structure"
    return _hit(
        form=FORM_UNKNOWN,
        raw=raw,
        catalog=str(cat_ev.get("catalog_number") or ""),
        confidence="LOW",
        evidence={
            "reason": reason,
            "structural_pattern_hash": ph,
            "catalog_signature": cat_ev or None,
        },
    )


def _as_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def classify_configio_rows(
    rows: list[dict[str, Any]],
    *,
    archive_sha256: str = "",
    machine: str = "",
) -> list[DialectHit]:
    """Classify Desc values; collapse identical (form, raw) with counts."""
    buckets: dict[tuple[str, str], DialectHit] = {}
    for r in rows or []:
        desc = str(r.get("Desc") or r.get("desc") or "").strip()
        hit = classify_configio_dialect(desc)
        hit.archive_sha256 = archive_sha256
        hit.machine = machine
        key = (hit.configio_form, hit.raw_example)
        if key in buckets:
            buckets[key].count += 1
        else:
            buckets[key] = hit
    return sorted(
        buckets.values(),
        key=lambda h: (-h.count, h.configio_form, h.raw_example),
    )
