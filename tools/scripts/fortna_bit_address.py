#!/usr/bin/env python3
"""Canonical Fortna bit-address model — preserve source semantics.

Conveyor.IO_Address_Bit is NOT a plain decimal integer. FortnaPlus runtime
prefers octal interpretation for digit strings in [0-7]+ (so label "10" means
logical bit 8 / High half module_bit 0).

Never call int(bit) alone and discard the raw source text.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

ENCODING_FORTNA_OCTAL_LABEL = "FORTNA_OCTAL_LABEL"
ENCODING_DECIMAL_INDEX = "DECIMAL_INDEX"
ENCODING_MODULE_LOCAL = "MODULE_LOCAL"
ENCODING_UNKNOWN = "UNKNOWN"

_OCTAL_DIGIT_RE = re.compile(r"^[0-7]+$")


@dataclass(frozen=True)
class FortnaBitAddress:
    """Source-preserving Fortna IO_Address_Bit interpretation."""

    raw_text: str
    raw_value: int | None
    encoding: str
    logical_bit: int | None
    half: str | None  # "Low" | "High" | None
    module_bit: int | None
    source_table: str = ""
    source_row: int | None = None
    confidence: str = "HIGH"  # HIGH | MEDIUM | LOW | UNKNOWN
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


def parse_fortna_bit_address(
    io_bit: Any,
    *,
    source_table: str = "",
    source_row: int | None = None,
) -> FortnaBitAddress:
    """Parse Conveyor/Configio bit field without losing Fortna label semantics.

    Evidence (FortnaPlus source):
      fortna_autogen._fortna_bit_is_high / _fortna_bit_to_data_bit:
        prefer int(s, 8) for digit strings; octal 10-17 → Data 8-15 (High).
      fortna_physical_word_resolver.parse_fortna_octal_bit:
        [0-7]+ strings parsed as base-8; decimal 10-17 remapped to 8+(n-10).

    Encoding rules (evidence-backed):
      - raw_text matching ^[0-7]+$ → FORTNA_OCTAL_LABEL via int(text, 8)
        e.g. "10" → logical 8, High, module_bit 0
      - raw_text "8"/"9" or decimal 8-9 → DECIMAL_INDEX logical 8/9 (High)
        (8/9 are NOT valid octal digit strings for the [0-7]+ path)
      - decimal integers 10-17 (when text has 8/9 digits or came as int) →
        FORTNA_OCTAL_LABEL equivalent via 8+(n-10)
      - 0-7 as decimal or octal (same value) → Low half
    """
    if io_bit is None:
        return FortnaBitAddress(
            raw_text="",
            raw_value=None,
            encoding=ENCODING_UNKNOWN,
            logical_bit=None,
            half=None,
            module_bit=None,
            source_table=source_table,
            source_row=source_row,
            confidence="UNKNOWN",
            notes=("empty_bit",),
        )

    # Preserve exact text before any numeric coercion
    if isinstance(io_bit, bool):
        raw_text = str(int(io_bit))
    elif isinstance(io_bit, int):
        raw_text = str(io_bit)
    else:
        raw_text = str(io_bit).strip()

    if raw_text == "":
        return FortnaBitAddress(
            raw_text="",
            raw_value=None,
            encoding=ENCODING_UNKNOWN,
            logical_bit=None,
            half=None,
            module_bit=None,
            source_table=source_table,
            source_row=source_row,
            confidence="UNKNOWN",
            notes=("empty_bit",),
        )

    notes: list[str] = []
    encoding = ENCODING_UNKNOWN
    logical: int | None = None

    # Path A: Fortna octal label — digit string using only 0-7 (includes "10".."17")
    if _OCTAL_DIGIT_RE.fullmatch(raw_text) and len(raw_text) <= 2:
        try:
            logical = int(raw_text, 8)
            encoding = ENCODING_FORTNA_OCTAL_LABEL
            notes.append("parsed_as_base8_label")
        except ValueError:
            logical = None

    # Path B: decimal / mixed (contains 8 or 9, or non-octal form)
    if logical is None:
        try:
            dec = int(float(raw_text))
        except (TypeError, ValueError):
            return FortnaBitAddress(
                raw_text=raw_text,
                raw_value=None,
                encoding=ENCODING_UNKNOWN,
                logical_bit=None,
                half=None,
                module_bit=None,
                source_table=source_table,
                source_row=source_row,
                confidence="UNKNOWN",
                notes=("unparseable",),
            )
        # Conveyor sometimes stores octal labels 10-17 as decimal integers 10-17
        if 10 <= dec <= 17:
            logical = 8 + (dec - 10)
            encoding = ENCODING_FORTNA_OCTAL_LABEL
            notes.append("decimal_10_17_remapped_to_logical_8_15")
        elif 0 <= dec <= 15:
            logical = dec
            encoding = ENCODING_DECIMAL_INDEX
            notes.append("decimal_0_15")
        else:
            return FortnaBitAddress(
                raw_text=raw_text,
                raw_value=dec,
                encoding=ENCODING_UNKNOWN,
                logical_bit=None,
                half=None,
                module_bit=None,
                source_table=source_table,
                source_row=source_row,
                confidence="LOW",
                notes=("out_of_range",),
            )

    assert logical is not None
    half = "High" if logical >= 8 else "Low"
    module_bit = logical - 8 if logical >= 8 else logical
    conf = "HIGH"
    if encoding == ENCODING_DECIMAL_INDEX and logical >= 8:
        # 8/9 as decimal High labels — legal normalized form, less common as source
        conf = "MEDIUM"
        notes.append("decimal_high_half_8_9")

    return FortnaBitAddress(
        raw_text=raw_text,
        raw_value=logical,  # logical after interpretation
        encoding=encoding,
        logical_bit=logical,
        half=half,
        module_bit=module_bit,
        source_table=source_table,
        source_row=source_row,
        confidence=conf,
        notes=tuple(notes),
    )


def fortna_bit_lookup_keys(addr: FortnaBitAddress, word: int | str) -> list[str]:
    """Canonical by_word_bit lookup keys for a parsed address (logical only)."""
    try:
        w = int(float(str(word).strip()))
    except (TypeError, ValueError):
        return []
    if addr.logical_bit is None:
        return []
    return [f"{w}:{addr.logical_bit}"]
