#!/usr/bin/env python3
"""Generic Studio/Logix identifier sanitization (safe partial emit).

Preserves raw source identity in provenance. Emits a deterministic Studio-safe
alias only when the transformation is unambiguous and collision-aware.

Never invents operational semantics — syntax legality only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_VALID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TAG_NAME_ATTR_RE = re.compile(r'\bName="([^"]+)"')
# Characters that are illegal in Logix tag names → underscore
_ILLEGAL_RE = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class IdentifierMapEntry:
    raw_name: str
    emitted_logix_name: str
    reason_for_change: str
    source_provenance: str = "l5x_tag_declaration"
    confidence: str = "SYNTAX_ONLY"
    collision_status: str = "OK"
    disposition: str = "SANITIZED_FOR_EMIT"  # or WITHHELD / COLLISION_REVIEW

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_name": self.raw_name,
            "canonical_identity": self.raw_name,
            "emitted_logix_name": self.emitted_logix_name,
            "reason_for_change": self.reason_for_change,
            "source/provenance": self.source_provenance,
            "confidence/authority": self.confidence,
            "collision_status": self.collision_status,
            "disposition": self.disposition,
        }


@dataclass
class IdentifierSanitizeReport:
    entries: list[IdentifierMapEntry] = field(default_factory=list)
    sanitized_count: int = 0
    withheld_count: int = 0
    collision_count: int = 0
    invalid_raw_found: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "invalid_raw_identifiers_found": self.invalid_raw_found,
            "safely_sanitized": self.sanitized_count,
            "quarantined_withheld": self.withheld_count,
            "sanitization_collisions": self.collision_count,
            "entries": [e.to_dict() for e in self.entries],
        }


def is_valid_logix_identifier(name: str) -> bool:
    return bool(name) and bool(_VALID_RE.match(name))


def sanitize_logix_identifier(raw: str) -> str:
    """Deterministic Studio-safe identifier from raw source name.

    - Replace illegal characters with underscore
    - Collapse repeated underscores
    - Ensure leading letter/underscore
    Does not invent semantics.
    """
    text = str(raw or "").strip()
    if not text:
        return "_"
    if is_valid_logix_identifier(text):
        return text
    out = _ILLEGAL_RE.sub("_", text)
    out = re.sub(r"_+", "_", out).strip("_")
    if not out:
        out = "SANITIZED"
    if out[0].isdigit():
        out = f"T_{out}"
    if not is_valid_logix_identifier(out):
        # Last resort: keep only alnum/underscore
        out = re.sub(r"[^A-Za-z0-9_]", "", out) or "SANITIZED"
        if out[0].isdigit():
            out = f"T_{out}"
    return out


def _collect_declared_tag_names(l5x_text: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'<Tag\b[^>]*\bName="([^"]+)"', l5x_text or ""):
        names.add(m.group(1))
    for m in re.finditer(r'<LocalTag\b[^>]*\bName="([^"]+)"', l5x_text or ""):
        names.add(m.group(1))
    return names


def sanitize_l5x_identifiers(l5x_text: str) -> tuple[str, IdentifierSanitizeReport]:
    """Rewrite Studio-invalid Tag/LocalTag names and matching operand roots.

    Collision policy: if two distinct raw names sanitize to the same emitted
    symbol, or emitted collides with an existing valid tag, mark COLLISION_REVIEW
    and do not merge — leave the original invalid name for quarantine/preflight
    soft handling only when we cannot emit a unique alias.
    """
    text = l5x_text or ""
    report = IdentifierSanitizeReport()
    declared = _collect_declared_tag_names(text)
    invalid = sorted(n for n in declared if not is_valid_logix_identifier(n))
    report.invalid_raw_found = len(invalid)
    if not invalid:
        return text, report

    # First pass: proposed sanitizations
    proposed: dict[str, str] = {}
    for raw in invalid:
        proposed[raw] = sanitize_logix_identifier(raw)

    # Detect collisions among proposed + existing valid names
    used: dict[str, str] = {n: n for n in declared if is_valid_logix_identifier(n)}
    final_map: dict[str, IdentifierMapEntry] = {}
    for raw, base in proposed.items():
        emitted = base
        collision = False
        if emitted in used and used[emitted] != raw:
            collision = True
            # Deterministic collision-safe alias
            n = 2
            while f"{base}_{n}" in used:
                n += 1
            emitted = f"{base}_{n}"
        # If still somehow invalid (shouldn't), withhold
        if not is_valid_logix_identifier(emitted):
            entry = IdentifierMapEntry(
                raw_name=raw,
                emitted_logix_name="N/A",
                reason_for_change="Unable to form Studio-safe unique identifier",
                collision_status="WITHHELD",
                disposition="WITHHELD",
            )
            report.withheld_count += 1
            report.entries.append(entry)
            final_map[raw] = entry
            continue
        entry = IdentifierMapEntry(
            raw_name=raw,
            emitted_logix_name=emitted,
            reason_for_change=(
                f"Raw identifier contains Studio-invalid characters; "
                f"deterministic sanitize {raw!r} → {emitted!r}"
                + (" (collision-safe suffix)" if collision else "")
            ),
            collision_status="COLLISION_RESOLVED" if collision else "OK",
            disposition="SANITIZED_FOR_EMIT",
        )
        if collision:
            report.collision_count += 1
        report.sanitized_count += 1
        used[emitted] = raw
        final_map[raw] = entry
        report.entries.append(entry)

    # Apply rewrites: longest raw first to avoid partial replacements
    out = text
    for raw in sorted(final_map.keys(), key=len, reverse=True):
        entry = final_map[raw]
        if entry.disposition != "SANITIZED_FOR_EMIT":
            continue
        emitted = entry.emitted_logix_name
        # Tag / LocalTag Name attributes
        out = re.sub(
            rf'(\b(?:Tag|LocalTag)\b[^>]*\bName="){re.escape(raw)}(")',
            rf"\1{emitted}\2",
            out,
        )
        # Operand roots in CDATA — word-boundary-ish: raw then . : [ ( or end
        out = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(raw)}(?=[.\[:(]|(?![A-Za-z0-9_]))",
            emitted,
            out,
        )

    return out, report


__all__ = [
    "IdentifierMapEntry",
    "IdentifierSanitizeReport",
    "is_valid_logix_identifier",
    "sanitize_logix_identifier",
    "sanitize_l5x_identifiers",
]
