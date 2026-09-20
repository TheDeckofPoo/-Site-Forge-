#!/usr/bin/env python3
"""Superseded by test_iomap_review_shared_output.py (REVIEW_SHARED_OUTPUT policy)."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "io"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

# Re-export the authoritative suite under this historical module name.
from test_iomap_review_shared_output import TestReviewSharedOutput  # noqa: E402,F401


if __name__ == "__main__":
    unittest.main(verbosity=2)
