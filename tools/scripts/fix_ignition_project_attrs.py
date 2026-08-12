#!/usr/bin/env python3
"""Clear ReadOnly on an Ignition project folder (OneDrive / copy artifact).

Designer shows "no-project" white canvas and "Failed to commit" when the
project tree is ReadOnly. OneDrive often stamps that attribute when files
sync or when you copy a pack from a synced Desktop folder.

Usage:
  py tools/scripts/fix_ignition_project_attrs.py
  py tools/scripts/fix_ignition_project_attrs.py --project FortnaPlus_ORNCCP5
  py tools/scripts/fix_ignition_project_attrs.py --path "C:\\Program Files\\...\\FortnaPlus_X"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_perspective_pack import _clear_readonly_tree  # noqa: E402

DEFAULT_PROJECTS = Path(
    r"C:\Program Files\Inductive Automation\Ignition\data\projects"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Clear ReadOnly on Ignition project")
    ap.add_argument("--project", default="FortnaPlus_ORNCCP5", help="Project folder name")
    ap.add_argument("--path", default="", help="Full path override")
    args = ap.parse_args()

    root = Path(args.path) if args.path else (DEFAULT_PROJECTS / args.project)
    if not root.is_dir():
        print(f"ERROR: project not found: {root}")
        return 1

    _clear_readonly_tree(root)

    # Report remaining ReadOnly (Windows)
    bad = []
    try:
        import ctypes
        import os

        FILE_ATTRIBUTE_READONLY = 0x01
        for p in [root, *root.rglob("*")]:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            if attrs != -1 and (attrs & FILE_ATTRIBUTE_READONLY):
                bad.append(str(p))
            elif os.name == "nt" and hasattr(p, "is_file") and p.is_file():
                # also check pathlib
                try:
                    if p.stat().st_file_attributes & 0x1:  # type: ignore[attr-defined]
                        bad.append(str(p))
                except Exception:
                    pass
    except Exception:
        pass

    print(f"OK cleared ReadOnly under: {root}")
    if bad:
        print(f"WARN still ReadOnly ({len(bad)}):")
        for b in bad[:15]:
            print(" ", b)
        return 2
    print("No ReadOnly attributes remain.")
    print("Next: Gateway → Platform → System → Projects → Scan Filesystem")
    print("Then Designer: File → Update Project (or re-open the project).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
