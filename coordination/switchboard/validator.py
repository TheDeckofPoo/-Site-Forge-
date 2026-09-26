"""Minimal JSON Schema validator (stdlib only).

Implements the subset of JSON Schema draft 2020-12 used by the Switchboard
schemas: type, required, properties, additionalProperties, items, enum,
const, pattern, minLength, minItems, minimum, uniqueItems, format
(date-time only), $ref (local ``#/$defs/...``), anyOf, oneOf, allOf,
if/then.  Unknown keywords are ignored (as the spec permits for annotations).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(t)
    return py is not None and isinstance(value, py)


def _check_datetime(s: str) -> bool:
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return "T" in s
    except ValueError:
        return False


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref!r} (only local refs)")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def iter_errors(instance: Any, schema: dict, root: dict | None = None, path: str = "$"):
    """Yield human-readable error strings."""
    root = root if root is not None else schema
    if schema is True or schema == {}:
        return
    if schema is False:
        yield f"{path}: not allowed"
        return
    if "$ref" in schema:
        yield from iter_errors(instance, _resolve(schema["$ref"], root), root, path)
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_is_type(instance, x) for x in types):
            yield f"{path}: expected type {'/'.join(types)}, got {type(instance).__name__}"
            return
    if "const" in schema and instance != schema["const"]:
        yield f"{path}: must equal {schema['const']!r}"
    if "enum" in schema and instance not in schema["enum"]:
        yield f"{path}: {instance!r} not one of {schema['enum']}"
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            yield f"{path}: shorter than {schema['minLength']}"
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            yield f"{path}: {instance!r} does not match /{schema['pattern']}/"
        if schema.get("format") == "date-time" and not _check_datetime(instance):
            yield f"{path}: {instance!r} is not an ISO-8601 date-time"
    if _is_type(instance, "number") and "minimum" in schema and instance < schema["minimum"]:
        yield f"{path}: {instance} < minimum {schema['minimum']}"
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            yield f"{path}: fewer than {schema['minItems']} items"
        if schema.get("uniqueItems"):
            seen = [json.dumps(x, sort_keys=True) for x in instance]
            if len(seen) != len(set(seen)):
                yield f"{path}: items not unique"
        if "items" in schema:
            for i, item in enumerate(instance):
                yield from iter_errors(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                yield f"{path}: missing required field '{req}'"
        props = schema.get("properties", {})
        for k, v in instance.items():
            if k in props:
                yield from iter_errors(v, props[k], root, f"{path}.{k}")
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    yield f"{path}: unexpected field '{k}'"
                elif isinstance(ap, dict):
                    yield from iter_errors(v, ap, root, f"{path}.{k}")
    for sub in schema.get("allOf", []):
        yield from iter_errors(instance, sub, root, path)
    if "anyOf" in schema:
        if not any(not list(iter_errors(instance, s, root, path)) for s in schema["anyOf"]):
            yield f"{path}: does not match any allowed form"
    if "oneOf" in schema:
        n = sum(1 for s in schema["oneOf"] if not list(iter_errors(instance, s, root, path)))
        if n != 1:
            yield f"{path}: must match exactly one allowed form (matched {n})"
    if "if" in schema:
        if not list(iter_errors(instance, schema["if"], root, path)):
            if "then" in schema:
                yield from iter_errors(instance, schema["then"], root, path)
        elif "else" in schema:
            yield from iter_errors(instance, schema["else"], root, path)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate(instance: Any, schema_name: str) -> list[str]:
    schema = load_schema(schema_name)
    return list(iter_errors(instance, schema, schema))
