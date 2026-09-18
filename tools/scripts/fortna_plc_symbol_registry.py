#!/usr/bin/env python3
"""Canonical PLC symbol registry — shared tag ownership (Gate C).

same identity + same semantics → one declaration, many references
same name + incompatible semantics → FATAL with both provenance chains
same name + ambiguous ownership → REVIEW/FATAL

Does not silently skip duplicates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlcSymbol:
    name: str
    scope: str  # controller | program:<ProgramName>
    datatype: str
    owner: str
    semantic_role: str = ""
    source_model: str = ""
    provenance: str = "PROVEN"
    block: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class PlcSymbolRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], PlcSymbol] = {}
        # name → list of scopes registered
        self._scopes_by_name: dict[str, list[str]] = {}
        self.collisions: list[dict[str, Any]] = []
        self.promotions: list[dict[str, Any]] = []

    @staticmethod
    def _parse_block(block: str) -> tuple[str, str]:
        nm = re.search(r'<Tag Name="([^"]+)"', block or "")
        dt = re.search(r'\bDataType="([^"]+)"', block or "")
        return (nm.group(1) if nm else ""), (dt.group(1) if dt else "")

    def register(
        self,
        *,
        name: str | None = None,
        scope: str,
        datatype: str | None = None,
        owner: str,
        semantic_role: str = "",
        source_model: str = "",
        provenance: str = "PROVEN",
        block: str = "",
    ) -> dict[str, Any]:
        """Register a declaration. Returns {ok, action, symbol?, collision?}."""
        if block and not name:
            name, datatype = self._parse_block(block)
        name = (name or "").strip()
        datatype = (datatype or "").strip()
        if not name:
            return {"ok": False, "action": "skip_empty"}

        key = (name, scope)
        existing = self._by_key.get(key)
        if existing:
            if (existing.datatype or "").upper() == (datatype or "").upper() or not datatype:
                return {
                    "ok": True,
                    "action": "reuse",
                    "symbol": existing,
                    "note": "same identity+scope+dtype — single declaration",
                }
            collision = {
                "severity": "FATAL",
                "name": name,
                "scope": scope,
                "reason": "incompatible_datatype",
                "existing": {
                    "owner": existing.owner,
                    "datatype": existing.datatype,
                    "semantic_role": existing.semantic_role,
                    "source_model": existing.source_model,
                    "provenance": existing.provenance,
                },
                "incoming": {
                    "owner": owner,
                    "datatype": datatype,
                    "semantic_role": semantic_role,
                    "source_model": source_model,
                    "provenance": provenance,
                },
            }
            self.collisions.append(collision)
            return {"ok": False, "action": "fatal_collision", "collision": collision}

        # Same name in different scopes: Logix allows program shadowing, but
        # shared BOOL roles like Sorter_At_Speed must be controller-owned once.
        other_scopes = list(self._scopes_by_name.get(name) or [])
        if other_scopes and scope.startswith("program:") and any(
            s == "controller" for s in other_scopes
        ):
            # Prefer existing controller declaration — do not add program decl
            return {
                "ok": True,
                "action": "reference_controller",
                "note": "controller already owns declaration; program should reference only",
            }
        if other_scopes and scope == "controller" and any(
            s.startswith("program:") for s in other_scopes
        ):
            # Controller registration wins; caller should strip program decl
            self.promotions.append(
                {
                    "name": name,
                    "from_scopes": [s for s in other_scopes if s.startswith("program:")],
                    "to_scope": "controller",
                    "owner": owner,
                    "reason": "shared_tag_promoted_to_controller",
                }
            )

        sym = PlcSymbol(
            name=name,
            scope=scope,
            datatype=datatype,
            owner=owner,
            semantic_role=semantic_role,
            source_model=source_model,
            provenance=provenance,
            block=block,
        )
        self._by_key[key] = sym
        self._scopes_by_name.setdefault(name, []).append(scope)
        return {"ok": True, "action": "declare", "symbol": sym}

    def controller_blocks(self) -> list[str]:
        return [
            s.block
            for s in self._by_key.values()
            if s.scope == "controller" and s.block
        ]

    def report(self) -> dict[str, Any]:
        return {
            "declared": len(self._by_key),
            "unique_names": len(self._scopes_by_name),
            "collisions": self.collisions,
            "promotions": self.promotions,
            "fatal": [c for c in self.collisions if c.get("severity") == "FATAL"],
        }


# Shared logical BOOL roles that must be controller-scoped once (oracle-proven).
CONTROLLER_OWNED_ROLES = (
    "_Sorter_At_Speed",
)


def is_controller_owned_shared_tag(name: str) -> bool:
    n = name or ""
    return any(n.endswith(suf) for suf in CONTROLLER_OWNED_ROLES)


def strip_program_tags(program_xml: str, names: set[str]) -> str:
    """Remove Tag declarations for names from <Program><Tags>…</Tags>."""
    if not names or not program_xml:
        return program_xml

    def _tags_repl(m: re.Match) -> str:
        body = m.group(1)
        kept = []
        for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", body, re.S):
            block = tm.group(0)
            nm = re.search(r'Tag Name="([^"]+)"', block)
            if nm and nm.group(1) in names:
                continue
            kept.append(block)
        return f"<Tags>{''.join(kept)}</Tags>"

    # Only the program's own Tags block (first Tags after <Program)
    return re.sub(
        r"<Tags>(.*?)</Tags>",
        _tags_repl,
        program_xml,
        count=1,
        flags=re.S,
    )


def extract_program_tag_blocks(program_xml: str) -> list[str]:
    m = re.search(r"<Program[^>]*>\s*<Tags>(.*?)</Tags>", program_xml or "", re.S)
    if not m:
        return []
    return [tm.group(0) for tm in re.finditer(r"<Tag\b[^>]*>.*?</Tag>", m.group(1), re.S)]
