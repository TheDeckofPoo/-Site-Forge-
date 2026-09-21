"""Controller tag ownership registry — first-line guard before L5X assembly.

Same canonical object + same datatype → emit once.
Different objects / incompatible datatypes → BUILD BLOCKED TAG_IDENTITY_CONFLICT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_ATOMIC = frozenset({
    "BOOL", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL", "STRING",
})


def _norm_name(name: str) -> str:
    return str(name or "").strip()


def _norm_dtype(datatype: str) -> str:
    return str(datatype or "").strip().upper()


def _norm_owner(owner: str) -> str:
    return str(owner or "").strip().upper().replace("-", "_")


def _is_atomic(dt: str) -> bool:
    return _norm_dtype(dt) in _ATOMIC


@dataclass
class TagRegistration:
    name: str
    owner: str
    datatype: str
    subsystem: str
    provenance: str = ""
    emit: bool = True


@dataclass
class ControllerTagRegistry:
    """Ownership registry for controller-scoped tag names."""

    _by_name: dict[str, TagRegistration] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    def register_tag(
        self,
        name: str,
        owner: str,
        datatype: str,
        subsystem: str,
        provenance: str = "",
    ) -> bool:
        """Register a controller tag request.

        Returns True when the caller should emit the tag block now.
        Returns False when an equivalent registration already owns the name
        (same canonical object + compatible datatype) — emit once.

        Raises TagIdentityConflict on incompatible ownership / datatype.
        """
        tname = _norm_name(name)
        if not tname:
            return False
        own = _norm_owner(owner) or tname.upper()
        dt = _norm_dtype(datatype) or "BOOL"
        sub = str(subsystem or "").strip() or "UNKNOWN"
        prov = str(provenance or "").strip()

        existing = self._by_name.get(tname)
        if existing is None:
            self._by_name[tname] = TagRegistration(
                name=tname,
                owner=own,
                datatype=dt,
                subsystem=sub,
                provenance=prov,
                emit=True,
            )
            return True

        same_owner = existing.owner == own
        same_dt = existing.datatype == dt

        if same_owner and same_dt:
            return False

        # Same object: allow atomic stub → structured UDT upgrade (emit replacement).
        if same_owner and _is_atomic(existing.datatype) and not _is_atomic(dt):
            self._by_name[tname] = TagRegistration(
                name=tname,
                owner=own,
                datatype=dt,
                subsystem=sub,
                provenance=prov or existing.provenance,
                emit=True,
            )
            return True

        # Same object + already richer / equal structured type — keep first.
        if same_owner and not _is_atomic(existing.datatype) and (
            same_dt or _is_atomic(dt)
        ):
            return False

        msg = (
            "BUILD BLOCKED TAG_IDENTITY_CONFLICT: "
            f"tag={tname} "
            f"existing[owner={existing.owner} datatype={existing.datatype} "
            f"subsystem={existing.subsystem} provenance={existing.provenance}] "
            f"requested[owner={own} datatype={dt} subsystem={sub} provenance={prov}]"
        )
        self.conflicts.append(msg)
        raise TagIdentityConflict(msg)

    def get(self, name: str) -> TagRegistration | None:
        return self._by_name.get(_norm_name(name))

    def names(self) -> set[str]:
        return set(self._by_name.keys())

    def assertion_failures(self) -> list[str]:
        return list(self.conflicts)


class TagIdentityConflict(Exception):
    """Incompatible controller tag ownership or datatype."""


def canonical_safety_logix_tag(name: str) -> str:
    """Map Fortna / engineer Safety identity → one canonical Logix tag.

    Digit-leading ESTOP/MCR/ESR/ESLS forms become T_NAME once.
    Already-legal names (CP2_ES, ES400, T_2ES, ESLS125) are unchanged.
    """
    import re

    raw = str(name or "").strip()
    n = re.sub(r"[^\w]", "_", raw)
    n = re.sub(r"_+", "_", n).strip("_")
    if not n:
        return ""
    if re.match(r"^[A-Za-z_]", n):
        return n
    if re.match(r"^\d", n):
        return f"T_{n}"
    return n


def safety_device_owner_key(name: str, kind: str = "") -> str:
    """Canonical owner key for Safety NAME / T_NAME alias pairs."""
    import re

    u = str(name or "").strip().upper().replace("-", "_")
    if not u:
        return ""
    m = re.match(r"^T_(.+)$", u)
    if m:
        u = m.group(1)
    m = re.match(r"^(.+)_AUX$", u)
    if m:
        u = m.group(1)
    k = str(kind or "").strip().upper()
    return f"{k}:{u}" if k else u
