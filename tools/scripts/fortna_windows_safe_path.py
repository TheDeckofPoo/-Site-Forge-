#!/usr/bin/env python3
"""Windows-safe artifact filename helpers.

Reserved characters that must never appear in generated filenames:
  < > : \" / \\ | ? *
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

WINDOWS_INVALID_CHARS = frozenset('<>:"/\\|?*')
_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def sanitize_windows_filename(
    name: str,
    *,
    replacement: str = "_",
    max_len: int = 120,
    default: str = "artifact",
) -> str:
    """Return a Windows-safe file basename (no directory components)."""
    raw = str(name or "").strip().replace("\n", " ").replace("\r", " ")
    # Drop any path components if a path-like string sneaks in
    raw = raw.replace("\\", "/").split("/")[-1]
    cleaned = _INVALID_RE.sub(replacement, raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    if not cleaned:
        cleaned = default
    stem = cleaned
    suffix = ""
    if "." in cleaned:
        # preserve final extension if present
        parts = cleaned.rsplit(".", 1)
        if len(parts[1]) <= 8 and parts[1].isalnum():
            stem, suffix = parts[0], "." + parts[1]
    stem = stem[: max(1, max_len - len(suffix))]
    if stem.upper() in _WIN_RESERVED:
        stem = f"_{stem}"
    return stem + suffix


def stable_defect_filename(
    *,
    prefix: str = "GENERATOR_DEFECT",
    failure_code: str = "",
    signature: str = "",
    ext: str = ".json",
) -> str:
    """Prefer stable failure-code filenames; never embed dynamic comparisons like 26.92<85.0."""
    code = str(failure_code or "").strip()
    if not code and signature:
        # Take leading CODE segments before dynamic values
        # e.g. IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:26.92<85.0 → IO_DEVICE_RESOLUTION_BELOW_THRESHOLD
        sig = str(signature).strip()
        # Strip trailing dynamic payload after second numeric/comparison segment
        parts = sig.split(":")
        # Keep code-like tokens (letters/underscores) only
        kept = []
        for p in parts:
            token = p.strip()
            if not token:
                continue
            if re.search(r"[<>]|^\d+(\.\d+)?$", token):
                break
            kept.append(token)
        code = "_".join(kept) if kept else sig
    code = code.replace(":", "_").replace(" ", "_")
    base = f"{prefix}_{code}" if code else prefix
    return sanitize_windows_filename(base + (ext if ext.startswith(".") else f".{ext}"))


def assert_windows_safe_filename(name: str) -> None:
    bad = [ch for ch in name if ch in WINDOWS_INVALID_CHARS]
    if bad:
        raise ValueError(f"Windows-invalid characters in filename {name!r}: {bad}")
    if "/" in name or "\\" in name:
        raise ValueError(f"path separators not allowed in basename: {name!r}")
