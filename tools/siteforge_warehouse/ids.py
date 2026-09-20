"""Stable warehouse fact identifiers. Archive identity is SHA256 hex lowercase."""
from __future__ import annotations

import hashlib
import re

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_archive_sha256(archive_sha256: str) -> str:
    """Normalize archive SHA256 to lowercase hex. Raises ValueError if invalid."""
    digest = (archive_sha256 or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if not _HEX64_RE.match(digest):
        raise ValueError(
            f"archive identity must be 64-char lowercase hex SHA256, got {archive_sha256!r}"
        )
    return digest


def fact_uid(
    kind: str,
    archive_sha256: str,
    source_path: str,
    source_row_index: int | str,
    extra: str = "",
) -> str:
    """Stable sha1-based fact id: ``sf_`` + hex digest.

    Identity inputs are ordered and delimited so collisions across kinds/paths
    are vanishingly unlikely. Archive identity is always SHA256 hex lowercase.
    """
    digest = normalize_archive_sha256(archive_sha256)
    payload = "|".join(
        [
            str(kind or "").strip(),
            digest,
            str(source_path or "").replace("\\", "/").strip(),
            str(source_row_index),
            str(extra or ""),
        ]
    )
    return "sf_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()
