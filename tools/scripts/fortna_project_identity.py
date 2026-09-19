#!/usr/bin/env python3
"""Canonical ProjectIdentity — authoritative same-project gate.

project_key     = stable project/controller identity (survives RUN revisions)
run_fingerprint = content revision of the current RUN
machine         = target Machinename from project.cfg

Same project_key + same machine → engineer decisions may reconcile.
Different project/controller → never inherit site-specific state.
Explicit Clear always purges active site state regardless of identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _upper(v: Any) -> str:
    return _clean(v).upper()


def normalize_machine_token(machine: str) -> str:
    """Normalize controller / Machinename token (no fuzzy substring aliases)."""
    m = _upper(machine).replace(" ", "")
    # Strip common project_name prefixes like MSCRENO_MSCRENOPICK → MSCRENOPICK
    if "_" in m:
        tail = m.rsplit("_", 1)[-1]
        if tail:
            return tail
    return m


def project_key_from_parts(*, project_name: str = "", machine: str = "") -> str:
    """Stable project key: prefer PROJECTNAME+MACHINENAME, else machine alone."""
    proj = _upper(project_name).replace(" ", "")
    mach = normalize_machine_token(machine)
    if proj and mach:
        # Avoid doubling when project_name already ends with machine
        if proj.endswith("_" + mach) or proj == mach:
            return f"{proj}|{mach}"
        return f"{proj}|{mach}"
    return mach or proj


@dataclass(frozen=True)
class ProjectIdentity:
    project_name: str
    machine: str
    project_key: str
    run_fingerprint: str
    archive: str = ""
    loaded_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "project_name": self.project_name,
            "machine": self.machine,
            "project_key": self.project_key,
            "run_fingerprint": self.run_fingerprint,
            "archive": self.archive,
            "loadedAt": self.loaded_at,
        }


def same_project(a: ProjectIdentity | None, b: ProjectIdentity | None) -> bool:
    """True only when both identities share project_key and machine."""
    return bool(
        a
        and b
        and a.project_key
        and a.project_key == b.project_key
        and normalize_machine_token(a.machine) == normalize_machine_token(b.machine)
    )


def same_run_revision(a: ProjectIdentity | None, b: ProjectIdentity | None) -> bool:
    return bool(
        same_project(a, b)
        and a
        and b
        and a.run_fingerprint
        and a.run_fingerprint == b.run_fingerprint
    )


def identity_from_mapping(data: dict[str, Any] | None) -> ProjectIdentity | None:
    if not isinstance(data, dict) or not data:
        return None
    machine = _clean(data.get("machine") or data.get("machine_name") or "")
    project_name = _clean(
        data.get("project_name") or data.get("project") or data.get("PROJECTNAME") or ""
    )
    project_key = _clean(data.get("project_key") or "") or project_key_from_parts(
        project_name=project_name, machine=machine
    )
    if not project_key and not machine:
        return None
    return ProjectIdentity(
        project_name=project_name,
        machine=normalize_machine_token(machine) or machine,
        project_key=project_key,
        run_fingerprint=_clean(data.get("run_fingerprint") or data.get("runFingerprint") or ""),
        archive=_clean(data.get("archive") or data.get("archive_name") or ""),
        loaded_at=_clean(data.get("loadedAt") or data.get("loaded_at") or ""),
    )


def identity_from_run(
    run_dir: Path | str,
    *,
    archive: str = "",
    fingerprint: str = "",
) -> ProjectIdentity:
    """Build identity from RUN project.cfg (+ optional content fingerprint)."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    meta = _read_project_cfg(run_dir / "project.cfg")
    machine = meta.get("MACHINENAME") or meta.get("machine_name") or ""
    project_name = meta.get("PROJECTNAME") or meta.get("project_name") or ""
    fp = fingerprint
    if not fp:
        try:
            from fortna_source_id import run_content_fingerprint

            fp = run_content_fingerprint(run_dir) or ""
        except Exception:
            fp = _fallback_run_fingerprint(run_dir)
    return ProjectIdentity(
        project_name=_clean(project_name),
        machine=normalize_machine_token(machine) or _clean(machine),
        project_key=project_key_from_parts(project_name=project_name, machine=machine),
        run_fingerprint=_clean(fp),
        archive=_clean(archive),
    )


def identity_from_workbook(workbook: dict[str, Any] | None) -> ProjectIdentity | None:
    if not isinstance(workbook, dict):
        return None
    stamped = workbook.get("project_identity") or workbook.get("projectIdentity")
    if isinstance(stamped, dict):
        ident = identity_from_mapping(stamped)
        if ident:
            return ident
    return identity_from_mapping(
        {
            "machine": workbook.get("machine") or workbook.get("machine_name"),
            "project_name": workbook.get("project_name") or workbook.get("project"),
            "run_fingerprint": workbook.get("run_fingerprint"),
            "archive": workbook.get("archive") or workbook.get("source_archive"),
            "project_key": workbook.get("project_key"),
        }
    )


def stamp_workbook_identity(workbook: dict[str, Any], identity: ProjectIdentity) -> dict[str, Any]:
    wb = dict(workbook or {})
    wb["project_identity"] = identity.to_dict()
    wb["machine"] = identity.machine
    if identity.project_name:
        wb["project_name"] = wb.get("project_name") or identity.project_name
    wb["run_fingerprint"] = identity.run_fingerprint
    wb["project_key"] = identity.project_key
    return wb


def _read_project_cfg(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s or s.startswith("[") or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip().upper()] = v.strip()
    return out


def _fallback_run_fingerprint(run_dir: Path) -> str:
    """Cheap content fingerprint when fortna_source_id is unavailable."""
    h = hashlib.sha256()
    fortna = run_dir / "FORTNA"
    cfg = run_dir / "project.cfg"
    if cfg.is_file():
        h.update(cfg.read_bytes())
    if fortna.is_dir():
        for p in sorted(fortna.glob("*.asc*"))[:40]:
            try:
                h.update(p.name.encode())
                h.update(str(p.stat().st_size).encode())
                h.update(p.read_bytes()[:4096])
            except OSError:
                continue
    return h.hexdigest()[:16]


# Browser / localStorage keys that hold site-specific state.
PROJECT_SCOPED_STORAGE_KEYS = (
    "fortna_sawtooth_build",
    "fortna_sorter_build",
    "fortna_merges_2to1",
    "fortna_wcs_build",
    "siteforge.transportBuild.v1",
    "siteforge.transportBuild.v2",
    "siteforge.safetyBuild.v1",
    "siteforge.wcsBuild.v1",
    "siteforge.projectIdentity",
    "fortna_last_equipment_names",
    "siteforge.ocrLastResult",
)

# Workspace files that must be identity-scoped or ignored on mismatch.
PROJECT_SCOPED_WORKSPACE_FILES = (
    "workspace/ocr-last-result.json",
    "workspace/autogen_workbook.json",
)


def storage_payload_matches_identity(payload: Any, current: ProjectIdentity | None) -> bool:
    """Reject cached JSON blobs whose embedded identity does not match current."""
    if current is None:
        return False
    if not isinstance(payload, dict):
        return False
    stamped = identity_from_mapping(
        payload.get("projectIdentity")
        or payload.get("project_identity")
        or payload
    )
    return same_project(stamped, current)
