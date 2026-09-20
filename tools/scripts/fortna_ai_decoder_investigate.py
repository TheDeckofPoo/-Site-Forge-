#!/usr/bin/env python3
"""Tool-driven Decoder Investigator session (Responses API).

ONE investigation session. Read-only tools only. Never implements rules.
Never assigns endpoints. Never mutates Site Forge / Autogen / compiler.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_decoder_schema import (  # noqa: E402
    DECODER_RULE_CANDIDATE_SCHEMA,
    FORBIDDEN_AUTHORITY_FIELDS,
    validate_decoder_rule_candidate,
)
from fortna_ai_readonly_tools import (  # noqa: E402
    FORBIDDEN_MUTATION_OPS,
    ReadOnlyViolation,
    SiteForgeReadOnlyContext,
    invoke_tool,
)

DEFAULT_MODEL = "gpt-5.6-terra"
MAX_TOOL_ROUNDS = 8
MAX_TOOL_CALLS = 30

INVESTIGATOR_TOOLS = [
    "get_project_identity",
    "get_configio_word",
    "get_configio_rows",
    "get_configio_binding_trace",
    "get_adapter",
    "get_module",
    "get_hardware_family",
    "get_source_rows",
    "get_failure_cluster",
    "get_physical_word_resolution_trace",
    "compare_candidate_rule_against_site",
    "get_io_claim",
    "get_neighbor_claims",
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_name() -> str:
    return (os.environ.get("SITEFORGE_AI_MODEL") or DEFAULT_MODEL).strip()


def _api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def _tool_schemas() -> list[dict[str, Any]]:
    """OpenAI function-tool schemas for Responses API custom tools."""
    # Keep schemas narrow; validation happens in our handlers.
    return [
        {
            "type": "function",
            "name": "get_project_identity",
            "description": "Return current project/machine identity and evidence_status.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "get_configio_word",
            "description": "Return Configio rows for one Octal_Word.",
            "parameters": {
                "type": "object",
                "properties": {"word": {"type": ["integer", "string"]}},
                "required": ["word"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_configio_rows",
            "description": "Filter Configio rows by optional bank/interface.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank": {"type": ["integer", "string"]},
                    "interface": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_configio_binding_trace",
            "description": (
                "Return the complete Site Forge binding attempt for one Configio word: "
                "Configio halves, candidates tried, accept/reject reasons, final result."
            ),
            "parameters": {
                "type": "object",
                "properties": {"word": {"type": ["integer", "string"]}},
                "required": ["word"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_adapter",
            "description": "Return one adapter from evidence by name/alias.",
            "parameters": {
                "type": "object",
                "properties": {"adapter_name": {"type": "string"}},
                "required": ["adapter_name"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_module",
            "description": "Return one module by adapter name and slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "adapter_name": {"type": "string"},
                    "slot": {"type": "integer"},
                },
                "required": ["adapter_name", "slot"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_hardware_family",
            "description": "Detect hardware family from a catalog string.",
            "parameters": {
                "type": "object",
                "properties": {"catalog": {"type": "string"}},
                "required": ["catalog"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_source_rows",
            "description": "Fetch one Conveyor or Configio source row by table and row index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "row": {"type": "integer"},
                },
                "required": ["source", "row"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_failure_cluster",
            "description": "Return one failure cluster by cluster_id if known.",
            "parameters": {
                "type": "object",
                "properties": {"cluster_id": {"type": "string"}},
                "required": ["cluster_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_physical_word_resolution_trace",
            "description": "Resolver hit/miss for one claim_id.",
            "parameters": {
                "type": "object",
                "properties": {"claim_id": {"type": "string"}},
                "required": ["claim_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "compare_candidate_rule_against_site",
            "description": "Schema-validate a DecoderRuleCandidate against current-site claims.",
            "parameters": {
                "type": "object",
                "properties": {"candidate": {"type": "object"}},
                "required": ["candidate"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_io_claim",
            "description": "Return one physical I/O claim by claim_id.",
            "parameters": {
                "type": "object",
                "properties": {"claim_id": {"type": "string"}},
                "required": ["claim_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_neighbor_claims",
            "description": "Neighbor physical claims filtered by word and/or adapter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "word": {"type": ["integer", "string"]},
                    "adapter": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    ]


def _dispatch_tool(ctx: SiteForgeReadOnlyContext, name: str, args: dict[str, Any]) -> Any:
    if name in FORBIDDEN_MUTATION_OPS or name not in INVESTIGATOR_TOOLS:
        raise ReadOnlyViolation(f"tool not allowed in investigation: {name}")
    if name == "get_project_identity":
        return invoke_tool(ctx, name)
    if name == "get_hardware_family":
        return invoke_tool(ctx, name, catalog=args.get("catalog") or "")
    if name == "get_configio_rows":
        kw = {}
        if "bank" in args and args["bank"] is not None:
            kw["bank"] = args["bank"]
        if "interface" in args and args["interface"] is not None:
            kw["interface"] = args["interface"]
        return invoke_tool(ctx, name, **kw)
    if name == "get_neighbor_claims":
        kw = {}
        if "word" in args:
            kw["word"] = args["word"]
        if "adapter" in args:
            kw["adapter"] = args["adapter"]
        if "limit" in args:
            kw["limit"] = args["limit"]
        return invoke_tool(ctx, name, **kw)
    if name == "compare_candidate_rule_against_site":
        return invoke_tool(ctx, name, candidate=args.get("candidate") or {})
    if name == "get_module":
        return invoke_tool(
            ctx, name, adapter_name=args.get("adapter_name") or "", slot=int(args.get("slot"))
        )
    # Single-arg tools
    key_map = {
        "get_configio_word": "word",
        "get_configio_binding_trace": "word",
        "get_adapter": "adapter_name",
        "get_failure_cluster": "cluster_id",
        "get_physical_word_resolution_trace": "claim_id",
        "get_io_claim": "claim_id",
    }
    if name == "get_source_rows":
        return invoke_tool(ctx, name, source=args.get("source") or "", row=int(args.get("row")))
    if name in key_map:
        return invoke_tool(ctx, name, **{key_map[name]: args.get(key_map[name])})
    raise KeyError(name)


def _extract_output_text(resp: Any) -> str:
    # SDK response object or dict
    if isinstance(resp, dict):
        if resp.get("output_text"):
            return str(resp["output_text"])
        # walk output items
        chunks = []
        for item in resp.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") in {"output_text", "text"}:
                        chunks.append(c.get("text") or "")
        return "\n".join(chunks)
    text = getattr(resp, "output_text", None)
    if text:
        return str(text)
    return ""


def _extract_tool_calls(resp: Any) -> list[dict[str, Any]]:
    calls = []
    output = getattr(resp, "output", None)
    if output is None and isinstance(resp, dict):
        output = resp.get("output")
    for item in output or []:
        typ = getattr(item, "type", None) if not isinstance(item, dict) else item.get("type")
        if typ in {"function_call", "tool_call", "custom_tool_call"}:
            if isinstance(item, dict):
                calls.append(item)
            else:
                calls.append(
                    {
                        "type": typ,
                        "call_id": getattr(item, "call_id", None) or getattr(item, "id", None),
                        "name": getattr(item, "name", None),
                        "arguments": getattr(item, "arguments", None),
                    }
                )
    return calls


def _usage_dict(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if usage is None and isinstance(resp, dict):
        usage = resp.get("usage")
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _forbid_authority(blob: str | dict[str, Any]) -> list[str]:
    text = blob if isinstance(blob, str) else json.dumps(blob)
    hits = []
    for f in FORBIDDEN_AUTHORITY_FIELDS | {
        "plc_channel",
        "READY",
        "Autogen",
        "compiler_accepted",
        "physical_endpoint",
    }:
        if f in text and f not in {"READY"}:  # READY checked as status separately
            hits.append(f)
    if '"status": "READY"' in text or '"status":"READY"' in text:
        hits.append("status=READY")
    return sorted(set(hits))


def run_mscatl_investigation(
    *,
    run_dir: Path,
    blind_packet: dict[str, Any],
    out_dir: Path,
    max_rounds: int = MAX_TOOL_ROUNDS,
    max_tool_calls: int = MAX_TOOL_CALLS,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    model = _model_name()
    key = _api_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY missing")

    from openai import OpenAI

    client = OpenAI(api_key=key)
    ctx = SiteForgeReadOnlyContext(run_dir=run_dir, machine="MSCATL_CP3", project="MSCATL_CP3")

    (out_dir / "blind_packet.json").write_text(
        json.dumps(blind_packet, indent=2), encoding="utf-8"
    )

    system = (
        "You are Site Forge Decoder Investigator. "
        "You investigate missing Fortna deterministic conventions. "
        "You are NOT an I/O endpoint resolver. "
        "Use only read-only tools. Current-site evidence only (MSCATL_CP3). "
        "Cite tool evidence. Search for counterexamples. "
        "Final answer MUST be a DecoderRuleCandidate JSON object. "
        "status must be CANDIDATE, REVIEW_REQUIRED, or INSUFFICIENT_EVIDENCE. "
        "Never return physical_endpoint, ai_derived, READY, Autogen, or PLC code."
    )
    user = blind_packet.get("problem_statement") or ""
    user += "\n\nSite summary:\n" + json.dumps(blind_packet.get("site_summary"), indent=2)
    user += (
        "\n\nYou may inspect configio_word_evidence in the attached packet via tools; "
        "prefer live tool calls over trusting summaries alone."
    )

    initial_request = {
        "model": model,
        "system": system,
        "user": user,
        "tools": [t["name"] for t in _tool_schemas()],
        "max_tool_rounds": max_rounds,
        "max_tool_calls": max_tool_calls,
        "investigation_id": "MSCATL_BINDING_INVESTIGATION_001",
    }
    (out_dir / "initial_request.json").write_text(
        json.dumps(initial_request, indent=2), encoding="utf-8"
    )

    transcript: list[dict[str, Any]] = []
    tool_calls_total = 0
    request_count = 0
    tool_rounds = 0
    usage_accum = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    t0 = time.perf_counter()

    # Build Responses API input
    input_items: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": user
            + "\n\nBlind packet site_summary and constraints are authoritative. "
            + "Packet path context: MSCATL_CP3 only.\n"
            + json.dumps(
                {
                    "constraints": blind_packet.get("constraints"),
                    "output_contract": blind_packet.get("output_contract"),
                    "representative_unresolved_claims": blind_packet.get(
                        "representative_unresolved_claims"
                    )[:12],
                    "configio_words_available": [
                        w.get("word") for w in (blind_packet.get("configio_word_evidence") or [])
                    ],
                },
                indent=2,
            ),
        },
    ]

    final_text = ""
    final_candidate: dict[str, Any] | None = None
    authority_hits: list[str] = []
    status = "INSUFFICIENT_EVIDENCE"

    while tool_rounds <= max_rounds and tool_calls_total <= max_tool_calls:
        request_count += 1
        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "tools": _tool_schemas(),
        }
        # Prefer structured final schema when no tools pending — still allow tools first
        try:
            resp = client.responses.create(**kwargs)
        except Exception as exc:
            transcript.append({"event": "api_error", "error": str(exc), "request": request_count})
            status = "INSUFFICIENT_EVIDENCE"
            break

        usage = _usage_dict(resp)
        for k in ("input_tokens", "output_tokens", "total_tokens"):
            if usage.get(k) is not None:
                usage_accum[k] = int(usage_accum.get(k) or 0) + int(usage[k] or 0)

        # Serialize response for transcript
        try:
            resp_dump = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        except Exception:
            resp_dump = {"output_text": _extract_output_text(resp), "usage": usage}
        (out_dir / f"model_response_{request_count:02d}.json").write_text(
            json.dumps(resp_dump, indent=2, default=str), encoding="utf-8"
        )
        transcript.append(
            {
                "event": "model_response",
                "request": request_count,
                "usage": usage,
            }
        )

        calls = _extract_tool_calls(resp)
        text = _extract_output_text(resp)
        if text:
            final_text = text
            authority_hits = _forbid_authority(text)

        if not calls:
            # Attempt parse candidate
            break

        tool_rounds += 1
        tool_outputs = []
        for call in calls:
            if tool_calls_total >= max_tool_calls:
                break
            tool_calls_total += 1
            name = call.get("name") or ""
            raw_args = call.get("arguments") or "{}"
            call_id = call.get("call_id") or call.get("id") or f"call_{tool_calls_total}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            try:
                result = _dispatch_tool(ctx, name, args if isinstance(args, dict) else {})
                ok = True
                err = None
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
                ok = False
                err = str(exc)
            tool_rec = {
                "event": "tool_call",
                "round": tool_rounds,
                "call_index": tool_calls_total,
                "call_id": call_id,
                "name": name,
                "arguments": args,
                "ok": ok,
                "error": err,
                "result": result,
            }
            transcript.append(tool_rec)
            (out_dir / f"tool_call_{tool_calls_total:03d}_{name}.json").write_text(
                json.dumps(tool_rec, indent=2, default=str), encoding="utf-8"
            )
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str)[:100000],
                }
            )

        # Continue conversation with function outputs
        # Append previous response output + tool results per Responses API pattern
        try:
            prev_id = getattr(resp, "id", None)
        except Exception:
            prev_id = None
        if prev_id:
            # Use previous_response_id continuation when available
            input_items = tool_outputs
            kwargs_next = {
                "model": model,
                "tools": _tool_schemas(),
                "previous_response_id": prev_id,
                "input": tool_outputs,
            }
            request_count += 1
            try:
                resp2 = client.responses.create(**kwargs_next)
            except Exception as exc:
                # Fallback: flatten into new input list
                transcript.append({"event": "continue_error", "error": str(exc)})
                input_items = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                    {
                        "role": "assistant",
                        "content": text or "(tool calls issued)",
                    },
                    {
                        "role": "user",
                        "content": "Tool results:\n"
                        + json.dumps(
                            [
                                {
                                    "name": t["name"],
                                    "arguments": t["arguments"],
                                    "result": t["result"],
                                }
                                for t in transcript
                                if t.get("event") == "tool_call"
                            ][-10:],
                            indent=2,
                            default=str,
                        )[:80000]
                        + "\n\nContinue investigation. When done, return ONLY DecoderRuleCandidate JSON.",
                    },
                ]
                continue

            usage = _usage_dict(resp2)
            for k in ("input_tokens", "output_tokens", "total_tokens"):
                if usage.get(k) is not None:
                    usage_accum[k] = int(usage_accum.get(k) or 0) + int(usage[k] or 0)
            try:
                resp_dump = resp2.model_dump() if hasattr(resp2, "model_dump") else dict(resp2)
            except Exception:
                resp_dump = {"output_text": _extract_output_text(resp2), "usage": usage}
            (out_dir / f"model_response_{request_count:02d}.json").write_text(
                json.dumps(resp_dump, indent=2, default=str), encoding="utf-8"
            )
            transcript.append({"event": "model_response", "request": request_count, "usage": usage})

            calls2 = _extract_tool_calls(resp2)
            text2 = _extract_output_text(resp2)
            if text2:
                final_text = text2
                authority_hits = _forbid_authority(text2)
            if not calls2:
                break
            # More tools — set resp for next loop iteration via previous_response_id path
            # by replacing input_items handling: loop continues with resp = resp2
            # Simplest: process calls2 inline like above then break/continue
            resp = resp2
            # fall through by not breaking — but while loop expects to call create again
            # Instead process remaining tool rounds by continuing with previous_response_id
            input_items = []  # will be replaced at top... actually restructure
            # For clarity: jump to process calls2 by assigning and continuing tool processing
            # We'll re-enter by setting a flag via recursive-style continue with stored resp
            # Easiest fix: don't use while for continuation; nest is messy.
            # Re-queue: set input_items empty and use a local loop for tool chains with previous_response_id
            chain_resp = resp2
            while True:
                more = _extract_tool_calls(chain_resp)
                if not more:
                    break
                if tool_rounds >= max_rounds or tool_calls_total >= max_tool_calls:
                    status = "INSUFFICIENT_EVIDENCE"
                    break
                tool_rounds += 1
                outs = []
                for call in more:
                    if tool_calls_total >= max_tool_calls:
                        break
                    tool_calls_total += 1
                    name = call.get("name") or ""
                    raw_args = call.get("arguments") or "{}"
                    call_id = call.get("call_id") or call.get("id") or f"call_{tool_calls_total}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        result = _dispatch_tool(ctx, name, args if isinstance(args, dict) else {})
                        ok = True
                        err = None
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc)}
                        ok = False
                        err = str(exc)
                    tool_rec = {
                        "event": "tool_call",
                        "round": tool_rounds,
                        "call_index": tool_calls_total,
                        "call_id": call_id,
                        "name": name,
                        "arguments": args,
                        "ok": ok,
                        "error": err,
                        "result": result,
                    }
                    transcript.append(tool_rec)
                    (out_dir / f"tool_call_{tool_calls_total:03d}_{name}.json").write_text(
                        json.dumps(tool_rec, indent=2, default=str), encoding="utf-8"
                    )
                    outs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(result, default=str)[:100000],
                        }
                    )
                request_count += 1
                try:
                    chain_resp = client.responses.create(
                        model=model,
                        tools=_tool_schemas(),
                        previous_response_id=getattr(chain_resp, "id", None),
                        input=outs,
                    )
                except Exception as exc:
                    transcript.append({"event": "chain_error", "error": str(exc)})
                    break
                usage = _usage_dict(chain_resp)
                for k in ("input_tokens", "output_tokens", "total_tokens"):
                    if usage.get(k) is not None:
                        usage_accum[k] = int(usage_accum.get(k) or 0) + int(usage[k] or 0)
                try:
                    dump = chain_resp.model_dump() if hasattr(chain_resp, "model_dump") else {}
                except Exception:
                    dump = {"output_text": _extract_output_text(chain_resp)}
                (out_dir / f"model_response_{request_count:02d}.json").write_text(
                    json.dumps(dump, indent=2, default=str), encoding="utf-8"
                )
                transcript.append(
                    {"event": "model_response", "request": request_count, "usage": usage}
                )
                t2 = _extract_output_text(chain_resp)
                if t2:
                    final_text = t2
                    authority_hits = _forbid_authority(t2)
            break

        # If we get here without previous_response_id path completing, continue while
        # with tool results embedded (already handled above with break)
        break

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    # Parse final candidate JSON from text
    parse_error = None
    if authority_hits:
        status = "REVIEW_REQUIRED"
        final_candidate = {
            "investigation_id": "MSCATL_BINDING_INVESTIGATION_001",
            "subsystem": "configio_to_hardware_binding",
            "failure_pattern": "AUTHORITY_VIOLATION",
            "affected_claim_ids": [],
            "affected_count": 0,
            "observed_facts": [f"Forbidden authority field(s) in response: {authority_hits}"],
            "evidence_refs": [],
            "candidate_rule_name": "rejected_authority_response",
            "candidate_rule_description": "Model returned forbidden compiler/endpoint authority concepts.",
            "proposed_inputs": [],
            "proposed_transformation": "NONE",
            "expected_outputs": [],
            "supporting_examples": [],
            "counterexamples": [],
            "ambiguities": [],
            "additional_evidence_needed": [],
            "tests_required": [],
            "scope": "MSCATL_CP3",
            "confidence": "LOW",
            "status": "REVIEW_REQUIRED",
        }
    else:
        try:
            # Extract JSON object from text
            t = final_text.strip()
            if "```" in t:
                import re

                m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
                if m:
                    t = m.group(1)
            start = t.find("{")
            end = t.rfind("}")
            if start >= 0 and end > start:
                final_candidate = json.loads(t[start : end + 1])
            else:
                raise ValueError("no JSON object in final text")
        except Exception as exc:
            parse_error = str(exc)
            status = "INSUFFICIENT_EVIDENCE"
            final_candidate = {
                "investigation_id": "MSCATL_BINDING_INVESTIGATION_001",
                "subsystem": "configio_to_hardware_binding",
                "failure_pattern": "UNPARSEABLE_OR_INCOMPLETE",
                "affected_claim_ids": [],
                "affected_count": 0,
                "observed_facts": [f"parse_error: {parse_error}", f"raw_text_len: {len(final_text)}"],
                "evidence_refs": [],
                "candidate_rule_name": "none",
                "candidate_rule_description": "Model did not return a parseable DecoderRuleCandidate.",
                "proposed_inputs": [],
                "proposed_transformation": "NONE",
                "expected_outputs": [],
                "supporting_examples": [],
                "counterexamples": [],
                "ambiguities": ["Model ended without structured candidate"],
                "additional_evidence_needed": [],
                "tests_required": [],
                "scope": "MSCATL_CP3",
                "confidence": "LOW",
                "status": "INSUFFICIENT_EVIDENCE",
            }

    schema_validation = validate_decoder_rule_candidate(final_candidate or {})
    if not authority_hits:
        status = str((final_candidate or {}).get("status") or status)
        if not schema_validation.get("ok"):
            # Keep model status if valid enum, else REVIEW
            if status not in {"CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"}:
                status = "REVIEW_REQUIRED"

    (out_dir / "final_decoder_rule_candidate.json").write_text(
        json.dumps(final_candidate, indent=2), encoding="utf-8"
    )
    (out_dir / "schema_validation.json").write_text(
        json.dumps(schema_validation, indent=2), encoding="utf-8"
    )
    (out_dir / "raw_final_text.txt").write_text(final_text or "", encoding="utf-8")
    usage_path = {
        "model": model,
        "reasoning_setting": os.environ.get("SITEFORGE_AI_REASONING") or "default/unspecified",
        "request_count": request_count,
        "tool_rounds": tool_rounds,
        "tool_calls": tool_calls_total,
        "latency_ms": latency_ms,
        "usage": usage_accum,
        "authority_hits": authority_hits,
        "parse_error": parse_error,
    }
    (out_dir / "usage.json").write_text(json.dumps(usage_path, indent=2), encoding="utf-8")
    (out_dir / "transcript.json").write_text(
        json.dumps(transcript, indent=2, default=str), encoding="utf-8"
    )

    summary = {
        "investigation_id": "MSCATL_BINDING_INVESTIGATION_001",
        "final_status": status,
        "candidate_rule_name": (final_candidate or {}).get("candidate_rule_name"),
        "candidate_rule_description": (final_candidate or {}).get("candidate_rule_description"),
        "confidence": (final_candidate or {}).get("confidence"),
        "schema_ok": schema_validation.get("ok"),
        "schema_reasons": schema_validation.get("reasons"),
        "tools_called": [
            t.get("name") for t in transcript if t.get("event") == "tool_call"
        ],
        "tool_call_count": tool_calls_total,
        "tool_rounds": tool_rounds,
        "request_count": request_count,
        "model": model,
        "latency_ms": latency_ms,
        "usage": usage_accum,
        "implemented_rule": False,
        "compiler_touched": False,
        "live_api_called": True,
    }
    (out_dir / "investigation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return {
        "ok": True,
        "summary": summary,
        "candidate": final_candidate,
        "schema_validation": schema_validation,
        "out_dir": str(out_dir),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MSCATL Decoder Investigator session")
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN",
    )
    ap.add_argument(
        "--blind-packet",
        type=Path,
        default=REPO_ROOT
        / "exports"
        / "ai-io"
        / "investigations"
        / "mscatl_binding_blind_packet.json",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT
        / "exports"
        / "ai-io"
        / "investigations"
        / "MSCATL_BINDING_001",
    )
    ap.add_argument("--max-rounds", type=int, default=MAX_TOOL_ROUNDS)
    ap.add_argument("--max-tool-calls", type=int, default=MAX_TOOL_CALLS)
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="Rebuild dossier/blind packet and validate gate; no API call",
    )
    args = ap.parse_args(argv)

    # Always refresh dossier/packets first
    from fortna_configio_binding_trace import (
        build_mscatl_binding_dossier,
        build_mscatl_blind_packet,
        build_mscatl_investigation_packet,
    )

    dossier = build_mscatl_binding_dossier(args.run_dir, "MSCATL_CP3")
    inv = REPO_ROOT / "exports" / "ai-io" / "investigations"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / "mscatl_binding_dossier.json").write_text(
        json.dumps(dossier, indent=2), encoding="utf-8"
    )
    eng = build_mscatl_investigation_packet(dossier)
    (inv / "mscatl_binding_investigation_packet.json").write_text(
        json.dumps(eng, indent=2), encoding="utf-8"
    )
    blind = build_mscatl_blind_packet(dossier)
    (inv / "mscatl_binding_blind_packet.json").write_text(
        json.dumps(blind, indent=2), encoding="utf-8"
    )
    ss = dossier["site_summary"]
    gate = (
        ss.get("physical_claims") == 256
        and ss.get("proven") == 0
        and ss.get("needs_resolution") == 256
        and ss.get("physical_resolution_failure") == 256
        and ss.get("conservation") == "PASS"
        and ss.get("evidence_status") == "NEEDS_RESOLUTION"
    )
    print(json.dumps({"packet_gate_pass": gate, "site_summary": ss}, indent=2))
    if not gate:
        return 2
    if args.prepare_only:
        return 0

    result = run_mscatl_investigation(
        run_dir=args.run_dir,
        blind_packet=blind,
        out_dir=args.out_dir,
        max_rounds=args.max_rounds,
        max_tool_calls=args.max_tool_calls,
    )
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
