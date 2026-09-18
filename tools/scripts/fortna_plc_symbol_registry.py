#!/usr/bin/env python3
"""Canonical PLC symbol registry — shared tag ownership + CP_I/CP_O classes.

Declaration ownership (historic Gate C):
  same identity + same semantics → one declaration, many references
  same name + incompatible semantics → FATAL with both provenance chains
  same name + ambiguous ownership → REVIEW/FATAL

IO_MAP symbol classes (Gate G):
  Every CP_I/CP_O operand resolves to a semantic class with provenance.
  Physical endpoint is required only for discrete PHYSICAL_INPUT / PHYSICAL_OUTPUT.
  NETWORK_DEVICE_* / LOGICAL_SIGNAL never invent a physical endpoint.

Unknown symbol policy (Gate H):
  NO auto BOOL, fake modules, TRUE/FALSE, NOP, silent omit, or name-prefix guesses.
  Disposition: FATAL | ENGINEER_REQUIRED | OPTIONAL | ABSENT_REFERENCE (with WHY).

Does not silently skip duplicates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Gate G — CP_I / CP_O operand semantic classes
PHYSICAL_INPUT = "PHYSICAL_INPUT"
PHYSICAL_OUTPUT = "PHYSICAL_OUTPUT"
NETWORK_DEVICE_COMMAND = "NETWORK_DEVICE_COMMAND"
NETWORK_DEVICE_STATUS = "NETWORK_DEVICE_STATUS"
LOGICAL_SIGNAL = "LOGICAL_SIGNAL"
MODULE_REFERENCE = "MODULE_REFERENCE"
ALIAS = "ALIAS"
TIMER = "TIMER"
AOI_INSTANCE = "AOI_INSTANCE"
CONTROLLER_TAG = "CONTROLLER_TAG"
PROGRAM_TAG = "PROGRAM_TAG"
UNKNOWN = "UNKNOWN"

SYMBOL_CLASSES = (
    PHYSICAL_INPUT,
    PHYSICAL_OUTPUT,
    NETWORK_DEVICE_COMMAND,
    NETWORK_DEVICE_STATUS,
    LOGICAL_SIGNAL,
    MODULE_REFERENCE,
    ALIAS,
    TIMER,
    AOI_INSTANCE,
    CONTROLLER_TAG,
    PROGRAM_TAG,
    UNKNOWN,
)

# Classes that MAY carry a physical endpoint (discrete I/O only)
PHYSICAL_ENDPOINT_REQUIRED_CLASSES = frozenset({PHYSICAL_INPUT, PHYSICAL_OUTPUT})
# Classes that must NOT invent / require a physical endpoint
PHYSICAL_ENDPOINT_FORBIDDEN_CLASSES = frozenset(
    {
        NETWORK_DEVICE_COMMAND,
        NETWORK_DEVICE_STATUS,
        LOGICAL_SIGNAL,
        TIMER,
        AOI_INSTANCE,
        ALIAS,
    }
)

# Gate H — unknown / unresolved disposition (never silent omit / auto BOOL)
DISP_FATAL = "FATAL"
DISP_ENGINEER_REQUIRED = "ENGINEER_REQUIRED"
DISP_OPTIONAL = "OPTIONAL"
DISP_ABSENT_REFERENCE = "ABSENT_REFERENCE"

UNKNOWN_DISPOSITIONS = (
    DISP_FATAL,
    DISP_ENGINEER_REQUIRED,
    DISP_OPTIONAL,
    DISP_ABSENT_REFERENCE,
)

_ABSENT_TOKENS = frozenset({"", "INVALID", "N/A", "NONE", "NULL", "~", "NA"})
_MODULE_RE = re.compile(
    r"^(?P<root>[A-Za-z_][A-Za-z0-9_]*):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\](?:\.(?P<bit>\d+))?$",
    re.I,
)
_TIMER_HINT = re.compile(r"^(tm|tmfc|TON|TOF|RTO)", re.I)
_AOI_HINT = re.compile(r"_AOI$", re.I)
_NET_CMD_HINT = re.compile(
    r"\.(O|Cmd|Command|Control|Run|Start|Stop|Reset)(\.|$)", re.I
)
_NET_STS_HINT = re.compile(
    r"\.(I|Sts|Status|Fault|Flt|Ready|At_Speed|Aux)(\.|$)", re.I
)


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
    semantic_class: str = CONTROLLER_TAG
    physical_endpoint: dict[str, Any] | None = None
    device_binding: str | None = None


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
        semantic_class: str = CONTROLLER_TAG,
        physical_endpoint: dict[str, Any] | None = None,
        device_binding: str | None = None,
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

        # Gate G: non-discrete classes must not invent a physical endpoint
        cls = (semantic_class or CONTROLLER_TAG).strip() or CONTROLLER_TAG
        if cls in PHYSICAL_ENDPOINT_FORBIDDEN_CLASSES:
            physical_endpoint = None

        sym = PlcSymbol(
            name=name,
            scope=scope,
            datatype=datatype,
            owner=owner,
            semantic_role=semantic_role,
            source_model=source_model,
            provenance=provenance,
            block=block,
            semantic_class=cls,
            physical_endpoint=physical_endpoint,
            device_binding=device_binding,
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


def _root_of(operand: str) -> str:
    op = (operand or "").strip()
    if not op:
        return ""
    if ":" in op:
        return op.split(":", 1)[0].strip()
    return op.split(".", 1)[0].strip()


def classify_cp_io_operand(
    operand: str,
    *,
    direction_hint: str = "",
    datatype: str = "",
    declared: dict[str, Any] | None = None,
    physical_endpoint: dict[str, Any] | None = None,
    device_binding: str | None = None,
) -> dict[str, Any]:
    """Resolve semantic class for one CP_I/CP_O operand (Gate G).

    Returns root, semantic_class, declaration owner/scope/datatype, physical
    endpoint (only when applicable), device binding, and provenance.
    Does NOT invent BOOL or fake modules for unknowns (Gate H).
    """
    op = (operand or "").strip()
    root = _root_of(op)
    decl = declared or {}
    scope = str(decl.get("scope") or "").strip()
    owner = str(decl.get("owner") or "").strip()
    dt = (datatype or decl.get("datatype") or "").strip()
    prov = str(decl.get("provenance") or "REVIEW").strip() or "REVIEW"
    dir_h = (direction_hint or "").strip().upper()
    if dir_h in ("IN", "INPUT"):
        dir_h = "I"
    elif dir_h in ("OUT", "OUTPUT"):
        dir_h = "O"

    # Explicit absent
    if op.upper() in _ABSENT_TOKENS or root.upper() in _ABSENT_TOKENS:
        return {
            "operand": op,
            "root": root or op,
            "semantic_class": LOGICAL_SIGNAL,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": None,
            "device_binding": None,
            "provenance": "ABSENT_REFERENCE",
            "disposition": DISP_ABSENT_REFERENCE,
            "why": "Explicit Fortna absent selection — do not fabricate BOOL",
            "requires_physical_endpoint": False,
        }

    # Module channel reference: CPxRIOn:I.Data[s].b
    mod = _MODULE_RE.match(op)
    if mod:
        cls = PHYSICAL_INPUT if mod.group("dir").upper() == "I" else PHYSICAL_OUTPUT
        if dir_h == "I":
            cls = PHYSICAL_INPUT
        elif dir_h == "O":
            cls = PHYSICAL_OUTPUT
        ep = physical_endpoint
        if ep is None:
            try:
                from fortna_hardware_io_model import make_physical_endpoint

                ep = make_physical_endpoint(
                    rio_name=mod.group("root"),
                    direction=mod.group("dir").upper(),
                    data_index=int(mod.group("slot")),
                    bit=int(mod.group("bit")) if mod.group("bit") is not None else None,
                    channel=op if mod.group("bit") is not None else None,
                )
            except Exception:
                ep = {
                    "rio_name": mod.group("root"),
                    "direction": mod.group("dir").upper(),
                    "data_index": int(mod.group("slot")),
                    "bit": int(mod.group("bit")) if mod.group("bit") is not None else None,
                    "channel": op if mod.group("bit") is not None else None,
                }
        return {
            "operand": op,
            "root": mod.group("root"),
            "semantic_class": cls,
            "declaration_owner": owner or "IO_MAP",
            "scope": scope or "controller",
            "datatype": dt or "MODULE",
            "physical_endpoint": ep,
            "device_binding": device_binding,
            "provenance": prov if decl else "PROVEN_MODULE_PATH",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": True,
        }

    # Alias (program of controller)
    if (decl.get("semantic_class") or "").upper() == ALIAS or (
        decl.get("alias_for") or decl.get("is_alias")
    ):
        return {
            "operand": op,
            "root": root,
            "semantic_class": ALIAS,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": None,
            "device_binding": device_binding or decl.get("alias_for"),
            "provenance": prov,
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": False,
        }

    # Timer
    if dt.upper() == "TIMER" or _TIMER_HINT.match(root):
        return {
            "operand": op,
            "root": root,
            "semantic_class": TIMER,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or "TIMER",
            "physical_endpoint": None,
            "device_binding": device_binding,
            "provenance": prov if decl else "DATATYPE_OR_NAME_HINT",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": False,
        }

    # AOI instance
    if _AOI_HINT.search(root) or (decl.get("semantic_class") or "").upper() == AOI_INSTANCE:
        return {
            "operand": op,
            "root": root,
            "semantic_class": AOI_INSTANCE,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": None,
            "device_binding": device_binding,
            "provenance": prov if decl else "NAME_SUFFIX_AOI",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": False,
        }

    # Network device command / status (UDT member paths — no physical endpoint)
    if "." in op and _NET_CMD_HINT.search(op) and dir_h != "I":
        # Prefer STATUS when .I. / fault-shaped and direction is input map
        if _NET_STS_HINT.search(op) and not re.search(r"\.O\.", op):
            cls = NETWORK_DEVICE_STATUS
        else:
            cls = NETWORK_DEVICE_COMMAND
        return {
            "operand": op,
            "root": root,
            "semantic_class": cls,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": None,  # NEVER invent
            "device_binding": device_binding or root,
            "provenance": prov if decl else "UDT_MEMBER_PATH",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": False,
        }
    if "." in op and _NET_STS_HINT.search(op):
        return {
            "operand": op,
            "root": root,
            "semantic_class": NETWORK_DEVICE_STATUS,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": None,
            "device_binding": device_binding or root,
            "provenance": prov if decl else "UDT_MEMBER_PATH",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": False,
        }

    # Declared controller / program tag
    if decl:
        cls = (decl.get("semantic_class") or "").strip().upper()
        if cls in SYMBOL_CLASSES:
            pass
        elif scope.startswith("program:"):
            cls = PROGRAM_TAG
        else:
            cls = CONTROLLER_TAG
        if cls in PHYSICAL_ENDPOINT_FORBIDDEN_CLASSES:
            physical_endpoint = None
        elif cls not in PHYSICAL_ENDPOINT_REQUIRED_CLASSES:
            # Declared non-discrete — do not require endpoint
            physical_endpoint = physical_endpoint if cls in PHYSICAL_ENDPOINT_REQUIRED_CLASSES else None
        return {
            "operand": op,
            "root": root,
            "semantic_class": cls,
            "declaration_owner": owner or None,
            "scope": scope or None,
            "datatype": dt or None,
            "physical_endpoint": physical_endpoint,
            "device_binding": device_binding,
            "provenance": prov,
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": cls in PHYSICAL_ENDPOINT_REQUIRED_CLASSES,
        }

    # Direction-hinted bare discrete BOOL only when explicitly physical map context
    # AND a physical endpoint is already proven — never invent one.
    if physical_endpoint and dir_h in ("I", "O"):
        cls = PHYSICAL_INPUT if dir_h == "I" else PHYSICAL_OUTPUT
        return {
            "operand": op,
            "root": root,
            "semantic_class": cls,
            "declaration_owner": owner or "IO_MAP",
            "scope": scope or "controller",
            "datatype": dt or "BOOL",
            "physical_endpoint": physical_endpoint,
            "device_binding": device_binding,
            "provenance": "PHYSICAL_ENDPOINT_BOUND",
            "disposition": None,
            "why": None,
            "requires_physical_endpoint": True,
        }

    # Unknown — Gate H policy (no auto BOOL)
    return unknown_symbol_policy(
        op,
        root=root,
        datatype=dt,
        scope=scope,
        why="No declaration, module path, or proven class for CP_I/CP_O operand",
    )


def unknown_symbol_policy(
    operand: str,
    *,
    root: str = "",
    datatype: str = "",
    scope: str = "",
    why: str = "",
    optional: bool = False,
    absent: bool = False,
) -> dict[str, Any]:
    """Gate H disposition for unknown symbols — never auto-BOOL / fake / omit."""
    op = (operand or "").strip()
    rt = (root or _root_of(op)).strip()
    if absent or op.upper() in _ABSENT_TOKENS:
        disp = DISP_ABSENT_REFERENCE
        reason = why or "Explicit absent reference"
    elif optional:
        disp = DISP_OPTIONAL
        reason = why or "Optional symbol — may be omitted with provenance"
    else:
        # Default: engineer must supply declaration; build must not invent BOOL
        disp = DISP_ENGINEER_REQUIRED
        reason = why or (
            "Unknown CP_I/CP_O symbol — FATAL to auto-create BOOL / fake module / "
            "TRUE/FALSE / NOP / silent omit / name-prefix guess"
        )
        # Escalate to FATAL when something looks like a fabricated path
        if re.search(r"(fake|placeholder|guess|auto_bool)", op, re.I):
            disp = DISP_FATAL
    return {
        "operand": op,
        "root": rt,
        "semantic_class": UNKNOWN,
        "declaration_owner": None,
        "scope": scope or None,
        "datatype": datatype or None,
        "physical_endpoint": None,
        "device_binding": None,
        "provenance": "UNRESOLVED",
        "disposition": disp,
        "why": reason,
        "requires_physical_endpoint": False,
        "forbidden_actions": [
            "auto_BOOL",
            "fake_module",
            "TRUE_FALSE_stub",
            "NOP_replace",
            "silent_omit",
            "name_prefix_guess",
        ],
    }


def symbol_requires_physical_endpoint(semantic_class: str) -> bool:
    return (semantic_class or "").strip().upper() in PHYSICAL_ENDPOINT_REQUIRED_CLASSES


def may_auto_declare_bool(resolved: dict[str, Any] | None) -> bool:
    """Gate H: never auto-declare BOOL for UNKNOWN / ENGINEER_REQUIRED / FATAL."""
    if not isinstance(resolved, dict):
        return False
    cls = (resolved.get("semantic_class") or "").upper()
    disp = (resolved.get("disposition") or "").upper()
    if cls == UNKNOWN:
        return False
    if disp in {DISP_FATAL, DISP_ENGINEER_REQUIRED, DISP_ABSENT_REFERENCE}:
        return False
    return False  # default deny — only explicit engineer override paths may create BOOL
