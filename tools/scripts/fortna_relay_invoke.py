#!/usr/bin/env python3
"""Relay invocation adapter — provider-independent shadow-mode interface.

Reuses Site Forge OpenAI env conventions when available.
Startup / default path makes NO AI call.
Never writes production endpoints.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from fortna_relay_knowledge_loader import build_relay_context_bundle
from fortna_relay_schema import validate_relay_result


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_key_available() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def _model_name() -> str:
    return (os.environ.get("SITEFORGE_RELAY_MODEL")
            or os.environ.get("SITEFORGE_AI_MODEL")
            or "gpt-5.6-terra").strip()


def build_relay_messages(
    *,
    context_bundle: dict[str, Any],
    evidence_packet: dict[str, Any],
) -> list[dict[str, str]]:
    """Assemble chat messages from durable knowledge + evidence packet."""
    system = (
        "You are Relay — Site Forge I/O Evidence Specialist.\n"
        "Authority: OBSERVE + PROPOSE only. Never write production endpoints.\n"
        "Return ONE JSON object matching RELAY_OUTPUT_SCHEMA.\n"
        "Panel-local physical mapping is mandatory.\n"
        "Set cross_panel_physical_mapping_used=false for valid claims.\n"
        "WHEN EVIDENCE STOPS, RELAY STOPS.\n\n"
        + str(context_bundle.get("context_text") or "")[:120000]
    )
    user = (
        "Analyze this panel-local evidence packet and return a single RelayCaseResult JSON object.\n"
        "Do not invent endpoints. Prefer REVIEW_REQUIRED when proof is incomplete.\n\n"
        + json.dumps(evidence_packet, indent=2, default=str)[:60000]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _call_openai_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Call OpenAI chat/completions; return parsed JSON or raise."""
    # Lazy import — tests without openai must still import this module
    from openai import OpenAI  # type: ignore

    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=key)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=_model_name(),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    content = (resp.choices[0].message.content or "").strip()
    usage = getattr(resp, "usage", None)
    meta = {
        "provider": "openai",
        "model": _model_name(),
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
    }
    data = json.loads(content)
    return {"raw": data, "meta": meta}


def invoke_relay(
    evidence_packet: dict[str, Any],
    *,
    repo_root: Any = None,
    context_bundle: dict[str, Any] | None = None,
    enabled: bool = False,
    transport: Callable[[list[dict[str, str]]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Invoke Relay in shadow mode.

    enabled=False → no AI call (default).
    transport: injectable for tests / alternate providers.
    """
    if not enabled:
        return {
            "ok": False,
            "status": "RELAY_DISABLED",
            "shadow_mode": True,
            "production_authority": False,
            "ai_call": False,
            "result": None,
            "validation": None,
            "meta": {"enabled": False},
            "timestamp": _ts(),
        }

    bundle = context_bundle or build_relay_context_bundle(repo_root=repo_root)
    if not bundle.get("ok"):
        return {
            "ok": False,
            "status": "RELAY_UNAVAILABLE",
            "shadow_mode": True,
            "production_authority": False,
            "ai_call": False,
            "result": None,
            "validation": None,
            "meta": {"knowledge_status": bundle.get("status"), "errors": bundle.get("errors")},
            "knowledge_bundle_hash": bundle.get("bundle_hash"),
            "timestamp": _ts(),
        }

    messages = build_relay_messages(context_bundle=bundle, evidence_packet=evidence_packet)
    caller = transport
    if caller is None:
        if not api_key_available():
            return {
                "ok": False,
                "status": "RELAY_UNAVAILABLE",
                "shadow_mode": True,
                "production_authority": False,
                "ai_call": False,
                "result": None,
                "validation": None,
                "meta": {"reason": "API_KEY_MISSING"},
                "knowledge_bundle_hash": bundle.get("bundle_hash"),
                "timestamp": _ts(),
            }
        caller = _call_openai_json

    try:
        raw_pack = caller(messages)
        raw = raw_pack.get("raw") if isinstance(raw_pack, dict) and "raw" in raw_pack else raw_pack
        meta = raw_pack.get("meta") if isinstance(raw_pack, dict) else {}
    except Exception as exc:
        return {
            "ok": False,
            "status": "RELAY_UNAVAILABLE",
            "shadow_mode": True,
            "production_authority": False,
            "ai_call": True,
            "result": None,
            "validation": None,
            "meta": {"error": str(exc)[:400]},
            "knowledge_bundle_hash": bundle.get("bundle_hash"),
            "timestamp": _ts(),
        }

    validation = validate_relay_result(raw)
    return {
        "ok": bool(validation.get("ok")),
        "status": validation.get("status") if not validation.get("ok") else "RELAY_COMPLETE",
        "shadow_mode": True,
        "production_authority": False,
        "ai_call": True,
        "result": validation.get("normalized") if validation.get("ok") else raw,
        "validation": validation,
        "meta": meta or {},
        "knowledge_bundle_hash": bundle.get("bundle_hash"),
        "knowledge_pack_version": bundle.get("knowledge_pack_version"),
        "timestamp": _ts(),
        "endpoint_written": False,
    }
