#!/usr/bin/env python3
"""
Source identity for FortnaPlus exports and PRISM ingest.

Raw-test rule: output folder / file stems follow the .tar.gz basename
(e.g. 20260624-1716-OReillyGreensboro-ORNCCP5-RUN.tar.gz
   → 20260624-1716-OReillyGreensboro-ORNCCP5-RUN).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ACTIVE_META = REPO_ROOT / "workspace" / "active-meta.json"


def archive_export_name(archive_path: Path | str | None) -> str:
    """Basename of the intake archive without .tar.gz / .tgz / .zip."""
    if not archive_path:
        return ""
    name = Path(str(archive_path)).name
    lower = name.lower()
    for suf in (".tar.gz", ".tgz", ".tar", ".zip"):
        if lower.endswith(suf):
            name = name[: -len(suf)]
            break
    else:
        name = Path(name).stem
    # Windows-safe path component; keep hyphens and alphanumerics
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    name = re.sub(r"_+", "_", name)
    return name or "RUN_PACKAGE"


def safe_fs_name(name: str, max_len: int = 120) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("._")
    if not s:
        s = "RUN_PACKAGE"
    return s[:max_len]


def load_active_meta() -> dict:
    if not ACTIVE_META.is_file():
        return {}
    try:
        return json.loads(ACTIVE_META.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def export_label_from_meta(meta: dict | None = None) -> str:
    """Preferred export label: tar.gz stem, else machine, else Autogen_Project."""
    meta = meta if meta is not None else load_active_meta()
    for key in ("export_name", "archive_stem", "source_label"):
        v = (meta.get(key) or "").strip()
        if v:
            return safe_fs_name(v)
    arch = meta.get("archive") or meta.get("archive_path") or ""
    if arch:
        return safe_fs_name(archive_export_name(arch))
    machine = (meta.get("machine") or "").strip()
    if machine:
        return safe_fs_name(machine)
    return "Autogen_Project"


def run_content_fingerprint(run_dir: Path) -> str:
    """
    Stable fingerprint of RUN content so re-import of the same site is skipped.
    Uses size + sha256 of key files (not full tree).
    """
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    h = hashlib.sha256()
    key_files = [
        run_dir / "project.cfg",
        run_dir / "FORTNA" / "Conveyor.asc",
        run_dir / "Conveyor.asc",
        run_dir / "PROJECT" / "EIPCSV.csv",
        run_dir / "PROJECT" / "EIPModules.csv",
    ]
    for p in key_files:
        if not p.is_file():
            continue
        try:
            st = p.stat()
            h.update(p.name.encode("utf-8"))
            h.update(str(st.st_size).encode("ascii"))
            # sample first/last 64KB for large ASC without hashing entire multi-MB file slowly
            with p.open("rb") as f:
                head = f.read(65536)
                h.update(head)
                if st.st_size > 131072:
                    f.seek(max(0, st.st_size - 65536))
                    h.update(f.read(65536))
                elif st.st_size > 65536:
                    h.update(f.read())
        except OSError:
            continue
    return h.hexdigest()[:40]


def write_active_meta_fields(**fields) -> dict:
    meta = load_active_meta()
    meta.update(fields)
    ACTIVE_META.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
