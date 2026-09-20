"""Warehouse configuration — env + local corpus roots. No credentials in source."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

# Status string returned / raised when PostgreSQL is not configured.
POSTGRESQL_NOT_CONFIGURED = "POSTGRESQL_NOT_CONFIGURED"

_LOCAL_CORPUS_ROOTS_FILE = REPO_ROOT / "config" / "local_corpus_roots.txt"
# Gitignored — single-line URL written by local bootstrap (never commit)
_LOCAL_DATABASE_URL_FILE = REPO_ROOT / "config" / "local_database_url.txt"


def get_database_url() -> Optional[str]:
    """Return DB URL from env SITEFORGE_DATABASE_URL or gitignored local file.

    Never log or print the raw URL (callers must use redaction helpers).
    """
    url = (os.environ.get("SITEFORGE_DATABASE_URL") or "").strip()
    if url:
        return url
    if _LOCAL_DATABASE_URL_FILE.is_file():
        raw = _LOCAL_DATABASE_URL_FILE.read_text(encoding="utf-8-sig", errors="replace")
        for line in raw.splitlines():
            line = line.strip().strip("\ufeff")
            if not line or line.startswith("#"):
                continue
            return line
    return None


def is_postgres_configured() -> bool:
    """True when SITEFORGE_DATABASE_URL is set (does not open a connection)."""
    return get_database_url() is not None


def corpus_roots_from_env() -> list[Path]:
    """Parse SITEFORGE_CORPUS_ROOTS (os.pathsep-separated directories)."""
    raw = (os.environ.get("SITEFORGE_CORPUS_ROOTS") or "").strip()
    if not raw:
        return []
    out: list[Path] = []
    for part in raw.split(os.pathsep):
        p = Path(part.strip())
        if part.strip():
            out.append(p)
    return out


def corpus_roots_from_local_file() -> list[Path]:
    """Read config/local_corpus_roots.txt (gitignored; one path per line)."""
    path = _LOCAL_CORPUS_ROOTS_FILE
    if not path.is_file():
        return []
    out: list[Path] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(Path(line))
    return out


def resolve_corpus_roots(cli_roots: list[Path | str] | None = None) -> list[Path]:
    """Merge CLI roots, SITEFORGE_CORPUS_ROOTS, and local_corpus_roots.txt."""
    merged: dict[str, Path] = {}
    for src in (
        list(cli_roots or []),
        corpus_roots_from_env(),
        corpus_roots_from_local_file(),
    ):
        for item in src:
            p = Path(item)
            key = str(p.resolve()) if p.exists() else str(p)
            merged[key.lower()] = p
    return sorted(merged.values(), key=lambda x: str(x).lower())


# Public alias used by docs / callers
SITEFORGE_CORPUS_ROOTS = "SITEFORGE_CORPUS_ROOTS"
SITEFORGE_DATABASE_URL = "SITEFORGE_DATABASE_URL"
