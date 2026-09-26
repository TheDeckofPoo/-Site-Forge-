"""Device-label grammar for CANDIDATE DISCOVERY ONLY.

A naming pattern is NOT physical proof.  The grammar only nominates
candidates and a family hypothesis; evidence semantics (see
device_candidates.py) decide state and confidence.

Generic controls / Fortna-style forms are supported (P####, PE####, M####,
CP#, MCP#, ESPB#, #ES#, ESLS####, ESR / MCR variants, ...).  No site names
and no site device lists are encoded here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ---------------------------------------------------------------- families
FAMILIES = (
    "controller",
    "control_panel",
    "remote_io_panel",
    "conveyor",
    "motor",
    "vfd",
    "photoeye",
    "scanner",
    "estop",
    "espb",
    "esls",
    "esr",
    "mcr",
    "control_station",
    "stacklight",
    "merge",
    "divert",
    "specialty_conveyor_device",
    "io_module",
    "io_channel_reference",
    "terminal_reference",
    "network_reference",
    "sheet_cross_reference",
    "ambiguous",
    "unknown",
)

SAFETY_FAMILIES = frozenset({"estop", "espb", "esls", "esr", "mcr"})


@dataclass(frozen=True)
class DeviceRule:
    rule_id: str
    family: str
    pattern: "re.Pattern[str]"
    base_confidence: float


def _r(p: str) -> "re.Pattern[str]":
    return re.compile(p, re.I)


# Full-token (anchored) rules.  Order matters only for readability: rules
# are anchored so ESPB12 can never match the ES rule, etc.
DEVICE_RULES: Tuple[DeviceRule, ...] = (
    DeviceRule("G-PLC", "controller", _r(r"^PLC[-_]?\d{1,3}[A-Z]?$"), 0.75),
    DeviceRule("G-MCP", "control_panel", _r(r"^MCP[-_]?\d{1,3}[A-Z]?$"), 0.75),
    DeviceRule("G-CP", "control_panel", _r(r"^CP[-_]?\d{1,3}[A-Z]?$"), 0.7),
    DeviceRule("G-RIO", "remote_io_panel", _r(r"^RIOP?[-_]?\d{1,3}[A-Z]?$"), 0.7),
    DeviceRule("G-VFD", "vfd", _r(r"^VFD[-_]?\d{1,5}[A-Z]?$"), 0.75),
    DeviceRule("G-PE", "photoeye", _r(r"^PE[-_]?\d{2,5}[A-Z]?\d?$"), 0.75),
    DeviceRule("G-P", "conveyor", _r(r"^P[-_]?\d{3,5}[A-Z]?$"), 0.7),
    DeviceRule("G-M", "motor", _r(r"^M[-_]?\d{3,5}[A-Z]?$"), 0.7),
    DeviceRule("G-SCN", "scanner", _r(r"^(?:SCN|SCANNER|BCR)[-_]?\d{1,5}[A-Z]?$"), 0.7),
    DeviceRule("G-ESPB", "espb", _r(r"^ESPB[-_]?\d{1,5}[A-Z]?$"), 0.75),
    DeviceRule("G-ESLS", "esls", _r(r"^ESLS[-_]?\d{1,5}[A-Z]?$"), 0.75),
    DeviceRule("G-ESR", "esr", _r(r"^(?:\d{1,3}ESR[-_]?[A-Z0-9]{0,6}|ESR[-_]?\d[A-Z0-9]{0,5})$"), 0.7),
    DeviceRule("G-MCR", "mcr", _r(r"^(?:\d{1,3}MCR[-_]?[A-Z0-9]{0,6}|MCR[-_]?\d[A-Z0-9]{0,5})$"), 0.7),
    DeviceRule("G-ES", "estop", _r(r"^ES[-_]?\d{1,5}[A-Z]?$"), 0.65),
    DeviceRule("G-NES", "estop", _r(r"^\d{1,3}ES\d{1,4}[A-Z]?$"), 0.65),
    DeviceRule("G-CS", "control_station", _r(r"^(?:CS|PB|PBS)[-_]?\d{1,5}[A-Z]?$"), 0.65),
    DeviceRule("G-SL", "stacklight", _r(r"^(?:SL|STK|STL)[-_]?\d{1,5}[A-Z]?$"), 0.65),
    DeviceRule("G-MRG", "merge", _r(r"^(?:MRG|MG)[-_]?\d{1,5}[A-Z]?$"), 0.65),
    DeviceRule("G-DIV", "divert", _r(r"^(?:DIV|DV)[-_]?\d{1,5}[A-Z]?$"), 0.65),
    DeviceRule("G-SPC", "specialty_conveyor_device", _r(r"^(?:LFT|TT|SRT|SPD)[-_]?\d{1,5}[A-Z]?$"), 0.6),
)

# Prefixes that mean different things on different prints (switch, sensor,
# scanner, power supply, disconnect, starter ...).  Kept, never guessed.
AMBIGUOUS_RULES: Tuple[Tuple[str, "re.Pattern[str]", Tuple[str, ...]], ...] = (
    ("A-S", _r(r"^S[-_]?\d{2,5}[A-Z]?$"), ("switch", "sensor", "scanner")),
    ("A-ST", _r(r"^ST[-_]?\d{1,5}[A-Z]?$"), ("scan_tunnel", "starter", "station")),
    ("A-PS", _r(r"^PS[-_]?\d{1,5}[A-Z]?$"), ("power_supply", "proximity_switch", "pressure_switch")),
    ("A-LS", _r(r"^LS[-_]?\d{1,5}[A-Z]?$"), ("limit_switch", "level_switch")),
    ("A-DS", _r(r"^DS[-_]?\d{1,5}[A-Z]?$"), ("disconnect_switch", "door_switch")),
    ("A-SS", _r(r"^SS[-_]?\d{1,5}[A-Z]?$"), ("selector_switch", "safety_switch")),
)

# Device-LIKE shape that no rule classifies => UNKNOWN (kept, never dropped).
UNKNOWN_SHAPES = (
    _r(r"^[A-Z]{1,5}[-_]?\d{2,5}[A-Z]{0,2}$"),
    _r(r"^\d{1,3}[A-Z]{1,4}\d{1,4}[A-Z]?$"),
)
# Tokens that look device-like but are ordinary drawing vocabulary/units.
NON_DEVICE_PREFIXES = frozenset(
    {"AWG", "REV", "SHT", "DWG", "QTY", "NO", "OF", "PG", "PAGE", "FIG", "NOTE", "ITEM", "DATE", "RM", "MM", "IP", "NEMA"}
)
UNIT_RE = _r(r"^\d+(?:\.\d+)?(?:V|VAC|VDC|A|MA|HP|HZ|PH|KW|KVA|MM|IN|FT|W|MS|S|SEC|RPM|FPM|AWG)$")

# ------------------------------------------------ line-level printed refs
IO_ADDRESS_RES = (
    ("IO-LOGIX", _r(r"\b[A-Z_][A-Z0-9_]*:\d+:[IO](?:\.Data)?(?:\.\d+)?\b")),
    ("IO-SLC", _r(r"\b[IO]:\d+(?:\.\d+)?/\d+\b")),
    ("IO-SLOTCH", _r(r"\bSLOT\s*\d+\s*(?:/|,)?\s*CH(?:ANNEL)?\s*\d+\b")),
    ("IO-SLOT", _r(r"\bSLOT\s*\d+\b")),
    ("IO-CH", _r(r"\bCH(?:ANNEL)?\s*\d+\b")),
)
IO_MODULE_RE = _r(r"\b(?:1734|1756|1769|1794|5069|5094|1732E?|1738|1719)-[A-Z0-9]{2,8}\b")
TERMINAL_RES = (
    ("TB", _r(r"\bTB[-_]?\d+[-:/]\d+\b")),
    ("X", _r(r"\bX\d+[:]\d+\b")),
    ("TERM", _r(r"\bTERM(?:INAL)?\.?\s*#?\s*\d+\b")),
)
NETWORK_RE = _r(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
CONTINUATION_RE = _r(
    r"\b(?:SEE|CONT(?:INUED|'D|\.)?|TO|FROM)\s+(?:ON\s+|FROM\s+|TO\s+)?(?:SHEET|SHT|DWG|DRAWING)\.?\s*(?:NO\.?\s*)?#?\s*"
    r"([A-Z0-9](?:[A-Z0-9\-\.]*[A-Z0-9])?)"
)

# Explicit connector words that make a printed relationship explicit.
CONNECTOR_RE = _r(
    r"^(->|→|=>|=|TO|DRIVES|DRIVEN\s+BY|FEEDS|FED\s+FROM|POWERS|POWERED\s+BY|MOUNTED\s+ON|ON|WIRED\s+TO|IN\s+CIRCUIT|IN\s+SAFETY\s+CIRCUIT|MONITORS|CONTROLS)$"
)

STRIP_CHARS = "()[]{}<>,;:\"'`"


def strip_token(text: str) -> str:
    """Remove surrounding punctuation only; interior punctuation/case kept."""
    t = text.strip(STRIP_CHARS)
    while t.endswith(".") or t.endswith(STRIP_CHARS[-1]):
        t = t[:-1]
    return t


def normalize_label(raw: str) -> str:
    """Normalization CANDIDATE only (upper-case, drop -, _, spaces, dots)."""
    return re.sub(r"[-_\s\.]", "", raw.upper())


@dataclass(frozen=True)
class TokenClass:
    kind: str  # "device" | "ambiguous" | "unknown"
    family: str
    rule_id: str
    base_confidence: float
    candidates: Tuple[str, ...] = ()


def classify_token(token: str) -> Optional[TokenClass]:
    """Classify an already-stripped token.  None => not device-like at all."""
    if not token or len(token) > 16:
        return None
    for rule in DEVICE_RULES:
        if rule.pattern.match(token):
            return TokenClass("device", rule.family, rule.rule_id, rule.base_confidence)
    for rid, pat, cands in AMBIGUOUS_RULES:
        if pat.match(token):
            return TokenClass("ambiguous", "ambiguous", rid, 0.4, cands)
    if UNIT_RE.match(token):
        return None
    for pat in UNKNOWN_SHAPES:
        if pat.match(token):
            prefix = re.match(r"^\d*([A-Z]+)", token.upper())
            if prefix and prefix.group(1) in NON_DEVICE_PREFIXES:
                return None
            return TokenClass("unknown", "unknown", "U-SHAPE", 0.2)
    return None


# Descriptive printed words that CORROBORATE a family.  Only these (printed
# on the same/adjacent line) can lift a label to PROVEN; the label prefix
# itself never does.
FAMILY_KEYWORDS = {
    "controller": ("CONTROLLER", "PROCESSOR", "CONTROLLOGIX", "COMPACTLOGIX"),
    "control_panel": ("CONTROL PANEL", "MAIN CONTROL PANEL", "ENCLOSURE"),
    "remote_io_panel": ("REMOTE I/O", "REMOTE IO", "I/O PANEL", "I/O RACK"),
    "conveyor": ("CONVEYOR", "CONV."),
    "motor": ("MOTOR",),
    "vfd": ("VARIABLE FREQUENCY DRIVE", "DRIVE", "INVERTER"),
    "photoeye": ("PHOTOEYE", "PHOTO EYE", "PHOTO-EYE", "PHOTOELECTRIC"),
    "scanner": ("SCANNER", "SCAN TUNNEL", "BARCODE"),
    "estop": ("E-STOP", "EMERGENCY STOP", "ESTOP"),
    "espb": ("EMERGENCY STOP PUSHBUTTON", "E-STOP PUSHBUTTON", "EMERGENCY STOP PUSH BUTTON", "E-STOP PUSH BUTTON"),
    "esls": ("PULL CORD", "PULLCORD", "LANYARD", "PULL-CORD"),
    "esr": ("SAFETY RELAY", "E-STOP RELAY", "EMERGENCY STOP RELAY"),
    "mcr": ("MASTER CONTROL RELAY",),
    "control_station": ("CONTROL STATION", "PUSHBUTTON STATION", "OPERATOR STATION"),
    "stacklight": ("STACK LIGHT", "STACKLIGHT", "BEACON"),
    "merge": ("MERGE",),
    "divert": ("DIVERT", "DIVERTER"),
    "specialty_conveyor_device": ("LIFT", "TURNTABLE", "SORTER"),
}


def corroborating_keyword(family: str, text: str) -> Optional[str]:
    up = f" {text.upper()} "
    for kw in FAMILY_KEYWORDS.get(family, ()):
        if re.search(r"(?<![A-Z0-9])" + re.escape(kw) + r"(?![A-Z0-9])", up):
            return kw
    return None


def device_tokens_in(text: str) -> List[str]:
    out = []
    for w in text.split():
        t = strip_token(w)
        c = classify_token(t)
        if c and c.kind == "device":
            out.append(t)
    return out
