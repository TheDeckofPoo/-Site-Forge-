#!/usr/bin/env python3
"""Unit tests for multi-section conveyor identity parsing.

Covers P130A letter family, P136_P1 / P136_P2 sections, and P120↛P1200 prefix guard.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import sys
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_identity import (  # noqa: E402
    conveyor_identities_match,
    linked_owns_conveyor,
    parse_p_tag,
)


def test_parse_p_tag_letter_and_section() -> None:
    assert parse_p_tag("P130A") == ("130", "A")
    assert parse_p_tag("p130a") == ("130", "A")
    assert parse_p_tag("P136_P1") == ("136", "_P1")
    assert parse_p_tag("P136_P2") == ("136", "_P2")
    assert parse_p_tag("P120") == ("120", "")
    assert parse_p_tag("P1200") == ("1200", "")
    assert parse_p_tag("P12") == ("12", "")
    assert parse_p_tag("") is None
    assert parse_p_tag("M130A") is None
    print("  [PASS] parse_p_tag letter + section forms")


def test_no_digit_prefix_bugs() -> None:
    assert not conveyor_identities_match("P120", "P1200")
    assert not conveyor_identities_match("P12", "P120")
    assert not conveyor_identities_match("P120", "P1202")
    assert conveyor_identities_match("P120", "P120")
    print("  [PASS] P120 vs P1200 / P12 vs P120 prefix guard")


def test_letter_family_still_matches() -> None:
    assert conveyor_identities_match("P130", "P130A")
    assert conveyor_identities_match("P130A", "P130")
    assert conveyor_identities_match("P424", "P424A")
    print("  [PASS] letter family P130 ↔ P130A")


def test_section_tokens_are_distinct() -> None:
    assert not conveyor_identities_match("P136_P1", "P136_P2")
    assert not conveyor_identities_match("P136", "P136_P1")
    assert not conveyor_identities_match("P136_P1", "P136")
    assert conveyor_identities_match("P136_P1", "P136_P1")
    assert conveyor_identities_match("p136_p2", "P136_P2")
    print("  [PASS] section tokens P136_P1 / P136_P2 are distinct")


def test_linked_owns_sections_and_motors() -> None:
    # Motor M130A → linked P130A owns ASC row P130A exactly; also letter-family P130
    linked = {"P130A", "P136_P1"}
    assert linked_owns_conveyor("P130A", linked)
    assert linked_owns_conveyor("P130", linked)  # letter family
    assert linked_owns_conveyor("P136_P1", linked)
    assert not linked_owns_conveyor("P136_P2", linked)
    assert not linked_owns_conveyor("P136", linked)  # section ≠ plain
    assert not linked_owns_conveyor("P1200", {"P120"})
    print("  [PASS] linked_owns section + motor letter family")


def main() -> int:
    print("=== fortna_identity section parsing ===")
    fails = 0
    for fn in (
        test_parse_p_tag_letter_and_section,
        test_no_digit_prefix_bugs,
        test_letter_family_still_matches,
        test_section_tokens_are_distinct,
        test_linked_owns_sections_and_motors,
    ):
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
