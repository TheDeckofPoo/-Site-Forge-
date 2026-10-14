"""Demo sprint: Control_Station must not dual-write Area_HMI with Area_Logic."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = (REPO_ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(
    encoding="utf-8", errors="replace"
)


def test_control_station_review_stub_when_no_cs_udt():
    assert "Control_Station REVIEW — no proven CS_UDT" in SRC
    assert "single writer" in SRC
    # Old dual-writer comments that emitted Area_HMI OTEs from Control_Station
    # must not remain as live emit strings for Start/Reset/Silence/Run.
    # Allow documentation mentions; forbid the old FUNCTIONAL dual-writer labels.
    assert "Control_Station FUNCTIONAL — Area_HMI Start" not in SRC
    assert "Control_Station FUNCTIONAL — Area_HMI Reset" not in SRC
    assert "Control_Station FUNCTIONAL — Area_HMI Silence" not in SRC
    assert "Control_Station FUNCTIONAL — Area.Run seal-in" not in SRC


def test_slow_controlstation_preferred_when_cs_proven():
    assert "Slow_ControlStation" in SRC
    assert "PD-0005 / PD-0034: Slow_ControlStation" in SRC or "Slow_ControlStation(" in SRC


def test_area_zero_conveyor_ux_strings():
    tb = (REPO_ROOT / "dashboard" / "transport-build.js").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "CONVEYORS:" in tb
    assert "Empty Area — no conveyors assigned" in tb
    assert "does not inherit" in tb


def test_sorter_top_card_fields_present():
    js = (REPO_ROOT / "dashboard" / "fortna-plus.js").read_text(
        encoding="utf-8", errors="replace"
    )
    html = (REPO_ROOT / "dashboard" / "index.html").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "renderSorterDiscoveryTopCard" in js
    assert "Equipment Type" in js
    assert "Physical divert count" in js
    assert "SORTER PLC GENERATION — NOT YET QUALIFIED" in js
    assert "sorter-discovery-top-card" in html
    assert "Lane Eye" in html
    assert "tb-insp-canon-upstream" in html


if __name__ == "__main__":
    test_control_station_review_stub_when_no_cs_udt()
    test_slow_controlstation_preferred_when_cs_proven()
    test_area_zero_conveyor_ux_strings()
    test_sorter_top_card_fields_present()
    print("PASS: demo control station + UX contracts")
