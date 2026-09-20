#!/usr/bin/env python3
"""Read-only Site Forge AI tool interfaces (Stage 1 design).

These tools expose narrow evidence lookups for the decoder investigator.
They MUST NOT mutate Site Forge state, Autogen, compiler input, or L5X.

Live OpenAI tool-calling is NOT wired yet — this module defines the contract
and a local in-process implementation for tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fortna_ai_failure_cluster import cluster_unresolved_claims
from fortna_ai_io_evidence import build_evidence_bundle
from fortna_configio_binding_trace import get_configio_binding_trace as _binding_trace
from fortna_physical_word_resolver import PhysicalWordResolver


class ReadOnlyViolation(RuntimeError):
    """Raised if a mutation is attempted through the AI tool surface."""


@dataclass
class SiteForgeReadOnlyContext:
    """Immutable snapshot for one investigation session."""

    run_dir: Path
    machine: str
    project: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    _mutation_log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        if not self.evidence:
            self.evidence = build_evidence_bundle(
                self.run_dir, self.machine, project=self.project
            )

    def _deny_write(self, op: str) -> None:
        self._mutation_log.append(op)
        raise ReadOnlyViolation(f"AI tools are read-only; refused: {op}")


def get_project_identity(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    return {
        "project": ctx.evidence.get("project") or ctx.project,
        "machine": ctx.machine,
        "run_dir": str(ctx.run_dir),
        "evidence_status": ctx.evidence.get("evidence_status"),
    }


def get_machine(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    return {"machine": ctx.machine, "project": ctx.evidence.get("project")}


def get_io_claim(ctx: SiteForgeReadOnlyContext, claim_id: str) -> dict[str, Any] | None:
    for c in ctx.evidence.get("raw_claims") or []:
        if c.get("claim_id") == claim_id:
            return dict(c)
    return None


def get_configio_word(ctx: SiteForgeReadOnlyContext, word: int | str) -> list[dict[str, Any]]:
    try:
        w = int(float(str(word)))
    except (TypeError, ValueError):
        return []
    out = []
    for r in ctx.evidence.get("configio") or []:
        try:
            ow = int(r.get("Octal_Word") if "Octal_Word" in r else r.get("octal_word"))
        except (TypeError, ValueError):
            continue
        if ow == w:
            out.append(dict(r))
    return out


def get_configio_rows(ctx: SiteForgeReadOnlyContext, **filters: Any) -> list[dict[str, Any]]:
    rows = list(ctx.evidence.get("configio") or [])
    if "bank" in filters:
        want = str(filters["bank"])
        rows = [
            r
            for r in rows
            if str(r.get("Bank") if r.get("Bank") is not None else r.get("bank")) == want
        ]
    if "interface" in filters:
        want = str(filters["interface"]).upper()
        rows = [
            r
            for r in rows
            if str(r.get("Interface") or r.get("interface") or "").upper() == want
        ]
    return rows


def get_adapter(ctx: SiteForgeReadOnlyContext, adapter_name: str) -> dict[str, Any] | None:
    want = (adapter_name or "").strip().upper()
    for ad in (ctx.evidence.get("eipcfg") or {}).get("adapters") or []:
        rio = str(ad.get("rio_name") or ad.get("eipcfg_name") or "").upper()
        if rio == want:
            return dict(ad)
    return None


def get_module(
    ctx: SiteForgeReadOnlyContext, adapter_name: str, slot: int
) -> dict[str, Any] | None:
    ad = get_adapter(ctx, adapter_name)
    if not ad:
        return None
    for m in ad.get("modules") or []:
        try:
            if int(m.get("slot")) == int(slot):
                return dict(m)
        except (TypeError, ValueError):
            continue
    return None


def get_neighbor_claims(
    ctx: SiteForgeReadOnlyContext,
    *,
    word: int | str | None = None,
    adapter: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    out = []
    for c in ctx.evidence.get("raw_claims") or []:
        if word is not None and str(c.get("word")) != str(word):
            continue
        if adapter and str(c.get("adapter") or "").upper() != adapter.upper():
            continue
        out.append(
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "disposition": c.get("deterministic_disposition"),
                "physical_address": c.get("physical_address"),
            }
        )
        if len(out) >= limit:
            break
    return out


def get_proven_io_examples(
    ctx: SiteForgeReadOnlyContext, *, limit: int = 20
) -> list[dict[str, Any]]:
    out = []
    for c in ctx.evidence.get("raw_claims") or []:
        if c.get("deterministic_disposition") != "ASSIGNED":
            continue
        out.append(
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "physical_address": c.get("physical_address"),
            }
        )
        if len(out) >= limit:
            break
    return out


def get_failure_cluster(
    ctx: SiteForgeReadOnlyContext, cluster_id: str
) -> dict[str, Any] | None:
    clustered = cluster_unresolved_claims(
        ctx.evidence.get("raw_claims") or [], evidence=ctx.evidence
    )
    for cl in clustered.get("clusters") or []:
        if cl.get("cluster_id") == cluster_id:
            return cl
    return None


def get_source_rows(
    ctx: SiteForgeReadOnlyContext, source: str, row: int
) -> dict[str, Any] | None:
    src = (source or "").lower()
    if "conveyor" in src:
        for r in ctx.evidence.get("conveyor") or []:
            if int(r.get("row") or -1) == int(row):
                return dict(r)
    if "configio" in src:
        for r in ctx.evidence.get("configio") or []:
            if int(r.get("row") or -1) == int(row):
                return dict(r)
    return None


def get_hardware_family(ctx: SiteForgeReadOnlyContext, catalog: str) -> str:
    from fortna_hardware_family import detect_family_from_catalog

    return detect_family_from_catalog(catalog)


def get_physical_word_resolution_trace(
    ctx: SiteForgeReadOnlyContext, claim_id: str
) -> dict[str, Any]:
    claim = get_io_claim(ctx, claim_id)
    if not claim:
        return {"ok": False, "error": "claim_id not found"}
    resolver = PhysicalWordResolver(ctx.run_dir, ctx.machine)
    hit = resolver.resolve(claim.get("word"), claim.get("bit"))
    return {
        "ok": True,
        "claim_id": claim_id,
        "word": claim.get("word"),
        "bit": claim.get("bit"),
        "resolver_hit": hit,
        "deterministic_disposition": claim.get("deterministic_disposition"),
    }


def get_configio_binding_trace(ctx: SiteForgeReadOnlyContext, word: int | str) -> dict[str, Any]:
    """Read-only Configio word → hardware binding attempt log."""
    return _binding_trace(ctx.run_dir, ctx.machine, word)


def compare_candidate_rule_against_site(
    ctx: SiteForgeReadOnlyContext, candidate: dict[str, Any]
) -> dict[str, Any]:
    """Read-only: validate schema + report affected claim coverage. No mutation."""
    from fortna_ai_decoder_schema import validate_decoder_rule_candidate

    v = validate_decoder_rule_candidate(candidate)
    ids = set(candidate.get("affected_claim_ids") or [])
    present = {
        c.get("claim_id")
        for c in (ctx.evidence.get("raw_claims") or [])
        if c.get("claim_id") in ids
    }
    return {
        "schema_ok": v["ok"],
        "compiler_authority": False,
        "creates_ready": False,
        "reasons": v["reasons"],
        "affected_present": sorted(present),
        "affected_missing": sorted(ids - present),
    }


# Explicit mutation stubs — always refuse
def _refuse_mutation(ctx: SiteForgeReadOnlyContext, *args: Any, **kwargs: Any) -> None:
    ctx._deny_write(kwargs.get("op") or args[0] if args else "mutation")


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_project_identity": get_project_identity,
    "get_machine": get_machine,
    "get_io_claim": get_io_claim,
    "get_configio_word": get_configio_word,
    "get_configio_rows": get_configio_rows,
    "get_adapter": get_adapter,
    "get_module": get_module,
    "get_neighbor_claims": get_neighbor_claims,
    "get_proven_io_examples": get_proven_io_examples,
    "get_failure_cluster": get_failure_cluster,
    "get_source_rows": get_source_rows,
    "get_hardware_family": get_hardware_family,
    "get_physical_word_resolution_trace": get_physical_word_resolution_trace,
    "get_configio_binding_trace": get_configio_binding_trace,
    "compare_candidate_rule_against_site": compare_candidate_rule_against_site,
}

# Documented as non-tools — any attempt must fail
FORBIDDEN_MUTATION_OPS = frozenset(
    {
        "save_hardware_io_channel",
        "write_autogen",
        "accept_assignment",
        "generate_plc",
        "edit_engineer_selection",
        "modify_compiler",
        "write_l5x",
    }
)


def invoke_tool(ctx: SiteForgeReadOnlyContext, name: str, **kwargs: Any) -> Any:
    if name in FORBIDDEN_MUTATION_OPS:
        ctx._deny_write(name)
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"unknown read-only tool: {name}")
    return fn(ctx, **kwargs) if name != "get_project_identity" else fn(ctx)
