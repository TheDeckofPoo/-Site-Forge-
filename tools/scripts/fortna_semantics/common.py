#!/usr/bin/env python3
"""CP4 shared semantic types — no subsystem interpretation logic."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FactStatus(str, Enum):
    """Deterministic semantic states (no numeric confidence)."""

    PROVEN = "PROVEN"  # Directly supported by CP3 edge + schema/runtime evidence
    DERIVED = "DERIVED"  # Deterministic composition of PROVEN facts/rules (not speculation)
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # Evidence incomplete; engineer must decide
    UNKNOWN = "UNKNOWN"  # Not established by Fortna source/RUN evidence
    CONFLICT = "CONFLICT"  # Contradictory proven evidence


class AdapterStatus(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class RuleClass(str, Enum):
    SOURCE_PROVEN = "SOURCE_PROVEN"
    RUN_PROVEN = "RUN_PROVEN"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class SemanticFact:
    semanticType: str
    identity: str
    value: Any
    status: str
    sourceMenu: str | None = None
    sourceRecord: int | None = None
    sourceColumn: str | None = None
    sourceRawValue: str | None = None
    cp3EdgeKey: str | None = None
    targetMenu: str | None = None
    targetRecord: int | None = None
    targetIdentity: str | None = None
    provenance: str = RuleClass.RUN_PROVEN.value
    evidence: list[dict[str, Any]] = field(default_factory=list)
    interpretationRule: str | None = None
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdapterResult:
    adapter: str
    status: str
    objects: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    proofs: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "status": self.status,
            "objects": self.objects,
            "facts": self.facts,
            "diagnostics": self.diagnostics,
            "counts": self.counts,
            "proofs": self.proofs,
            "notes": self.notes,
        }


def edge_key(e: dict[str, Any]) -> str:
    return (
        f"{e.get('sourceMenu')}#{e.get('sourceRecord')}."
        f"{e.get('sourceColumn')}->{e.get('targetMenu')}#"
        f"{e.get('targetRecord')}:{e.get('targetIdentity')}"
    )


def index_cp3_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Build immutable indexes over a CP3 graph for adapters."""
    rels = graph.get("relationships") or []
    by_source_menu: dict[str, list[dict[str, Any]]] = {}
    by_target_identity: dict[str, list[dict[str, Any]]] = {}
    record_edges: list[dict[str, Any]] = []
    for e in rels:
        if e.get("scope") != "RECORD":
            continue
        record_edges.append(e)
        sm = e.get("sourceMenu") or ""
        by_source_menu.setdefault(sm, []).append(e)
        tid = e.get("targetIdentity")
        tm = e.get("targetMenu")
        if tid and tm:
            by_target_identity.setdefault(f"{tm}::{tid}", []).append(e)
    return {
        "graph": graph,
        "recordEdges": record_edges,
        "bySourceMenu": by_source_menu,
        "byTargetIdentity": by_target_identity,
        "reverse": graph.get("reverseRelationships") or {},
        "statistics": graph.get("statistics") or {},
        "acName": graph.get("acName"),
        "runDir": graph.get("runDir"),
    }


def group_edges_by_record(edges: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    """recordIndex -> {columnName -> edge} (last wins if duplicates)."""
    out: dict[int, dict[str, dict[str, Any]]] = {}
    for e in edges:
        rec = e.get("sourceRecord")
        if rec is None:
            continue
        out.setdefault(int(rec), {})[str(e.get("sourceColumn"))] = e
    return out


def fact_from_edge(
    *,
    semantic_type: str,
    identity: str,
    value: Any,
    edge: dict[str, Any],
    status: str = FactStatus.PROVEN.value,
    interpretation_rule: str,
    provenance: str = RuleClass.RUN_PROVEN.value,
    diagnostics: list[str] | None = None,
) -> SemanticFact:
    return SemanticFact(
        semanticType=semantic_type,
        identity=identity,
        value=value,
        status=status,
        sourceMenu=edge.get("sourceMenu"),
        sourceRecord=edge.get("sourceRecord"),
        sourceColumn=edge.get("sourceColumn"),
        sourceRawValue=edge.get("sourceRawValue"),
        cp3EdgeKey=edge_key(edge),
        targetMenu=edge.get("targetMenu"),
        targetRecord=edge.get("targetRecord"),
        targetIdentity=edge.get("targetIdentity"),
        provenance=provenance,
        evidence=list(edge.get("evidence") or []),
        interpretationRule=interpretation_rule,
        diagnostics=list(diagnostics or []),
    )
